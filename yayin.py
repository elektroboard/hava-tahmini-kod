"""Telefon widget'ı için küçük tahmin dosyasını (tahmin.json) GitHub Pages deposuna yükler.

Depo: https://github.com/elektroboard/hava-tahmini-veri  (yerel kopya: yayin/)
Adres: https://elektroboard.github.io/hava-tahmini-veri/tahmin.json
Dosyada yalnızca hava tahmini vardır, kişisel veri yoktur.
"""
import json
import subprocess
from datetime import datetime, date
import csv
from pathlib import Path

from sehirler import SEHIRLER
from tur import AD, tur_bul

KLASOR = Path(__file__).parent
DEPO = KLASOR / "yayin"


def mgm_bugun(sehir):
    """MGM'nin bugünkü en düşük/en yüksek değeri (kayıtlı MGM dosyasından)."""
    yol = KLASOR / "veri" / "mgm" / f"{sehir}_{date.today().isoformat()}.csv"
    try:
        for r in csv.DictReader(open(yol, encoding="utf-8")):
            if r["tarih"] == date.today().isoformat():
                return {"en_dusuk": round(float(r["mgm_en_dusuk"])), "en_yuksek": round(float(r["mgm_en_yuksek"]))}
    except Exception:
        pass
    return None


def dosya_olustur(ileri, bugun_usta=None):
    sehirler = {}
    for s, b in SEHIRLER.items():
        g = sorted([r for r in ileri if r.get("sehir") == s and r["kac_gun_sonra"] <= 7], key=lambda r: r["tarih"])
        if not g:
            continue
        sehirler[s] = {"ad": b["ad"], "lat": b["lat"], "lon": b["lon"], "mgm_bugun": mgm_bugun(s), "usta_bugun": (bugun_usta or {}).get(s), "gunler": [{
            "tarih": r["tarih"], "en_yuksek": round(r["en_yuksek"]), "en_dusuk": round(r["en_dusuk"]),
            "yagis": None if r.get("yagis_olasiligi") is None else round(r["yagis_olasiligi"]),
            "tur": tur_bul(r), "durum": r.get("mgm_hadise") or AD[tur_bul(r)],
            "mgm_en_yuksek": None if r.get("mgm_en_yuksek") is None else round(r["mgm_en_yuksek"]),
            "mgm_en_dusuk": None if r.get("mgm_en_dusuk") is None else round(r["mgm_en_dusuk"])} for r in g]}
    return {"guncelleme": datetime.now().astimezone().isoformat(timespec="minutes"), "sehirler": sehirler}


def yukle(ileri, bugun_usta=None):
    """tahmin.json'ı yazıp depoya gönderir. Başarısızlık ana akışı durdurmaz."""
    try:
        (DEPO / "tahmin.json").write_text(json.dumps(dosya_olustur(ileri, bugun_usta), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        (DEPO / ".nojekyll").touch()
        def git(*a):
            return subprocess.run(["git", "-C", str(DEPO), *a], capture_output=True, text=True, timeout=120)
        git("add", "-A")
        if not git("status", "--porcelain").stdout.strip():
            print("   yayın: değişiklik yok", flush=True)
            return True
        r = git("commit", "-m", f"Tahmin {datetime.now():%Y-%m-%d %H:%M}")
        r = git("push", "origin", "HEAD")
        print("   yayın:", "gönderildi" if r.returncode == 0 else "GÖNDERİLEMEDİ " + r.stderr[-200:], flush=True)
        return r.returncode == 0
    except Exception as e:
        print(f"   yayın başarısız: {e}", flush=True)
        return False
