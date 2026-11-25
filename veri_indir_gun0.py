"""Arşiv dosyalarına 'bugün' (0 gün önce) tahmin sütunlarını ekler: tmax_t0, tmin_t0, yagis_t0.
Open-Meteo previous-runs'ta düz 'temperature_2m' = o günün en güncel model çalışması."""
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from veri_indir import ARSIV_SON, getir
from sehirler import SEHIRLER
from veri_indir_modeller import KLASOR, MODELLER


def ekle(sehir, b, model):
    klasor = KLASOR if sehir == "ankara" else KLASOR / sehir
    dosya = klasor / f"{model}.csv"
    df = pd.read_csv(dosya, index_col="time")
    if "tmax_t0" in df.columns:
        print(f"{sehir}/{model}: t0 zaten var", flush=True)
        return
    parcalar, bas = [], date(2024, 3, 1)
    while bas <= ARSIV_SON:
        son = min(bas + timedelta(days=180), ARSIV_SON)
        j = getir("https://previous-runs-api.open-meteo.com/v1/forecast", {
            "latitude": b["lat"], "longitude": b["lon"], "start_date": bas.isoformat(), "end_date": son.isoformat(),
            "hourly": "temperature_2m,precipitation", "models": model, "timezone": "Europe/Istanbul"})
        parcalar.append(pd.DataFrame(j["hourly"]))
        bas = son + timedelta(days=1)
        time.sleep(3)
    s = pd.concat(parcalar)
    s["gun"] = pd.to_datetime(s.pop("time")).dt.date.astype(str)
    g = s.groupby("gun")
    tam = g.count() == 24
    t, p = "temperature_2m", "precipitation"
    yeni = pd.DataFrame({"tmax_t0": g[t].max().where(tam[t]), "tmin_t0": g[t].min().where(tam[t]),
                         "yagis_t0": g[p].sum().where(tam[p])})
    yeni.index.name = "time"
    df.index = df.index.astype(str)
    df = df.join(yeni)
    df = df[["tmax_t0", "tmin_t0", "yagis_t0"] + [c for c in df.columns if not c.endswith("_t0")]]
    df.to_csv(dosya)
    print(f"{sehir}/{model}: t0 eklendi, {df['tmax_t0'].notna().sum()} gün", flush=True)


if __name__ == "__main__":
    for s, b in SEHIRLER.items():
        for m in MODELLER:
            try:
                ekle(s, b, m)
            except Exception as e:
                print(f"{s}/{m}: HATA {e}", flush=True)
    print("Bitti.")
