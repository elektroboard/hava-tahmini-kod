"""Yeni şehirler için gereken arşivleri indirir (Ankara zaten var).

1. 6 modelin 2024-03'ten bugüne geçmiş tahminleri (Open-Meteo previous runs)
2. İstasyonun Meteostat günlük arşivi (iklim normalleri ve uzun geçmiş için)
3. İstasyonun 2024-01'den bugüne Ogimet SYNOP günlük ölçümleri (eğitim, test ve canlı karşılaştırma için)

Kullanım: python veri_indir_sehirler.py [sehir ...]
"""
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

import kaynaklar
from sehirler import SEHIRLER
from veri_indir_modeller import MODELLER, indir

VERI = Path(__file__).parent / "veri"
BUGUN = date(2026, 11, 22)


def meteostat(istasyon):
    dosya = VERI / "istasyon" / f"{istasyon}.csv.gz"
    if dosya.exists():
        return
    r = requests.get(f"https://bulk.meteostat.net/v2/daily/{istasyon}.csv.gz", timeout=120)
    r.raise_for_status()
    dosya.write_bytes(r.content)
    print(f"meteostat {istasyon}: {len(r.content)} bayt", flush=True)


def ogimet(istasyon, bugun=BUGUN):
    dosya = VERI / f"gozlem_{istasyon}.csv"
    eski = pd.read_csv(dosya) if dosya.exists() else pd.DataFrame(columns=["tarih"])
    if len(eski) and eski["tarih"].min() <= "2024-01-05":
        print(f"ogimet {istasyon}: zaten var ({len(eski)} gün)")
        return
    print(f"ogimet {istasyon}: indiriliyor (yavaş)", flush=True)
    yeni = kaynaklar.gozlem_doldur(date(2024, 1, 1), bugun, istasyon=istasyon)
    tum = yeni.set_index("tarih").combine_first(eski.set_index("tarih")).reset_index().sort_values("tarih")
    tum.to_csv(dosya, index=False)
    eksik = len(pd.date_range("2024-01-01", bugun).difference(pd.to_datetime(tum["tarih"])))
    print(f"ogimet {istasyon}: {len(tum)} gün, {eksik} gün eksik", flush=True)


if __name__ == "__main__":
    secili = sys.argv[1:] or [s for s in SEHIRLER if s != "ankara"]
    for s in secili:
        b = SEHIRLER[s]
        for m in MODELLER:
            indir(m, s, b["lat"], b["lon"])
        meteostat(b["istasyon"])
    for s in secili:
        ogimet(SEHIRLER[s]["istasyon"])
        time.sleep(5)
    print("Bitti.")
