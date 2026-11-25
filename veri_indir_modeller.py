"""Birden çok hava tahmin modelinin Ankara için geçmişte yaptığı tahminleri indirir.

Çıktı: veri/modeller/<model>.csv  ->  her gün için tmax_t1..t7, tmin_t1..t7, yagis_t1..t7
(tN = o gün için N gün önce yapılmış tahmin)
"""
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from veri_indir import ARSIV_SON, SEHIRLER, getir

KLASOR = Path(__file__).parent / "veri" / "modeller"
KLASOR.mkdir(parents=True, exist_ok=True)
MODELLER = ["ecmwf_ifs025", "gfs_seamless", "icon_seamless", "gem_seamless", "jma_seamless", "ukmo_seamless"]
UFUK = range(1, 8)


def indir(model, sehir="ankara", lat=None, lon=None):
    """Ankara: veri/modeller/<model>.csv (eski yol); diğer şehirler: veri/modeller/<sehir>/<model>.csv"""
    klasor = KLASOR if sehir == "ankara" else KLASOR / sehir
    klasor.mkdir(parents=True, exist_ok=True)
    dosya = klasor / f"{model}.csv"
    if dosya.exists():
        print(f"{sehir}/{model}: zaten var")
        return
    if lat is None:
        lat, lon = SEHIRLER["ankara"]
    degisken = [f"{v}_previous_day{n}" for v in ("temperature_2m", "precipitation") for n in UFUK]
    parcalar, bas = [], date(2024, 3, 1)
    while bas <= ARSIV_SON:
        son = min(bas + timedelta(days=180), ARSIV_SON)
        print(f"{sehir}/{model}: {bas} - {son}", flush=True)
        j = getir("https://previous-runs-api.open-meteo.com/v1/forecast", {
            "latitude": lat, "longitude": lon, "start_date": bas.isoformat(), "end_date": son.isoformat(),
            "hourly": ",".join(degisken), "models": model, "timezone": "Europe/Istanbul"})
        parcalar.append(pd.DataFrame(j["hourly"]))
        bas = son + timedelta(days=1)
        time.sleep(3)
    s = pd.concat(parcalar)
    s["gun"] = pd.to_datetime(s.pop("time")).dt.date
    g = s.groupby("gun")
    tam = g.count() == 24  # 24 saatin hepsi olmayan günler geçersiz
    cikti = {}
    for n in UFUK:
        t, p = f"temperature_2m_previous_day{n}", f"precipitation_previous_day{n}"
        cikti[f"tmax_t{n}"] = g[t].max().where(tam[t])
        cikti[f"tmin_t{n}"] = g[t].min().where(tam[t])
        cikti[f"yagis_t{n}"] = g[p].sum().where(tam[p])
    df = pd.DataFrame(cikti)
    df.index.name = "time"
    df.to_csv(dosya)
    print(f"{sehir}/{model}: {df['tmax_t1'].notna().sum()} gün geçerli (1 gün önce), {df['tmax_t5'].notna().sum()} (5 gün önce)")


if __name__ == "__main__":
    for m in MODELLER:
        indir(m)
    print("Bitti.")
