"""Ankara + çevre şehirler için ERA5 günlük arşivini ve geçmiş hava tahminlerini indirir."""
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

VERI = Path(__file__).parent / "veri"
VERI.mkdir(exist_ok=True)

SEHIRLER = {
    "ankara": (39.93, 32.86),
    "istanbul": (41.01, 28.98),
    "eskisehir": (39.78, 30.52),
    "zonguldak": (41.45, 31.79),
    "konya": (37.87, 32.48),
}
GUNLUK = [
    "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
    "precipitation_sum", "wind_speed_10m_max", "wind_direction_10m_dominant",
    "pressure_msl_mean", "relative_humidity_2m_mean", "cloud_cover_mean",
]
BUGUN = date(2026, 11, 22)
ARSIV_SON = BUGUN - timedelta(days=7)  # son günler henüz kesin ERA5 değil


def getir(url, params):
    for deneme in range(8):
        r = requests.get(url, params=params, timeout=180)
        if r.status_code == 200:
            return r.json()
        print(f"  HTTP {r.status_code}: {r.text[:150]}", flush=True)
        if "Daily" in r.text:
            raise RuntimeError("Günlük API sınırı doldu, yarın tekrar çalıştırın.")
        if "Hourly" in r.text:  # bir sonraki saat başını bekle
            bekle = 3600 - (time.time() % 3600) + 90
            print(f"  saatlik sınır: {bekle / 60:.0f} dk bekleniyor", flush=True)
            time.sleep(bekle)
        else:
            time.sleep(30 * (deneme + 1))
    raise RuntimeError("İndirme başarısız")


def arsiv_indir():
    for ad, (lat, lon) in SEHIRLER.items():
        dosya = VERI / f"era5_{ad}.csv"
        if dosya.exists():
            print(f"{ad}: zaten var")
            continue
        # Ücretsiz API kotası için Ankara dışındaki şehirler 1980'den başlıyor.
        ilk_yil = 1940 if ad == "ankara" else 1980
        parcalar = []
        for bas in range(ilk_yil, ARSIV_SON.year + 1, 20):
            son = min(date(bas + 19, 12, 31), ARSIV_SON)
            parca = VERI / f"_parca_{ad}_{bas}.csv"
            if not parca.exists():
                print(f"{ad}: {bas}-{son.year}", flush=True)
                j = getir("https://archive-api.open-meteo.com/v1/archive", {
                    "latitude": lat, "longitude": lon,
                    "start_date": f"{bas}-01-01", "end_date": son.isoformat(),
                    "daily": ",".join(GUNLUK), "timezone": "Europe/Istanbul",
                })
                pd.DataFrame(j["daily"]).to_csv(parca, index=False)
                time.sleep(2)
            parcalar.append(pd.read_csv(parca))
        pd.concat(parcalar).to_csv(dosya, index=False)
        for p in VERI.glob(f"_parca_{ad}_*.csv"):
            p.unlink()


def tahmin_indir():
    """Geçmişte yapılmış tahminler: previous_dayN = N gün önce yapılan tahmin."""
    dosya = VERI / "gecmis_tahminler.csv"
    if dosya.exists():
        print("tahminler: zaten var")
        return
    lat, lon = SEHIRLER["ankara"]
    degiskenler = [f"{v}_previous_day{n}" for v in ("temperature_2m", "precipitation") for n in range(1, 8)]
    parcalar = []
    bas = date(2024, 3, 1)
    while bas <= ARSIV_SON:
        son = min(bas + timedelta(days=180), ARSIV_SON)
        print(f"tahminler: {bas} - {son}")
        j = getir("https://previous-runs-api.open-meteo.com/v1/forecast", {
            "latitude": lat, "longitude": lon,
            "start_date": bas.isoformat(), "end_date": son.isoformat(),
            "hourly": ",".join(degiskenler), "models": "best_match",
            "timezone": "Europe/Istanbul",
        })
        parcalar.append(pd.DataFrame(j["hourly"]))
        bas = son + timedelta(days=1)
        time.sleep(2)
    saatlik = pd.concat(parcalar)
    saatlik["time"] = pd.to_datetime(saatlik["time"])
    saatlik["gun"] = saatlik["time"].dt.date
    agg = {f"temperature_2m_previous_day{n}": "max" for n in range(1, 8)}
    agg |= {f"precipitation_previous_day{n}": "sum" for n in range(1, 8)}
    gunluk = saatlik.groupby("gun").agg(agg)
    # 24 saatin tamamı yoksa o günü at
    eksik = saatlik.groupby("gun")[list(agg)].count() < 24
    gunluk = gunluk.mask(eksik)
    gunluk.columns = [c.replace("temperature_2m_previous_day", "tmax_t").replace("precipitation_previous_day", "yagis_t")
                      for c in gunluk.columns]
    gunluk.index.name = "time"
    gunluk.to_csv(dosya)


if __name__ == "__main__":
    arsiv_indir()
    tahmin_indir()
    print("Bitti.")
