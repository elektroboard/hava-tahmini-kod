"""Ankara günlük en yüksek sıcaklık ve yağış tahmini deneyi.

Karşılaştırılanlar (1-7 gün ileri):
  1. Kalıcılık      : "N gün sonra bugünkü gibi olacak"
  2. Mevsim normali : 1994-2023 ortalaması (o takvim günü ±7 gün)
  3. ML (yalnız geçmiş veri): Ankara + 4 şehrin son 3 günü -> gradyan artırma
  4. Hazır tahmin    : Open-Meteo best_match (ECMWF/GFS vb.), N gün önce yapılmış hali
  5. Düzeltilmiş tahmin: hazır tahmin + ML ile yerel hata düzeltmesi

Eğitim: 1940-2023 | Test: 2024-03-01 -> son gün (hazır tahmin arşivinin olduğu dönem)
Doğru kabul edilen değer: ERA5 (istasyon ölçümü değil).
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

KLASOR = Path(__file__).parent
VERI = KLASOR / "veri"
SEHIRLER = [s for s in ["ankara", "istanbul", "eskisehir", "zonguldak", "konya"]
            if (VERI / f"era5_{s}.csv").exists()]
HAZIR_VAR = (VERI / "gecmis_tahminler.csv").exists()
TEST_SON = pd.Timestamp("2026-11-15")
KISA = {"temperature_2m_max": "tmax", "temperature_2m_min": "tmin", "temperature_2m_mean": "tort",
        "precipitation_sum": "yagis", "wind_speed_10m_max": "ruzgar", "wind_direction_10m_dominant": "yon",
        "pressure_msl_mean": "basinc", "relative_humidity_2m_mean": "nem", "cloud_cover_mean": "bulut"}
UFUK = range(1, 8)
TEST_BAS = pd.Timestamp("2024-03-01")
EGITIM_SON = pd.Timestamp("2023-12-31")
YAGIS_ESIK = 1.0  # mm, bu değer ve üstü "yağışlı gün"


def veri_yukle():
    tablolar = []
    for s in SEHIRLER:
        d = pd.read_csv(VERI / f"era5_{s}.csv", parse_dates=["time"]).set_index("time").rename(columns=KISA)
        yon = np.deg2rad(d.pop("yon"))
        d["yon_sin"], d["yon_cos"] = np.sin(yon), np.cos(yon)
        tablolar.append(d.add_prefix(f"{s}_"))
    return pd.concat(tablolar, axis=1).sort_index()


def ozellikler(df):
    X = pd.DataFrame(index=df.index)
    for gecikme in range(3):
        X = X.join(df.shift(gecikme).add_suffix(f"_g{gecikme}"))
    for s in SEHIRLER:  # basınç ve sıcaklık eğilimi
        X[f"{s}_basinc_degisim"] = df[f"{s}_basinc"] - df[f"{s}_basinc"].shift(1)
        X[f"{s}_tort_degisim"] = df[f"{s}_tort"] - df[f"{s}_tort"].shift(1)
    gun = df.index.day_of_year
    X["gun_sin"], X["gun_cos"] = np.sin(2 * np.pi * gun / 365.25), np.cos(2 * np.pi * gun / 365.25)
    X["yil"] = df.index.year  # iklim ısınması eğilimi
    return X


def mevsim_normali(seri):
    ref = seri["1994":"2023"]
    gunluk = ref.groupby(ref.index.day_of_year).mean()
    gunluk = pd.concat([gunluk.iloc[-7:], gunluk, gunluk.iloc[:7]])
    duz = gunluk.rolling(15, center=True).mean().iloc[7:-7]
    return pd.Series(duz.reindex(seri.index.day_of_year).values, index=seri.index)


def main():
    df = veri_yukle()
    X = ozellikler(df)
    tmax = df["ankara_tmax"]
    yagisli = (df["ankara_yagis"] >= YAGIS_ESIK).astype(float)
    normal_tmax = mevsim_normali(tmax)
    normal_yagis = mevsim_normali(yagisli)

    print(f"Kullanılan şehirler: {', '.join(SEHIRLER)} | hazır tahmin arşivi: {'var' if HAZIR_VAR else 'YOK (ön test)'}")
    test_gunleri = tmax.index[(tmax.index >= TEST_BAS) & (tmax.index <= TEST_SON)]
    if HAZIR_VAR:
        hazir = pd.read_csv(VERI / "gecmis_tahminler.csv", parse_dates=["time"]).set_index("time")
        test_gunleri = test_gunleri[hazir.reindex(test_gunleri)[[f"tmax_t{h}" for h in UFUK]].notna().all(axis=1)]

    sonuc_sic, sonuc_yag = [], []
    for h in UFUK:
        # X'in t günü satırı -> t+h hedefi. Hedef gün indeksine kaydırıyoruz.
        Xh = X.shift(h)
        hedef_sic, hedef_yag = tmax, yagisli
        egit = Xh.index[(Xh.index > "1940-01-10") & (Xh.index <= EGITIM_SON)]

        reg = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, max_leaf_nodes=31,
                                            l2_regularization=1.0, random_state=0)
        reg.fit(Xh.loc[egit], hedef_sic.loc[egit])
        clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, random_state=0)
        clf.fit(Xh.loc[egit], hedef_yag.loc[egit])

        g = test_gunleri
        gercek = hedef_sic.loc[g]
        ml = pd.Series(reg.predict(Xh.loc[g]), index=g)
        kalici = tmax.shift(h).loc[g]
        normal = normal_tmax.loc[g]
        mae = lambda p: float(np.mean(np.abs(p - gercek)))
        gy = hedef_yag.loc[g]
        p_ml = clf.predict_proba(Xh.loc[g])[:, 1]
        dogru = lambda p: float(np.mean((np.asarray(p) >= 0.5) == (gy.values == 1)))
        brier = lambda p: float(np.mean((np.asarray(p) - gy.values) ** 2))
        if not HAZIR_VAR:
            sonuc_sic.append({"ufuk": h, "Kalıcılık": mae(kalici), "Mevsim normali": mae(normal),
                              "ML (yalnız geçmiş)": mae(ml)})
            sonuc_yag.append({"ufuk": h, "Hiç yağmaz de (doğru %)": 100 * dogru(np.zeros(len(g))),
                              "ML (doğru %)": 100 * dogru(p_ml),
                              "Mevsim olasılığı Brier": brier(normal_yagis.loc[g]), "ML Brier": brier(p_ml)})
            print(f"{h}. gün tamam")
            continue
        hz = hazir.loc[g, f"tmax_t{h}"]

        # Düzeltilmiş tahmin: hazır tahmin + ML tahmini + mevsim, hatayı öğren.
        # Hazır tahmin arşivi kısa (≈2.5 yıl) olduğu için 6 aylık bloklar halinde
        # "o blok hariç diğerleriyle eğit, o bloğu tahmin et" yapıyoruz.
        Z = pd.DataFrame({"hazir": hz, "ml": ml, "gun_sin": X.loc[g, "gun_sin"], "gun_cos": X.loc[g, "gun_cos"],
                          "dun_tmax": kalici})
        blok = (g.year - g.year.min()) * 2 + (g.month > 6)
        duz = pd.Series(index=g, dtype=float)
        for b in np.unique(blok):
            tr, te = blok != b, blok == b
            m = HistGradientBoostingRegressor(max_iter=150, learning_rate=0.05, max_depth=3, random_state=0)
            m.fit(Z[tr], (gercek - hz)[tr])
            duz[te] = hz[te] + m.predict(Z[te])

        sonuc_sic.append({"ufuk": h, "Kalıcılık": mae(kalici), "Mevsim normali": mae(normal),
                          "ML (yalnız geçmiş)": mae(ml), "Hazır tahmin": mae(hz), "Düzeltilmiş tahmin": mae(duz)})

        # Yağış: yağışlı gün mü?
        p_hz = (hazir.loc[g, f"yagis_t{h}"] >= YAGIS_ESIK).astype(float)
        sonuc_yag.append({"ufuk": h,
                          "Hiç yağmaz de (doğru %)": 100 * dogru(np.zeros(len(g))),
                          "ML (doğru %)": 100 * dogru(p_ml),
                          "Hazır tahmin (doğru %)": 100 * dogru(p_hz),
                          "Mevsim olasılığı Brier": brier(normal_yagis.loc[g]),
                          "ML Brier": brier(p_ml)})
        print(f"{h}. gün tamam")

    sic = pd.DataFrame(sonuc_sic).set_index("ufuk")
    yag = pd.DataFrame(sonuc_yag).set_index("ufuk")
    pd.set_option("display.width", 200)
    print(f"\nTest dönemi: {test_gunleri.min().date()} - {test_gunleri.max().date()} ({len(test_gunleri)} gün)")
    print("\nEN YÜKSEK SICAKLIK - ortalama mutlak hata (°C, düşük = iyi)")
    print(sic.round(2).to_string())
    print(f"\nYAĞIŞLI GÜN (≥{YAGIS_ESIK} mm) - test dönemindeki yağışlı gün oranı: %{100 * yagisli.loc[test_gunleri].mean():.0f}")
    print(yag.round(3).to_string())
    sic.round(3).to_csv(KLASOR / "sonuc_sicaklik.csv")
    yag.round(3).to_csv(KLASOR / "sonuc_yagis.csv")

    fig, ax = plt.subplots(figsize=(9, 5.5))
    stiller = {"Kalıcılık": ("#999999", "--"), "Mevsim normali": ("#bbbbbb", ":"),
               "ML (yalnız geçmiş)": ("#e07b39", "-"), "Hazır tahmin": ("#3a7bd5", "-"),
               "Düzeltilmiş tahmin": ("#2a9d5c", "-")}
    for ad, (renk, cizgi) in stiller.items():
        if ad not in sic:
            continue
        ax.plot(sic.index, sic[ad], marker="o", color=renk, linestyle=cizgi, linewidth=2.2, label=ad)
    ax.set_xlabel("Kaç gün sonrası tahmin ediliyor")
    ax.set_ylabel("Ortalama hata (°C)")
    ax.set_title("Ankara en yüksek sıcaklık tahmini: hangi yöntem kaç gün işe yarıyor?")
    ax.set_xticks(list(UFUK))
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(KLASOR / "sonuc_grafik.png", dpi=130)
    print("\nGrafik: sonuc_grafik.png")


if __name__ == "__main__":
    main()
