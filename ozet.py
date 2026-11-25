"""İndirilen Ankara ve İstanbul ERA5 verilerinin özeti ve grafiği."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

KLASOR = Path(__file__).parent
renkler = {"ankara": "#c0392b", "istanbul": "#2471a3"}
veri = {s: pd.read_csv(KLASOR / "veri" / f"era5_{s}.csv", parse_dates=["time"]).set_index("time")
        for s in renkler}

for s, d in veri.items():
    tam = d.loc[:"2025"]
    yillik = tam["temperature_2m_mean"].groupby(tam.index.year).mean()
    yagis = tam["precipitation_sum"].groupby(tam.index.year).sum()
    print(f"\n=== {s.upper()} ===")
    print(f"Kapsam: {d.index.min().date()} - {d.index.max().date()} ({len(d):,} gün)")
    print(f"En sıcak gün : {d['temperature_2m_max'].idxmax().date()}  {d['temperature_2m_max'].max():.1f} °C")
    print(f"En soğuk gün : {d['temperature_2m_min'].idxmin().date()}  {d['temperature_2m_min'].min():.1f} °C")
    print(f"Yıllık ortalama sıcaklık 1940-1969: {yillik.loc[1940:1969].mean():.1f} °C | 1996-2025: {yillik.loc[1996:2025].mean():.1f} °C")
    print(f"En sıcak yıl: {yillik.idxmax()} ({yillik.max():.1f} °C) | En soğuk yıl: {yillik.idxmin()} ({yillik.min():.1f} °C)")
    print(f"Ortalama yıllık yağış: {yagis.mean():.0f} mm | En kurak yıl: {yagis.idxmin()} ({yagis.min():.0f} mm)")
    print("Son 7 gün:")
    print(d[["temperature_2m_max", "temperature_2m_min", "precipitation_sum"]].tail(7)
          .rename(columns={"temperature_2m_max": "en_yuksek", "temperature_2m_min": "en_dusuk",
                           "precipitation_sum": "yagis_mm"}).to_string())

fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 8))
for s, d in veri.items():
    tam = d.loc[:"2025"]
    y = tam["temperature_2m_mean"].groupby(tam.index.year).mean()
    a1.plot(y.index, y, color=renkler[s], alpha=0.35, linewidth=1)
    a1.plot(y.index, y.rolling(10, center=True).mean(), color=renkler[s], linewidth=2.5,
            label=f"{s.capitalize()} (10 yıllık ortalama)")
    ay = d["temperature_2m_mean"].groupby(d.index.month).mean()
    a2.plot(ay.index, ay, marker="o", color=renkler[s], linewidth=2.2, label=s.capitalize())
a1.set_title("Yıllık ortalama sıcaklık, 1940-2025 (ERA5)")
a1.set_ylabel("°C"); a1.grid(alpha=0.3); a1.legend()
a2.set_title("Aylara göre ortalama sıcaklık")
a2.set_xticks(range(1, 13))
a2.set_xticklabels(["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"])
a2.set_ylabel("°C"); a2.grid(alpha=0.3); a2.legend()
fig.tight_layout()
fig.savefig(KLASOR / "ozet_ankara_istanbul.png", dpi=130)
