"""Bizim modelle önümüzdeki günler için Ankara tahmini üretir ve MGM tahminiyle yan yana kaydeder.

Kullanım: python tahmin_yap.py 2026-11-22   (MGM tahmininin alındığı gün)
Model, dünkü güne (son tam gün) kadar olan veriye bakarak tahmin yapar.
"""
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

import deney
from veri_indir import GUNLUK, SEHIRLER as KOORD

KLASOR = Path(__file__).parent
BUGUN = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
TABAN = pd.Timestamp(BUGUN - timedelta(days=1))  # son tam gün
GUN_SAYISI = 6  # bugün + 5 gün (MGM'nin 5 günlük tahminini kapsar)


def son_gunleri_getir():
    """Arşiv dosyalarından sonraki son günleri API'den çeker."""
    tablolar = []
    for s in deney.SEHIRLER:
        lat, lon = KOORD[s]
        for deneme in range(5):
            r = requests.get("https://archive-api.open-meteo.com/v1/archive", params={
                "latitude": lat, "longitude": lon,
                "start_date": (TABAN - pd.Timedelta(days=14)).date().isoformat(), "end_date": TABAN.date().isoformat(),
                "daily": ",".join(GUNLUK), "timezone": "Europe/Istanbul"}, timeout=60)
            if r.status_code == 200:
                break
            print("  ", r.text[:120]); time.sleep(20)
        r.raise_for_status()
        d = pd.DataFrame(r.json()["daily"])
        d["time"] = pd.to_datetime(d["time"])
        d = d.set_index("time").rename(columns=deney.KISA)
        yon = np.deg2rad(d.pop("yon"))
        d["yon_sin"], d["yon_cos"] = np.sin(yon), np.cos(yon)
        tablolar.append(d.add_prefix(f"{s}_"))
    return pd.concat(tablolar, axis=1)


def main():
    gecmis = deney.veri_yukle()
    son = son_gunleri_getir()
    df = son.combine_first(gecmis).sort_index().loc[:TABAN]
    X = deney.ozellikler(df)
    hedef_son = gecmis.index.max()  # eğitimde yalnızca kesinleşmiş ERA5 günleri hedef olur
    print(f"Şehirler: {', '.join(deney.SEHIRLER)} | eğitim hedefleri 1940 - {hedef_son.date()} | tahmin tabanı {TABAN.date()}")

    satirlar = []
    for h in range(1, GUN_SAYISI + 1):
        Xh = X.shift(h)
        egit = Xh.index[(Xh.index > "1940-01-10") & (Xh.index <= hedef_son)]
        hgun = TABAN + pd.Timedelta(days=h)
        x_bugun = X.loc[[TABAN]]
        satir = {"tarih": hgun.date().isoformat(), "kac_gun_sonra": (hgun.date() - BUGUN).days}
        for hedef, ad in (("ankara_tmax", "model_en_yuksek"), ("ankara_tmin", "model_en_dusuk")):
            m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, l2_regularization=1.0, random_state=0)
            m.fit(Xh.loc[egit], df.loc[egit, hedef])
            satir[ad] = round(float(m.predict(x_bugun)[0]), 1)
        c = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, random_state=0)
        c.fit(Xh.loc[egit], (df.loc[egit, "ankara_yagis"] >= deney.YAGIS_ESIK).astype(int))
        satir["model_yagis_olasiligi_%"] = round(100 * float(c.predict_proba(x_bugun)[0, 1]))
        satirlar.append(satir)
        print(f"  {satir['tarih']} hazır")

    tahmin = pd.DataFrame(satirlar)
    mgm_dosya = KLASOR / "veri" / f"mgm_tahmin_{BUGUN.isoformat()}.csv"
    if mgm_dosya.exists():
        tahmin = tahmin.merge(pd.read_csv(mgm_dosya), on="tarih", how="left")
    normal_max = deney.mevsim_normali(gecmis["ankara_tmax"])
    normal_min = deney.mevsim_normali(gecmis["ankara_tmin"])
    gunler = pd.to_datetime(tahmin["tarih"])
    tahmin["normal_en_yuksek"] = [round(float(normal_max[normal_max.index.day_of_year == g.day_of_year].iloc[0]), 1) for g in gunler]
    tahmin["normal_en_dusuk"] = [round(float(normal_min[normal_min.index.day_of_year == g.day_of_year].iloc[0]), 1) for g in gunler]
    tahmin["tahmin_tarihi"] = BUGUN.isoformat()

    kayit = KLASOR / "canli_tahminler.csv"
    if kayit.exists():
        eski = pd.read_csv(kayit)
        tahmin = pd.concat([eski[eski["tahmin_tarihi"] != BUGUN.isoformat()], tahmin])
    tahmin.to_csv(kayit, index=False)
    pd.set_option("display.width", 220)
    print(tahmin[tahmin["tahmin_tarihi"] == BUGUN.isoformat()].drop(columns="tahmin_tarihi").to_string(index=False))


if __name__ == "__main__":
    main()
