"""Deney 2: çoklu model + basit doğrusal düzeltme (MOS) + istasyon gerçeği.

Hedefler:
  - "istasyon": Ankara / Central (WMO 17130, MGM'nin Ankara merkez istasyonu) ölçümleri, 2024-03 .. 2026-03
  - "era5"    : önceki deneyle aynı hedef, 2024-03 .. 2026-11

Yöntemler (her 1-7 gün için ayrı):
  Hazır tahmin (tek)     : Open-Meteo best_match (önceki deneyin "hazır tahmin"i)
  ECMWF                  : en iyi tek model
  Model ortalaması       : 6 modelin düz ortalaması
  Eski düzeltme (GBM)    : önceki deneydeki yöntem (tek model + gradyan artırma)
  Yeni sistem (MOS)      : 6 model + mevsim + dünkü değer -> Ridge regresyonu
  Yeni sistem (güvenli)  : MOS, eğitim verisinde ortalamayı geçemiyorsa ortalamaya döner

Değerlendirme: 6 aylık bloklar; her blok, diğer bloklarla eğitilen modelle tahmin edilir.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression, RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import deney

KLASOR = Path(__file__).parent
VERI = KLASOR / "veri"
MODELLER = ["ecmwf_ifs025", "gfs_seamless", "icon_seamless", "gem_seamless", "jma_seamless", "ukmo_seamless"]
UFUK = range(1, 8)
ESIK = deney.YAGIS_ESIK


def yukle():
    era5 = pd.read_csv(VERI / "era5_ankara.csv", parse_dates=["time"]).set_index("time")
    ist = pd.read_csv(VERI / "istasyon" / "17130.csv.gz", header=None, parse_dates=[0],
                      names=["time", "tavg", "tmin", "tmax", "prcp", "snow", "wdir", "wspd", "wpgt", "pres", "tsun"])
    ist = ist.set_index("time")
    modeller = {m: pd.read_csv(VERI / "modeller" / f"{m}.csv", parse_dates=["time"]).set_index("time") for m in MODELLER}
    best = pd.read_csv(VERI / "gecmis_tahminler.csv", parse_dates=["time"]).set_index("time")
    return era5, ist, modeller, best


def bloklar(idx):
    return np.asarray((idx.year - 2024) * 2 + (idx.month > 6))


def mos_tahmin(Z, y, blok):
    """Blok dışı eğitim + RidgeCV. Ayrıca 'güvenli' sürüm: iç doğrulamada ortalamayı geçemezse ortalama."""
    mos = pd.Series(np.nan, index=Z.index)
    guvenli = pd.Series(np.nan, index=Z.index)
    yap = lambda: make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 20)))
    for b in np.unique(blok):
        tr, te = blok != b, blok == b
        m = yap().fit(Z[tr], y[tr])
        mos[te] = m.predict(Z[te])
        # iç doğrulama: yalnızca eğitim blokları içinde
        ic_mos, ic_ort = [], []
        for b2 in np.unique(blok[tr]):
            tr2, te2 = tr & (blok != b2), blok == b2
            p = yap().fit(Z[tr2], y[tr2]).predict(Z[te2])
            ic_mos.append(np.abs(p - y[te2]).mean())
            ic_ort.append(np.abs(Z.loc[te2, "ortalama"] - y[te2]).mean())
        guvenli[te] = mos[te] if np.mean(ic_mos) < np.mean(ic_ort) else Z.loc[te, "ortalama"]
    return mos, guvenli


def gbm_duzeltme(hz, ek, y, blok):
    """Önceki deneydeki düzeltme: tek hazır tahmin + GBM ile hata öğrenme."""
    Z = pd.concat([hz.rename("hazir"), ek], axis=1)
    duz = pd.Series(np.nan, index=hz.index)
    for b in np.unique(blok):
        tr, te = blok != b, blok == b
        m = HistGradientBoostingRegressor(max_iter=150, learning_rate=0.05, max_depth=3, random_state=0)
        m.fit(Z[tr], (y - hz)[tr])
        duz[te] = hz[te] + m.predict(Z[te])
    return duz


def sicaklik_deneyi(hedef_adi, gercek, era5, modeller, best, degisken):
    """degisken: 'tmax' veya 'tmin'"""
    era5_kolon = "temperature_2m_max" if degisken == "tmax" else "temperature_2m_min"
    normal = deney.mevsim_normali(era5[era5_kolon])
    sonuc = []
    for h in UFUK:
        M = pd.DataFrame({m: modeller[m][f"{degisken}_t{h}"] for m in MODELLER})
        g = gercek.dropna().index.intersection(M.index)
        g = g[M.loc[g, "ecmwf_ifs025"].notna() & best.reindex(g)[f"{degisken}_t{h}" if degisken == "tmax" else "tmax_t1"].notna()]
        M = M.loc[g]
        ort = M.mean(axis=1)
        M = M.apply(lambda s: s.fillna(ort))  # eksik model -> diğerlerinin ortalaması
        gun = g.day_of_year
        Z = M.assign(ortalama=ort, normal=normal.loc[g].values,
                     dunku=era5[era5_kolon].shift(h).loc[g].values,
                     gun_sin=np.sin(2 * np.pi * gun / 365.25), gun_cos=np.cos(2 * np.pi * gun / 365.25))
        y = gercek.loc[g]
        blok = bloklar(g)
        mos, guvenli = mos_tahmin(Z, y, blok)
        mae = lambda p: float(np.mean(np.abs(np.asarray(p) - y.values)))
        satir = {"ufuk": h, "gün sayısı": len(g), "ECMWF": mae(M["ecmwf_ifs025"]), "Model ortalaması": mae(ort),
                 "Yeni sistem (MOS)": mae(mos), "Yeni sistem (güvenli)": mae(guvenli)}
        if degisken == "tmax":
            hz = best.loc[g, f"tmax_t{h}"]
            ek = Z[["gun_sin", "gun_cos", "dunku"]]
            satir = {"ufuk": h, "gün sayısı": len(g), "Hazır tahmin (tek)": mae(hz),
                     "Eski düzeltme (GBM)": mae(gbm_duzeltme(hz, ek, y, blok)), **{k: v for k, v in satir.items() if k not in ("ufuk", "gün sayısı")}}
        sonuc.append(satir)
    return pd.DataFrame(sonuc).set_index("ufuk")


def yagis_deneyi(gercek_mm, modeller, best):
    sonuc = []
    for h in UFUK:
        M = pd.DataFrame({m: modeller[m][f"yagis_t{h}"] for m in MODELLER})
        g = gercek_mm.dropna().index.intersection(M.index)
        g = g[M.loc[g, "ecmwf_ifs025"].notna() & best.reindex(g)[f"yagis_t{h}"].notna()]
        M = M.loc[g]
        M = M.apply(lambda s: s.fillna(M.mean(axis=1)))
        y = (gercek_mm.loc[g] >= ESIK).astype(int).values
        oy = (M >= ESIK).mean(axis=1)  # kaç model yağış diyor
        Z = np.log1p(M).assign(oy=oy, ort=np.log1p(M.mean(axis=1)),
                               gun_sin=np.sin(2 * np.pi * g.day_of_year / 365.25), gun_cos=np.cos(2 * np.pi * g.day_of_year / 365.25))
        blok = bloklar(g)
        p = np.zeros(len(g))
        for b in np.unique(blok):
            tr, te = blok != b, blok == b
            c = make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=1000)).fit(Z[tr], y[tr])
            p[te] = c.predict_proba(Z[te])[:, 1]
        dogru = lambda q: 100 * float(np.mean((np.asarray(q) >= 0.5) == (y == 1)))
        brier = lambda q: float(np.mean((np.asarray(q, dtype=float) - y) ** 2))
        hz = (best.loc[g, f"yagis_t{h}"] >= ESIK).astype(float)
        sonuc.append({"ufuk": h, "Hiç yağmaz (doğru %)": dogru(np.zeros(len(g))),
                      "Hazır tahmin (doğru %)": dogru(hz), "ECMWF (doğru %)": dogru((M["ecmwf_ifs025"] >= ESIK).astype(float)),
                      "Model oylaması (doğru %)": dogru(oy), "Yeni sistem (doğru %)": dogru(p),
                      "Hazır tahmin Brier": brier(hz), "Oylama Brier": brier(oy), "Yeni sistem Brier": brier(p)})
    return pd.DataFrame(sonuc).set_index("ufuk")


def main():
    era5, ist, modeller, best = yukle()
    pd.set_option("display.width", 250)
    sonuclar = {}

    sonuclar["istasyon_tmax"] = sicaklik_deneyi("istasyon", ist["tmax"], era5, modeller, best, "tmax")
    sonuclar["istasyon_tmin"] = sicaklik_deneyi("istasyon", ist["tmin"], era5, modeller, best, "tmin")
    sonuclar["era5_tmax"] = sicaklik_deneyi("era5", era5["temperature_2m_max"], era5, modeller, best, "tmax")
    sonuclar["istasyon_yagis"] = yagis_deneyi(ist["prcp"], modeller, best)
    sonuclar["era5_yagis"] = yagis_deneyi(era5["precipitation_sum"], modeller, best)

    basliklar = {
        "istasyon_tmax": "İSTASYON (Ankara Merkez, gerçek termometre) - EN YÜKSEK sıcaklık, ortalama hata °C",
        "istasyon_tmin": "İSTASYON - EN DÜŞÜK sıcaklık, ortalama hata °C",
        "era5_tmax": "ERA5 (önceki deneyle aynı hedef) - EN YÜKSEK sıcaklık, ortalama hata °C",
        "istasyon_yagis": f"İSTASYON - YAĞIŞLI GÜN (≥{ESIK} mm)",
        "era5_yagis": f"ERA5 - YAĞIŞLI GÜN (≥{ESIK} mm)",
    }
    for k, df in sonuclar.items():
        print(f"\n{basliklar[k]}")
        print(df.round(2).to_string())
        df.round(3).to_csv(KLASOR / f"sonuc2_{k}.csv")

    fig, eksenler = plt.subplots(1, 2, figsize=(13, 5.5), sharey=True)
    stil = {"Hazır tahmin (tek)": ("#3a7bd5", "-"), "Eski düzeltme (GBM)": ("#999999", "--"),
            "ECMWF": ("#8e44ad", ":"), "Model ortalaması": ("#e07b39", "-"),
            "Yeni sistem (MOS)": ("#2a9d5c", "-")}
    for ax, k, baslik in zip(eksenler, ["istasyon_tmax", "era5_tmax"],
                             ["Gerçek istasyon ölçümüne göre", "ERA5'e göre (önceki deneyin hedefi)"]):
        df = sonuclar[k]
        for ad, (renk, cizgi) in stil.items():
            ax.plot(df.index, df[ad], marker="o", color=renk, linestyle=cizgi, linewidth=2.4 if "Yeni" in ad else 1.8, label=ad)
        ax.set_title(f"{baslik}\n({int(df['gün sayısı'].iloc[0])} gün)")
        ax.set_xlabel("Kaç gün sonrası")
        ax.set_xticks(list(UFUK))
        ax.grid(alpha=0.3)
    eksenler[0].set_ylabel("Ortalama hata (°C)")
    eksenler[0].legend()
    fig.suptitle("Ankara en yüksek sıcaklık: yeni sistem (6 model + doğrusal düzeltme) ve öncekiler", fontsize=13)
    fig.tight_layout()
    fig.savefig(KLASOR / "sonuc2_grafik.png", dpi=130)
    print("\nGrafik: sonuc2_grafik.png")


if __name__ == "__main__":
    main()
