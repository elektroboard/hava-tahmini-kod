"""Dış kaynaklardan günlük veri çekme.

mgm_tahmin()  : MGM'nin bir il için 5 günlük tahmini (herkese açık sayfa, Edge ile görüntülenip okunur)
gozlemler()   : bir istasyonun (WMO no) gerçekleşen günlük ölçümleri (Ogimet SYNOP özeti)
"""
import html
import os
import re
from datetime import date, timedelta

import pandas as pd
import requests

MGM_URL = "https://www.mgm.gov.tr/tahmin/il-ve-ilceler.aspx"
AYLAR = {"Ocak": 1, "Şubat": 2, "Mart": 3, "Nisan": 4, "Mayıs": 5, "Haziran": 6, "Temmuz": 7,
         "Ağustos": 8, "Eylül": 9, "Ekim": 10, "Kasım": 11, "Aralık": 12}


def mgm_tahmin(bugun: date, il: str = "Ankara", konum: bool = False):
    """konum=True ise (tahmin, {"rakim", "enlem", "boylam"}) döner."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        kanal = os.environ.get("MGM_KANAL", "msedge")  # bulutta "chromium"
        tarayici = p.chromium.launch(headless=True) if kanal == "chromium" else p.chromium.launch(channel=kanal, headless=True)
        sayfa = tarayici.new_page()
        sayfa.goto(MGM_URL + "?il=" + il, wait_until="domcontentloaded", timeout=60000)
        sayfa.wait_for_function(
            "() => [...document.querySelectorAll('tr')].filter(r => /\\d+ \\S+ \\S+/.test(r.innerText) && r.querySelector('img[title]')).length >= 5",
            timeout=60000)
        satirlar = sayfa.evaluate("""() => [...document.querySelectorAll('tr')]
            .filter(r => r.querySelector('img[title]') && /^\\s*\\d{1,2} \\S+ \\S+/.test(r.innerText))
            .map(r => ({metin: r.innerText, hadise: [...r.querySelectorAll('img[title]')].map(i => i.title).filter(Boolean)[0] || ''}))""")
        govde = sayfa.inner_text("body")
        tarayici.close()
    yer = {}
    for ad, etiket in (("rakim", "Rakım"), ("enlem", "Enlem"), ("boylam", "Boylam")):
        m = re.search(etiket + r":\s*(-?[\d.,]+)", govde)
        if m:
            yer[ad] = float(m.group(1).replace(",", "."))

    kayit = []
    for s in satirlar:
        parca = [x.strip() for x in s["metin"].split("\t") if x.strip()]
        m = re.match(r"(\d{1,2}) (\S+)", parca[0])
        if not m or m.group(2) not in AYLAR:
            continue
        ay, gun = AYLAR[m.group(2)], int(m.group(1))
        yil = bugun.year + (1 if ay < bugun.month else 0)
        sayilar = [float(x.replace(",", ".")) for x in parca[1:] if re.fullmatch(r"-?\d+(,\d+)?", x)]
        kayit.append({"tarih": date(yil, ay, gun).isoformat(), "mgm_en_dusuk": sayilar[0],
                      "mgm_en_yuksek": sayilar[1], "mgm_hadise": s["hadise"]})
    df = pd.DataFrame(kayit).drop_duplicates("tarih")
    if len(df) < 5:
        raise RuntimeError(f"MGM tahmini okunamadı: {il} ({len(df)} satır)")
    return (df.head(5), yer) if konum else df.head(5)


def gozlemler(bugun: date, gun_sayisi: int = 30, istasyon: str = "17130") -> pd.DataFrame:
    """Ogimet 06:00 UTC günlük özeti. D satırında: en yüksek = D-1 gündüzü, en düşük = D sabahı,
    yağış = D-1 06 UTC -> D 06 UTC (çoğunlukla D-1'e ait)."""
    r = requests.get("https://www.ogimet.com/cgi-bin/gsynres", params={
        "lang": "en", "ind": istasyon, "ndays": gun_sayisi, "ano": bugun.year, "mes": bugun.month,
        "day": bugun.day, "hora": 6, "enviar": "Ver"}, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    r.raise_for_status()
    metin = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text)))

    def sayi(x):
        if x == "Tr":
            return 0.0
        try:
            return float(x)
        except ValueError:
            return None

    tmax, tmin, yagis = {}, {}, {}
    for m in re.finditer(r"(\d{2})/(\d{2}) (\S+) (\S+) (?:\S+ ){8}(\S+) ", metin):
        ay, gun = int(m.group(1)), int(m.group(2))
        d = date(bugun.year - (1 if ay > bugun.month else 0), ay, gun)
        onceki = d - timedelta(days=1)
        tmax[onceki], tmin[d], yagis[onceki] = sayi(m.group(3)), sayi(m.group(4)), sayi(m.group(5))
    gunler = sorted(set(tmax) | set(tmin))
    return pd.DataFrame({"tarih": [g.isoformat() for g in gunler],
                         "gercek_en_yuksek": [tmax.get(g) for g in gunler],
                         "gercek_en_dusuk": [tmin.get(g) for g in gunler],
                         "gercek_yagis_mm": [yagis.get(g) for g in gunler]})


def gozlem_doldur(bas: date, son: date, parca_gun: int = 30, istasyon: str = "17130") -> pd.DataFrame:
    """bas..son aralığını Ogimet'ten parça parça çeker (sunucuyu yormamak için aralarda bekler)."""
    import time
    parcalar, bitis = [], son
    while bitis >= bas:
        for deneme in range(4):
            p = gozlemler(bitis, parca_gun, istasyon)
            if len(p):
                break
            time.sleep(30 * (deneme + 1))  # Ogimet sık istekte boş sayfa döndürüyor
        parcalar.append(p)
        bitis -= timedelta(days=parca_gun)
        time.sleep(12)
    df = pd.concat(parcalar).drop_duplicates("tarih", keep="first")
    return df[(df["tarih"] >= bas.isoformat()) & (df["tarih"] <= son.isoformat())].sort_values("tarih")


if __name__ == "__main__":
    bugun = date.today()
    print(mgm_tahmin(bugun).to_string(index=False))
    print(gozlemler(bugun, 10).to_string(index=False))


def met_tahmin(bugun: date, lat: float, lon: float) -> pd.DataFrame:
    """MET Norway (api.met.no) tahmini -> günlük en düşük/en yüksek/yağış (Türkiye saati, UTC+3).

    Sütunlar: tarih, met_en_dusuk, met_en_yuksek, met_yagis_mm
    Her 6 saatlik blok kendi en düşük/en yüksek değerini taşır; yağış blokların toplamıdır.
    Günün tamamı kapsanmayan günler (ilk ve son gün) atlanır.
    """
    r = requests.get("https://api.met.no/weatherapi/locationforecast/2.0/complete",
                     params={"lat": round(lat, 4), "lon": round(lon, 4)},
                     headers={"User-Agent": "hava-tahmini-proje/1.0"}, timeout=40)
    r.raise_for_status()
    # 6 saatlik bloklar: [başlangıç, başlangıç+6s) yerel saatle
    bloklar = {}
    for x in r.json()["properties"]["timeseries"]:
        d6 = x["data"].get("next_6_hours")
        if not d6 or "air_temperature_max" not in d6["details"]:
            continue
        bas = pd.Timestamp(x["time"]).tz_convert(None) + pd.Timedelta(hours=3)
        bloklar[bas] = d6["details"]
    # Bir gün = o günün 00:00'ından önceki 21:00 bloğu + 03, 09, 15 blokları (yaklaşık 21:00-21:00, tmax/tmin'i doğru yakalar)
    gunler = {}
    for bas, d in bloklar.items():
        if bas.hour % 6 == 3:  # MET blokları UTC 00/06/12/18 -> yerel 03/09/15/21 başlar
            gunler.setdefault((bas + pd.Timedelta(hours=3)).date(), {})[bas.hour] = d
    satirlar = []
    for g, b in sorted(gunler.items()):
        if len(b) < 4 or g <= bugun:
            continue
        satirlar.append({"tarih": g.isoformat(),
                         "met_en_dusuk": min(v["air_temperature_min"] for v in b.values()),
                         "met_en_yuksek": max(v["air_temperature_max"] for v in b.values()),
                         "met_yagis_mm": round(sum(v["precipitation_amount"] for v in b.values()), 1)})
    return pd.DataFrame(satirlar, columns=["tarih", "met_en_dusuk", "met_en_yuksek", "met_yagis_mm"])
