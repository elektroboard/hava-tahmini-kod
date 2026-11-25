"""Ek Open-Meteo modellerini Ankara'da dener: her aday, mevcut 6 modele eklenince geriye testte iyileştiriyor mu?

Kullanım: python deney_ek_modeller.py   (Open-Meteo günlük kotası boşken çalıştırın; ~2 dk/model)
Çıktı: deney_ek_modeller.csv  (kac_gun_sonra x aday: en yüksek/en düşük hata farkı, negatif = iyileşme)
"""
import pandas as pd

import sistem
from veri_indir_modeller import indir

ADAYLAR = ["ecmwf_aifs025", "meteofrance_seamless", "metno_seamless", "cma_grib2", "knmi_seamless", "dmi_seamless"]
TABAN = list(sistem.MODELLER)


def calistir():
    taban = pd.DataFrame(sistem.geriye_test("ankara")).set_index("kac_gun_sonra")
    sonuc = []
    for a in ADAYLAR:
        try:
            indir(a)
            sistem.MODELLER = TABAN + [a]
            df = pd.DataFrame(sistem.geriye_test("ankara")).set_index("kac_gun_sonra")
        except Exception as e:
            print(f"{a}: atlandı ({e})", flush=True)
            continue
        finally:
            sistem.MODELLER = TABAN
        for h in df.index:
            sonuc.append({"aday": a, "kac_gun_sonra": h,
                          "tmax_fark": round(df.loc[h, "tmax_bizim_sistem"] - taban.loc[h, "tmax_bizim_sistem"], 3),
                          "tmin_fark": round(df.loc[h, "tmin_bizim_sistem"] - taban.loc[h, "tmin_bizim_sistem"], 3),
                          "yagis_dogru_fark": round(df.loc[h, "yagis_bizim_dogru"] - taban.loc[h, "yagis_bizim_dogru"], 2),
                          "gun_sayisi": df.loc[h, "tmax_gun"], "taban_gun_sayisi": taban.loc[h, "tmax_gun"]})
        pd.DataFrame(sonuc).to_csv("deney_ek_modeller.csv", index=False)
    print(pd.DataFrame(sonuc).groupby("aday")[["tmax_fark", "tmin_fark", "yagis_dogru_fark"]].mean().round(3))


if __name__ == "__main__":
    calistir()
