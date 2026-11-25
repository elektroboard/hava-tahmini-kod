"""Çok şehirli tahmin sistemi: 6 model + istasyona göre doğrusal düzeltme (MOS).

Her şehir ve her "kaç gün sonrası" (1-7) için ayrı model:
  girdiler: 6 modelin tahmini, modellerin ortalaması, mevsim normali (istasyon 2003-2023),
            tahminin yapıldığı günden bir önceki günün ölçümü, yılın günü (sin/cos)
  hedef   : istasyonda ölçülen en yüksek / en düşük sıcaklık; yağış için 1 mm ve üzeri (lojistik)
"""
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import LogisticRegression, RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from sehirler import SEHIRLER

KLASOR = Path(__file__).parent
VERI = KLASOR / "veri"
MODELLER = ["ecmwf_ifs025", "gfs_seamless", "icon_seamless", "gem_seamless", "jma_seamless", "ukmo_seamless"]
UFUK = range(1, 8)
ESIK = 1.0
DEG = {"tmax": "en_yuksek", "tmin": "en_dusuk"}


# ---------- veri ----------
def gozlem(sehir: str) -> pd.DataFrame:
    """İstasyonun günlük ölçümleri: Ogimet varsa o, yoksa Meteostat. index: tarih (Timestamp)."""
    ist = SEHIRLER[sehir]["istasyon"]
    ms = pd.read_csv(VERI / "istasyon" / f"{ist}.csv.gz", header=None, usecols=[0, 2, 3, 4],
                     names=["tarih", "en_dusuk", "en_yuksek", "yagis_mm"]).assign(kaynak="Meteostat")
    yol = VERI / f"gozlem_{ist}.csv"
    if yol.exists():
        og = pd.read_csv(yol).rename(columns={"gercek_en_yuksek": "en_yuksek", "gercek_en_dusuk": "en_dusuk",
                                              "gercek_yagis_mm": "yagis_mm"}).assign(kaynak="Ogimet SYNOP")
        og = og.dropna(subset=["en_yuksek", "en_dusuk"], how="all")
        ms = pd.concat([og, ms[~ms["tarih"].isin(og["tarih"])]])
    ms["tarih"] = pd.to_datetime(ms["tarih"])
    return ms.set_index("tarih").sort_index()[["en_yuksek", "en_dusuk", "yagis_mm", "kaynak"]]


def model_arsivi(sehir: str) -> dict:
    klasor = VERI / "modeller" if sehir == "ankara" else VERI / "modeller" / sehir
    return {m: pd.read_csv(klasor / f"{m}.csv", parse_dates=["time"]).set_index("time") for m in MODELLER}


def normal_tablosu(seri: pd.Series, bas=2003, son=2023) -> pd.Series:
    """Yılın her günü (1-366) için ±7 gün yumuşatılmış ortalama."""
    ref = seri.loc[str(bas):str(son)].dropna()
    g = ref.groupby(ref.index.day_of_year).mean().reindex(range(1, 367)).interpolate(limit_direction="both")
    g = pd.concat([g.iloc[-7:], g, g.iloc[:7]]).rolling(15, center=True, min_periods=1).mean().iloc[7:-7]
    g.index = range(1, 367)
    return g


def _gun(idx):
    d = idx.day_of_year
    return np.sin(2 * np.pi * d / 365.25), np.cos(2 * np.pi * d / 365.25)


def ozellik(M: pd.DataFrame, normal: np.ndarray, dunku: np.ndarray) -> pd.DataFrame:
    ort = M.mean(axis=1)
    M = M.apply(lambda c: c.fillna(ort))
    dunku = pd.Series(dunku, index=M.index).fillna(pd.Series(normal, index=M.index))
    s, c = _gun(M.index)
    return M.assign(ortalama=ort.values, normal=normal, dunku=dunku.values, gun_sin=s, gun_cos=c)


def yagis_ozellik(M: pd.DataFrame) -> pd.DataFrame:
    M = M.apply(lambda c: c.fillna(M.mean(axis=1)))
    s, c = _gun(M.index)
    return np.log1p(M).assign(oy=(M >= ESIK).mean(axis=1), ort=np.log1p(M.mean(axis=1)), gun_sin=s, gun_cos=c)


def egitim_verisi(sehir, h, deg, obs=None, arsiv=None):
    obs = gozlem(sehir) if obs is None else obs
    arsiv = model_arsivi(sehir) if arsiv is None else arsiv
    alan = DEG[deg]
    M = pd.DataFrame({m: arsiv[m][f"{deg}_t{h}"] for m in MODELLER})
    y = obs[alan].dropna()
    g = y.index.intersection(M.index)
    g = g[M.loc[g, "ecmwf_ifs025"].notna()]
    nt = normal_tablosu(obs[alan])
    normal = nt.loc[g.day_of_year].to_numpy()
    dunku = obs[alan].reindex(g - pd.Timedelta(days=h + 1)).to_numpy()
    return ozellik(M.loc[g], normal, dunku), y.loc[g], M.loc[g], nt


def yagis_egitim(sehir, h, obs=None, arsiv=None):
    obs = gozlem(sehir) if obs is None else obs
    arsiv = model_arsivi(sehir) if arsiv is None else arsiv
    M = pd.DataFrame({m: arsiv[m][f"yagis_t{h}"] for m in MODELLER})
    y = obs["yagis_mm"].dropna()
    g = y.index.intersection(M.index)
    g = g[M.loc[g, "ecmwf_ifs025"].notna()]
    return yagis_ozellik(M.loc[g]), (y.loc[g] >= ESIK).astype(int), M.loc[g]


def mos():
    return make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 20)))


def lojistik():
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=1000))


# ---------- geçmiş test ----------
def geriye_test(sehir):
    """6 aylık bloklar: her blok, diğer bloklarla eğitilen modelle tahmin edilir."""
    obs, arsiv = gozlem(sehir), model_arsivi(sehir)
    satirlar = []
    for h in UFUK:
        satir = {"sehir": sehir, "kac_gun_sonra": h}
        for deg in ("tmax", "tmin"):
            Z, y, M, _ = egitim_verisi(sehir, h, deg, obs, arsiv)
            blok = np.asarray((Z.index.year - Z.index.year.min()) * 2 + (Z.index.month > 6))
            p = pd.Series(np.nan, index=Z.index)
            for b in np.unique(blok):
                tr, te = blok != b, blok == b
                if tr.sum() < 100:
                    continue
                p[te] = mos().fit(Z[tr], y[tr]).predict(Z[te])
            ok = p.notna()
            mae = lambda v: round(float(np.mean(np.abs(np.asarray(v)[ok] - y.values[ok]))), 3)
            satir[f"{deg}_gun"] = int(ok.sum())
            satir[f"{deg}_ecmwf"] = mae(M["ecmwf_ifs025"])
            satir[f"{deg}_model_ortalamasi"] = mae(Z["ortalama"])
            satir[f"{deg}_bizim_sistem"] = mae(p)
        Z, y, M = yagis_egitim(sehir, h, obs, arsiv)
        blok = np.asarray((Z.index.year - Z.index.year.min()) * 2 + (Z.index.month > 6))
        p = pd.Series(np.nan, index=Z.index)
        for b in np.unique(blok):
            tr, te = blok != b, blok == b
            if tr.sum() < 100 or y[tr].nunique() < 2:
                continue
            p[te] = lojistik().fit(Z[tr], y[tr]).predict_proba(Z[te])[:, 1]
        ok = p.notna().to_numpy()
        yv = y.to_numpy()[ok]
        satir["yagis_hic_yagmaz_dogru"] = round(100 * float(np.mean(yv == 0)), 1)
        satir["yagis_ecmwf_dogru"] = round(100 * float(np.mean((M["ecmwf_ifs025"].to_numpy()[ok] >= ESIK) == (yv == 1))), 1)
        satir["yagis_bizim_dogru"] = round(100 * float(np.mean((p.to_numpy()[ok] >= 0.5) == (yv == 1))), 1)
        satirlar.append(satir)
    return satirlar


# ---------- canlı tahmin ----------
def guncel_modeller(sehir, bugun, gun=15, bas=1):
    b = SEHIRLER[sehir]
    r = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": b["lat"], "longitude": b["lon"], "timezone": "Europe/Istanbul",
        "hourly": "temperature_2m,precipitation", "models": ",".join(MODELLER),
        "start_date": (pd.Timestamp(bugun) + pd.Timedelta(days=bas)).date().isoformat(),
        "end_date": (pd.Timestamp(bugun) + pd.Timedelta(days=gun)).date().isoformat()}, timeout=60)
    r.raise_for_status()
    s = pd.DataFrame(r.json()["hourly"])
    s["gun"] = pd.to_datetime(s.pop("time")).dt.normalize()
    g = s.groupby("gun")
    tmax, tmin, yagis = {}, {}, {}
    for m in MODELLER:
        t, p = f"temperature_2m_{m}", f"precipitation_{m}"
        if t not in s:
            continue
        tam_t, tam_p = g[t].count() == 24, g[p].count() == 24
        tmax[m], tmin[m], yagis[m] = g[t].max().where(tam_t), g[t].min().where(tam_t), g[p].sum().where(tam_p)
    return {"tmax": pd.DataFrame(tmax).reindex(columns=MODELLER), "tmin": pd.DataFrame(tmin).reindex(columns=MODELLER),
            "yagis": pd.DataFrame(yagis).reindex(columns=MODELLER)}


def hava_kodlari(sehir, bugun, gun=15):
    b = SEHIRLER[sehir]
    r = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": b["lat"], "longitude": b["lon"], "timezone": "Europe/Istanbul", "daily": "weather_code",
        "models": "ecmwf_ifs025", "start_date": (pd.Timestamp(bugun) + pd.Timedelta(days=1)).date().isoformat(),
        "end_date": (pd.Timestamp(bugun) + pd.Timedelta(days=gun)).date().isoformat()}, timeout=60)
    r.raise_for_status()
    d = r.json()["daily"]
    return {t: (int(k) if k is not None else None) for t, k in zip(d["time"], d["weather_code"])}


def canli_tahmin(sehir, bugun, obs=None):
    """1-7 gün: düzeltilmiş tahmin; 8-14 gün: modellerin ham ortalaması. Liste döner."""
    obs = gozlem(sehir) if obs is None else obs
    arsiv = model_arsivi(sehir)
    simdi = guncel_modeller(sehir, bugun)
    dun = pd.Timestamp(bugun) - pd.Timedelta(days=1)
    satirlar = []
    for gun in simdi["tmax"].index:
        h = (gun - pd.Timestamp(bugun)).days
        if h < 1 or h > 14:
            continue
        Mx, Mn, My = simdi["tmax"].loc[[gun]], simdi["tmin"].loc[[gun]], simdi["yagis"].loc[[gun]]
        n = int(Mx.notna().sum(axis=1).iloc[0])
        if n < 2:
            continue
        satir = {"sehir": sehir, "tarih": gun.date().isoformat(), "kac_gun_sonra": h,
                 "en_yuksek_alt": round(float(Mx.min(axis=1).iloc[0]), 1), "en_yuksek_ust": round(float(Mx.max(axis=1).iloc[0]), 1),
                 "en_dusuk_alt": round(float(Mn.min(axis=1).iloc[0]), 1), "en_dusuk_ust": round(float(Mn.max(axis=1).iloc[0]), 1),
                 "ecmwf_en_yuksek": None if pd.isna(Mx["ecmwf_ifs025"].iloc[0]) else round(float(Mx["ecmwf_ifs025"].iloc[0]), 1)}
        if h <= 7:
            for deg, M in (("tmax", Mx), ("tmin", Mn)):
                Z, y, _, nt = egitim_verisi(sehir, h, deg, obs, arsiv)
                m = mos().fit(Z, y)
                d = obs[DEG[deg]].get(dun, np.nan)
                Zn = ozellik(M, np.array([nt.loc[gun.day_of_year]]), np.array([d]))
                satir[DEG[deg]] = round(float(m.predict(Zn[Z.columns])[0]), 1)
            Z, y, _ = yagis_egitim(sehir, h, obs, arsiv)
            c = lojistik().fit(Z, y)
            satir["yagis_olasiligi"] = round(100 * float(c.predict_proba(yagis_ozellik(My)[Z.columns])[0, 1]))
            satir["tur"] = "Bizim sistem"
            satir["guven"] = "yüksek" if h <= 5 else "orta"
        else:
            yg = My.iloc[0].dropna()
            satir["en_yuksek"] = round(float(Mx.mean(axis=1).iloc[0]), 1)
            satir["en_dusuk"] = round(float(Mn.mean(axis=1).iloc[0]), 1)
            satir["yagis_olasiligi"] = round(100 * float((yg >= ESIK).mean())) if len(yg) else None
            satir["tur"] = f"{n} modelin ortalaması"
            satir["guven"] = "düşük"
        satirlar.append(satir)
    return satirlar


def bugun_tahmin(sehir, bugun, obs=None):
    """Bugün için (0 gün önceki model çalışmasıyla eğitilmiş) düzeltilmiş tahmin. t0 arşivi yoksa None."""
    obs = gozlem(sehir) if obs is None else obs
    arsiv = model_arsivi(sehir)
    if any("tmax_t0" not in a.columns for a in arsiv.values()):
        return None
    simdi = guncel_modeller(sehir, bugun, gun=0, bas=0)
    gun = pd.Timestamp(bugun)
    if gun not in simdi["tmax"].index:
        return None
    Mx, Mn, My = simdi["tmax"].loc[[gun]], simdi["tmin"].loc[[gun]], simdi["yagis"].loc[[gun]]
    if int(Mx.notna().sum(axis=1).iloc[0]) < 2:
        return None
    dun = gun - pd.Timedelta(days=1)
    sonuc = {}
    for deg, M in (("tmax", Mx), ("tmin", Mn)):
        Z, y, _, nt = egitim_verisi(sehir, 0, deg, obs, arsiv)
        m = mos().fit(Z, y)
        Zn = ozellik(M, np.array([nt.loc[gun.day_of_year]]), np.array([obs[DEG[deg]].get(dun, np.nan)]))
        sonuc[DEG[deg]] = round(float(m.predict(Zn[Z.columns])[0]))
    Z, y, _ = yagis_egitim(sehir, 0, obs, arsiv)
    c = lojistik().fit(Z, y)
    sonuc["yagis"] = round(100 * float(c.predict_proba(yagis_ozellik(My)[Z.columns])[0, 1]))
    return sonuc


def iklim_tablosu(sehir, bugun, obs=None):
    obs = gozlem(sehir) if obs is None else obs
    d = obs.loc["2010-01-01":f"{bugun.year - 1}-12-31"]
    doy = d.index.day_of_year.to_numpy()
    satirlar = []
    for g in range(1, 367):
        fark = np.minimum((doy - g) % 366, (g - doy) % 366)
        p = d[fark <= 7]
        mx, mn, yg = p["en_yuksek"].dropna(), p["en_dusuk"].dropna(), p["yagis_mm"].dropna()
        r1 = lambda v: None if pd.isna(v) else round(float(v), 1)
        satirlar.append({
            "sehir": sehir, "gun_no": g,
            "en_yuksek_ort": r1(mx.mean()), "en_yuksek_p10": r1(mx.quantile(0.1)), "en_yuksek_p90": r1(mx.quantile(0.9)),
            "en_dusuk_ort": r1(mn.mean()), "en_dusuk_p10": r1(mn.quantile(0.1)), "en_dusuk_p90": r1(mn.quantile(0.9)),
            "yagis_olasiligi": round(100 * float((yg >= ESIK).mean())) if len(yg) else None,
            "don_olasiligi": round(100 * float((mn < 0).mean())) if len(mn) else None,
            "ornek_gun": int(len(mx)), "yil_sayisi": int(p.index.year.nunique())})
    return satirlar
