"""Yeni sistemle (6 model + MOS, istasyon hedefli) önümüzdeki 5 gün için Ankara tahmini ve MGM ile karşılaştırma.

Kullanım: python canli2.py 2026-11-22
"""
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import LogisticRegression, RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import deney
import deney2

KLASOR = Path(__file__).parent
BUGUN = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
GUN = 5
LAT, LON = 39.93, 32.86


def guncel_tahminler():
    r = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": LAT, "longitude": LON, "timezone": "Europe/Istanbul",
        "hourly": "temperature_2m,precipitation", "models": ",".join(deney2.MODELLER),
        "start_date": (BUGUN + timedelta(days=1)).isoformat(),
        "end_date": (BUGUN + timedelta(days=GUN)).isoformat()}, timeout=60)
    r.raise_for_status()
    s = pd.DataFrame(r.json()["hourly"])
    s["gun"] = pd.to_datetime(s.pop("time")).dt.normalize()
    g = s.groupby("gun")
    sonuc = {}
    for m in deney2.MODELLER:
        t, p = f"temperature_2m_{m}", f"precipitation_{m}"
        tam_t, tam_p = g[t].count() == 24, g[p].count() == 24
        sonuc[m] = pd.DataFrame({"tmax": g[t].max().where(tam_t), "tmin": g[t].min().where(tam_t),
                                 "yagis": g[p].sum().where(tam_p)})
    return sonuc


def son_era5():
    r = requests.get("https://archive-api.open-meteo.com/v1/archive", params={
        "latitude": LAT, "longitude": LON, "timezone": "Europe/Istanbul",
        "start_date": (BUGUN - timedelta(days=10)).isoformat(), "end_date": BUGUN.isoformat(),
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum"}, timeout=60)
    r.raise_for_status()
    d = pd.DataFrame(r.json()["daily"])
    d["time"] = pd.to_datetime(d["time"])
    return d.set_index("time")


def ozellik(M, normal, dunku, gunler):
    ort = M.mean(axis=1)
    M = M.apply(lambda s: s.fillna(ort))
    gun = gunler.day_of_year
    return M.assign(ortalama=ort.values, normal=normal, dunku=dunku,
                    gun_sin=np.sin(2 * np.pi * gun / 365.25), gun_cos=np.cos(2 * np.pi * gun / 365.25))


def main():
    era5, ist, modeller, _ = deney2.yukle()
    era5 = son_era5().combine_first(era5)
    simdi = guncel_tahminler()
    hedef_gunler = pd.date_range(BUGUN + timedelta(days=1), periods=GUN)
    satirlar = []
    for h, gun in enumerate(hedef_gunler, start=1):
        satir = {"tarih": gun.date().isoformat()}
        for dg, kolon in (("tmax", "temperature_2m_max"), ("tmin", "temperature_2m_min")):
            normal = deney.mevsim_normali(era5[kolon])
            # eğitim: geçmiş tahmin arşivi + istasyon ölçümü
            M = pd.DataFrame({m: modeller[m][f"{dg}_t{h}"] for m in deney2.MODELLER})
            y = ist[dg].dropna()
            g = y.index.intersection(M.index)
            g = g[M.loc[g, "ecmwf_ifs025"].notna()]
            Z = ozellik(M.loc[g], normal.loc[g].values, era5[kolon].shift(h).loc[g].values, g)
            mos = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 20))).fit(Z, y.loc[g])
            # bugünkü girdiler
            Mn = pd.DataFrame({m: [simdi[m].loc[gun, dg]] for m in deney2.MODELLER}, index=[gun])
            norm_g = normal[normal.index.day_of_year == gun.day_of_year].iloc[0]
            Zn = ozellik(Mn, [norm_g], [era5[kolon].loc[pd.Timestamp(BUGUN)]], pd.DatetimeIndex([gun]))
            satir[f"bizim_{dg}"] = round(float(mos.predict(Zn[Z.columns])[0]), 1)
            satir[f"ecmwf_{dg}"] = round(float(Mn["ecmwf_ifs025"].iloc[0]), 1)
            satir[f"modeller_{dg}_aralik"] = f"{Mn.min(axis=1).iloc[0]:.0f}..{Mn.max(axis=1).iloc[0]:.0f}"
        # yağış olasılığı
        M = pd.DataFrame({m: modeller[m][f"yagis_t{h}"] for m in deney2.MODELLER})
        y = ist["prcp"].dropna()
        g = y.index.intersection(M.index)
        g = g[M.loc[g, "ecmwf_ifs025"].notna()]

        def yz(Mx, idx):
            Mx = Mx.apply(lambda s: s.fillna(Mx.mean(axis=1)))
            return np.log1p(Mx).assign(oy=(Mx >= deney.YAGIS_ESIK).mean(axis=1), ort=np.log1p(Mx.mean(axis=1)),
                                       gun_sin=np.sin(2 * np.pi * idx.day_of_year / 365.25),
                                       gun_cos=np.cos(2 * np.pi * idx.day_of_year / 365.25))
        c = make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=1000)).fit(
            yz(M.loc[g], g), (y.loc[g] >= deney.YAGIS_ESIK).astype(int))
        Mn = pd.DataFrame({m: [simdi[m].loc[gun, "yagis"]] for m in deney2.MODELLER}, index=[gun])
        satir["bizim_yagis_%"] = round(100 * float(c.predict_proba(yz(Mn, pd.DatetimeIndex([gun])))[0, 1]))
        satir["modeller_yagis_mm"] = f"{Mn.min(axis=1).iloc[0]:.1f}..{Mn.max(axis=1).iloc[0]:.1f}"
        satirlar.append(satir)

    df = pd.DataFrame(satirlar)
    mgm = KLASOR / "veri" / f"mgm_tahmin_{BUGUN.isoformat()}.csv"
    if mgm.exists():
        df = df.merge(pd.read_csv(mgm), on="tarih", how="left")
    df.insert(0, "tahmin_tarihi", BUGUN.isoformat())
    kayit = KLASOR / "canli_tahminler_v2.csv"
    if kayit.exists():
        eski = pd.read_csv(kayit)
        df = pd.concat([eski[eski["tahmin_tarihi"] != BUGUN.isoformat()], df])
    df.to_csv(kayit, index=False)
    pd.set_option("display.width", 250)
    print(df[df["tahmin_tarihi"] == BUGUN.isoformat()].drop(columns="tahmin_tarihi").to_string(index=False))


if __name__ == "__main__":
    main()
