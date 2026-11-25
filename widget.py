"""Masaüstü hava widget'ı (Windows). Yarın + sonraki 5 gün, web/ileri.json'dan okunur.

Çalıştırma: Hava_Widget.bat (konsol penceresi açmaz)  veya  python widget.py
Kullanım : sürükleyerek taşıyın; sağ tık -> şehir seç, yenile, her zaman üstte, kapat.
Veriyi günlük görev (gunluk.py) günceller; widget dosya değişince kendini yeniler.
"""
import json
import threading
import time
import tkinter as tk
import urllib.request
from datetime import datetime
from pathlib import Path

from sehirler import SEHIRLER
from tur import AD, kod_ad, tur_bul


def KOD_TUR(k):
    return tur_bul({"hava_kodu": k})

KLASOR = Path(__file__).parent
VERI = KLASOR / "web" / "ileri.json"
AYAR = KLASOR / "widget_ayar.json"
SEHIR_AD = {"ankara": "Ankara", "istanbul": "İstanbul", "izmir": "İzmir", "konya": "Konya"}
GUN = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
GUN_UZUN = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

BG, KART, YAZI, SOLUK, CIZGI = "#161b22", "#1f2630", "#e8ecf1", "#8f9bab", "#2c3440"
GUNES, BULUT, BULUT2, DAMLA, KAR, SIMSEK = "#f5b335", "#aab4c2", "#7d8898", "#4aa3ff", "#dce8f5", "#f5c542"


def ikon(c, x, y, s, tur):
    """Canvas üzerine s piksellik ikon çizer; (x, y) sol üst köşe."""
    def daire(cx, cy, r, **k):
        c.create_oval(x + cx * s - r * s, y + cy * s - r * s, x + cx * s + r * s, y + cy * s + r * s, **k)

    def gunes(cx, cy, r):
        import math
        for i in range(8):
            a = i * math.pi / 4
            c.create_line(x + (cx + math.cos(a) * (r + .1)) * s, y + (cy + math.sin(a) * (r + .1)) * s,
                          x + (cx + math.cos(a) * (r + .26)) * s, y + (cy + math.sin(a) * (r + .26)) * s,
                          fill=GUNES, width=max(2, s // 14), capstyle="round")
        daire(cx, cy, r, fill=GUNES, outline="")

    def bulut(dx=0, dy=0, renk=BULUT):
        daire(.36 + dx, .58 + dy, .17, fill=renk, outline="")
        daire(.56 + dx, .46 + dy, .22, fill=renk, outline="")
        daire(.74 + dx, .6 + dy, .16, fill=renk, outline="")
        c.create_rectangle(x + (.36 + dx) * s, y + (.58 + dy) * s, x + (.74 + dx) * s, y + (.76 + dy) * s, fill=renk, outline="")
        daire(.36 + dx, .59 + dy, .17, fill=renk, outline="")
        daire(.74 + dx, .6 + dy, .16, fill=renk, outline="")

    if tur == "gunes":
        gunes(.5, .5, .2)
    elif tur == "az-bulut":
        gunes(.4, .38, .13)
        bulut(.05, .02)
    elif tur == "parcali":
        gunes(.4, .4, .12)
        bulut(.05, .04, BULUT)
    elif tur == "bulut":
        bulut(0, -.04)
    elif tur in ("yagmur", "kar", "firtina"):
        bulut(0, -.12, BULUT2)
        if tur == "yagmur":
            for dx in (.36, .52, .68):
                c.create_line(x + dx * s, y + .74 * s, x + (dx - .05) * s, y + .88 * s, fill=DAMLA, width=max(2, s // 14), capstyle="round")
        elif tur == "kar":
            for dx in (.36, .52, .68):
                daire(dx, .82, .035, fill=KAR, outline="")
        else:
            c.create_polygon([x + .54 * s, y + .66 * s, x + .44 * s, y + .82 * s, x + .53 * s, y + .82 * s,
                              x + .49 * s, y + .96 * s, x + .64 * s, y + .76 * s, x + .55 * s, y + .76 * s], fill=SIMSEK, outline="")
    elif tur == "sis":
        for i, (a, b) in enumerate([(.2, .8), (.12, .88), (.24, .76), (.16, .84)]):
            c.create_line(x + a * s, y + (.3 + i * .14) * s, x + b * s, y + (.3 + i * .14) * s, fill=BULUT, width=max(2, s // 12), capstyle="round")


class Widget:
    def __init__(self):
        self.k = tk.Tk()
        self.k.overrideredirect(True)
        self.k.configure(bg=BG)
        self.ayar = {"sehir": "ankara", "ustte": True, "x": 80, "y": 80}
        try:
            self.ayar.update(json.loads(AYAR.read_text(encoding="utf-8")))
        except Exception:
            pass
        self.k.geometry(f"+{self.ayar['x']}+{self.ayar['y']}")
        self.k.attributes("-topmost", bool(self.ayar["ustte"]))
        self.k.attributes("-alpha", 0.97)
        self.c = tk.Canvas(self.k, width=340, height=282, bg=BG, highlightthickness=1, highlightbackground=CIZGI)
        self.c.pack()
        self.veri, self.mtime = [], 0
        self.anlik = {}  # şehir -> (alınma zamanı, sıcaklık, hava kodu)
        self.c.bind("<ButtonPress-1>", self.basla)
        self.c.bind("<B1-Motion>", self.surukle)
        self.c.bind("<ButtonRelease-1>", lambda e: self.kaydet())
        self.c.bind("<Button-3>", self.menu)
        self.c.bind("<Double-Button-1>", lambda e: self.yukle(zorla=True))
        self.yukle(zorla=True)
        self.anlik_cek()
        self.k.after(60_000, self.kontrol)

    def kaydet(self):
        self.ayar["x"], self.ayar["y"] = self.k.winfo_x(), self.k.winfo_y()
        try:
            AYAR.write_text(json.dumps(self.ayar), encoding="utf-8")
        except OSError:
            pass

    def basla(self, e):
        self.ox, self.oy = e.x, e.y

    def surukle(self, e):
        self.k.geometry(f"+{self.k.winfo_x() + e.x - self.ox}+{self.k.winfo_y() + e.y - self.oy}")

    def menu(self, e):
        m = tk.Menu(self.k, tearoff=0)
        sehirler = sorted({r["sehir"] for r in self.veri}) or ["ankara"]
        for s in sehirler:
            m.add_command(label=("● " if s == self.ayar["sehir"] else "   ") + SEHIR_AD.get(s, s.title()), command=lambda s=s: self.sehir_sec(s))
        m.add_separator()
        m.add_command(label="Yenile", command=lambda: self.yukle(zorla=True))
        m.add_command(label=("✓ " if self.ayar["ustte"] else "   ") + "Her zaman üstte", command=self.ustte)
        m.add_separator()
        m.add_command(label="Kapat", command=self.k.destroy)
        m.tk_popup(e.x_root, e.y_root)

    def sehir_sec(self, s):
        self.ayar["sehir"] = s
        self.kaydet()
        self.ciz()
        self.anlik_cek()

    def anlik_cek(self, zorla=False):
        """Seçili şehrin şu anki havasını Open-Meteo'dan arka planda çeker (10 dk önbellek)."""
        s = self.ayar["sehir"]
        if s not in SEHIRLER or (not zorla and s in self.anlik and time.time() - self.anlik[s][0] < 600):
            return

        def is_():
            try:
                b = SEHIRLER[s]
                u = (f"https://api.open-meteo.com/v1/forecast?latitude={b['lat']}&longitude={b['lon']}"
                     "&current=temperature_2m,apparent_temperature,weather_code&timezone=Europe%2FIstanbul")
                with urllib.request.urlopen(u, timeout=10) as r:
                    c = json.loads(r.read().decode("utf-8"))["current"]
                self.anlik[s] = (time.time(), c["temperature_2m"], c["weather_code"], c.get("apparent_temperature"))
            except Exception:
                pass
        threading.Thread(target=is_, daemon=True).start()
        for ms in (2500, 6000):
            self.k.after(ms, self.ciz)

    def ustte(self):
        self.ayar["ustte"] = not self.ayar["ustte"]
        self.k.attributes("-topmost", self.ayar["ustte"])
        self.kaydet()

    def kontrol(self):
        self.anlik_cek()
        self.yukle()
        self.k.after(60_000, self.kontrol)

    def yukle(self, zorla=False):
        try:
            m = VERI.stat().st_mtime
            if zorla or m != self.mtime:
                self.veri = json.loads(VERI.read_text(encoding="utf-8"))
                self.mtime = m
        except Exception:
            self.veri = self.veri or []
        self.ciz()

    def ciz(self):
        c = self.c
        c.delete("all")
        s = self.ayar["sehir"]
        satirlar = sorted([r for r in self.veri if r["sehir"] == s], key=lambda r: r["tarih"])
        sid = c.create_text(16, 18, text=SEHIR_AD.get(s, s.title()), anchor="w", fill=YAZI, font=("Segoe UI Semibold", 12))
        if not satirlar:
            c.create_text(170, 130, text="Bu şehir için tahmin yok.\nGünlük güncellemeyi bekleyin.", fill=SOLUK, font=("Segoe UI", 10), justify="center")
            return
        yas = (time.time() - self.mtime) / 3600
        if yas > 36:
            guncel = "tahmin eski: " + datetime.fromtimestamp(self.mtime).strftime("%d.%m %H:%M")
            renk = "#e0a106"
        else:
            guncel = "tahmin " + datetime.fromtimestamp(self.mtime).strftime("%H:%M")
            renk = SOLUK
        sol = c.bbox(sid)[2] + 8
        c.create_text(sol, 20, text=guncel, anchor="w", fill=renk, font=("Segoe UI", 8))
        an = self.anlik.get(s)
        if an and time.time() - an[0] < 3 * 3600:
            tur = KOD_TUR(an[2])
            ikon(c, 14, 34, 84, tur)
            c.create_text(104, 52, text="Şu an", anchor="w", fill=SOLUK, font=("Segoe UI", 9))
            c.create_text(104, 90, text=f"{round(an[1])}°", anchor="w", fill=YAZI, font=("Segoe UI Semibold", 34))
            c.create_text(104, 128, text=kod_ad(an[2]), anchor="w", fill=YAZI, font=("Segoe UI", 10))
            if an[3] is not None:
                c.create_text(104, 146, text=f"hissedilen {round(an[3])}°", anchor="w", fill=SOLUK, font=("Segoe UI", 9))
        else:
            c.create_text(104, 52, text="Şu an", anchor="w", fill=SOLUK, font=("Segoe UI", 9))
            c.create_text(104, 90, text="—", anchor="w", fill=SOLUK, font=("Segoe UI Semibold", 34))
            c.create_text(104, 128, text="Şu anki hava alınamadı", anchor="w", fill=SOLUK, font=("Segoe UI", 9))
        y0 = satirlar[0]
        c.create_text(324, 52, text="Yarın için", anchor="e", fill=SOLUK, font=("Segoe UI", 9))
        c.create_text(324, 80, text=f"USTA  {round(y0['en_yuksek'])}° / {round(y0['en_dusuk'])}°", anchor="e", fill=YAZI, font=("Segoe UI Semibold", 11))
        if y0.get("mgm_en_yuksek") is not None:
            c.create_text(324, 102, text=f"MGM  {round(y0['mgm_en_yuksek'])}° / {round(y0['mgm_en_dusuk'])}°", anchor="e", fill=YAZI, font=("Segoe UI Semibold", 11))
        if y0.get("yagis_olasiligi") is not None:
            c.create_text(324, 124, text=f"yağış %{round(y0['yagis_olasiligi'])}", anchor="e", fill=SOLUK, font=("Segoe UI", 9))
        c.create_line(16, 168, 324, 168, fill=CIZGI)
        for i, r in enumerate(satirlar[:6]):
            cx = 16 + i * 51.3
            d = datetime.strptime(r["tarih"], "%Y-%m-%d").weekday()
            c.create_text(cx + 25, 182, text="Yarın" if i == 0 else GUN[d], fill=YAZI if i == 0 else SOLUK,
                          font=("Segoe UI Semibold" if i == 0 else "Segoe UI", 9))
            ikon(c, cx + 9, 192, 32, tur_bul(r))
            c.create_text(cx + 25, 238, text=f"{round(r['en_yuksek'])}°", fill=YAZI, font=("Segoe UI Semibold", 11))
            c.create_text(cx + 25, 253, text=f"{round(r['en_dusuk'])}°", fill=SOLUK, font=("Segoe UI", 9))
            p = r.get("yagis_olasiligi")
            if p is not None and p >= 30:
                c.create_text(cx + 25, 270, text=f"💧{round(p)}%", fill=DAMLA, font=("Segoe UI", 8))


if __name__ == "__main__":
    Widget().k.mainloop()
