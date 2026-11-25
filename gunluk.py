"""Her gün çalışan ana betik (çok şehirli).

Her şehir için:
1. MGM'nin 5 günlük tahminini çeker
2. İstasyonun son 30 günlük ölçümlerini günceller (Ogimet)
3. Bizim sistemle 1-7 gün düzeltilmiş, 8-14 gün model ortalaması tahmin üretir (+ ECMWF hava kodu)
4. Kayıtlı geçmiş tahminleri gerçekleşenle puanlar (karne)
Sonra arayüz için web/ altına ileri.json, gecmis.csv, karne.json, iklim.json, test.json yazar.

Kullanım: python gunluk.py [YYYY-MM-DD]
"""
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

import kaynaklar
import sistem
from sehirler import SEHIRLER

KLASOR = Path(__file__).parent
VERI = KLASOR / "veri"
WEB = KLASOR / "web"
WEB.mkdir(exist_ok=True)
(VERI / "mgm").mkdir(exist_ok=True)
KAYIT = KLASOR / "canli_tahminler_v3.csv"
TEST_DOSYA = VERI / "test_sonuclari.json"
YAGIS_KELIME = "Yağmur|Sağanak|Kar|Yağış|Gök Gürültü|Karla|Dolu|Çisenti"


def temiz(x):
    if x is None:
        return None
    if isinstance(x, (float, np.floating)):
        return None if np.isnan(x) else round(float(x), 1)
    if isinstance(x, np.integer):
        return int(x)
    return x


def gozlem_guncelle(sehir, bugun):
    ist = SEHIRLER[sehir]["istasyon"]
    yol = VERI / f"gozlem_{ist}.csv"
    yeni = kaynaklar.gozlemler(bugun, 30, ist)
    if yol.exists():
        eski = pd.read_csv(yol)
        yeni = yeni.set_index("tarih").combine_first(eski.set_index("tarih")).reset_index()
    yeni.sort_values("tarih").to_csv(yol, index=False)


def kayit_yukle():
    if KAYIT.exists():
        return pd.read_csv(KAYIT)
    eski = KLASOR / "canli_tahminler_v2.csv"  # yalnız Ankara'lı ilk kayıtları taşı
    if eski.exists():
        e = pd.read_csv(eski)
        return pd.DataFrame({"sehir": "ankara", "tahmin_tarihi": e["tahmin_tarihi"], "tarih": e["tarih"],
                             "bizim_tmax": e["bizim_tmax"], "bizim_tmin": e["bizim_tmin"], "bizim_yagis": e["bizim_yagis_%"],
                             "mgm_en_yuksek": e["mgm_en_yuksek"], "mgm_en_dusuk": e["mgm_en_dusuk"], "mgm_hadise": e["mgm_hadise"]})
    return pd.DataFrame()


def puanla(kayit, sehir, obs):
    g = obs.reset_index().assign(tarih=lambda d: d["tarih"].dt.strftime("%Y-%m-%d"))
    t = kayit[kayit["sehir"] == sehir].merge(g, on="tarih", how="inner")
    for c in ("met_en_yuksek", "met_en_dusuk", "met_yagis_mm"):
        if c not in t.columns:
            t[c] = np.nan
    t["kac_gun_once"] = (pd.to_datetime(t["tarih"]) - pd.to_datetime(t["tahmin_tarihi"])).dt.days
    t["mgm_yagis_var"] = t["mgm_hadise"].fillna("").str.contains(YAGIS_KELIME)
    sonuc = []
    for n, k in t.groupby("kac_gun_once"):
        satir = {"sehir": sehir, "kac_gun_once": int(n)}
        for ad, biz, mgm, ger in (("en_yuksek", "bizim_tmax", "mgm_en_yuksek", "en_yuksek"),
                                  ("en_dusuk", "bizim_tmin", "mgm_en_dusuk", "en_dusuk")):
            x = k.dropna(subset=[biz, mgm, ger])
            satir[f"{ad}_gun"] = len(x)
            satir[f"{ad}_bizim_hata"] = round(float((x[biz] - x[ger]).abs().mean()), 2) if len(x) else None
            satir[f"{ad}_mgm_hata"] = round(float((x[mgm] - x[ger]).abs().mean()), 2) if len(x) else None
            met = "met_en_yuksek" if ad == "en_yuksek" else "met_en_dusuk"
            y = k.dropna(subset=[met, ger])
            satir[f"{ad}_met_hata"] = round(float((y[met] - y[ger]).abs().mean()), 2) if len(y) else None
            satir[f"{ad}_met_gun"] = len(y)
        x = k.dropna(subset=["yagis_mm", "bizim_yagis"])
        x = x[x["mgm_hadise"].notna()]
        var = x["yagis_mm"] >= 1.0
        satir["yagis_gun"] = len(x)
        satir["yagis_bizim_dogru_%"] = round(100 * float(((x["bizim_yagis"] >= 50) == var).mean()), 1) if len(x) else None
        z = x.dropna(subset=["met_yagis_mm"])
        satir["yagis_met_gun"] = len(z)
        satir["yagis_met_dogru_%"] = round(100 * float(((z["met_yagis_mm"] >= 1.0) == (z["yagis_mm"] >= 1.0)).mean()), 1) if len(z) else None
        satir["yagis_mgm_dogru_%"] = round(100 * float((x["mgm_yagis_var"] == var).mean()), 1) if len(x) else None
        if satir["en_yuksek_gun"] or satir["yagis_gun"]:
            sonuc.append(satir)
    return sonuc, t


def gecmis_tablo(sehir, obs, eslesen):
    d = obs.loc["2003-01-01":].reset_index()
    d["tarih"] = d["tarih"].dt.strftime("%Y-%m-%d")
    bir = eslesen[eslesen["kac_gun_once"] == 1][["tarih", "bizim_tmax", "mgm_en_yuksek"]].rename(
        columns={"bizim_tmax": "bizim_en_yuksek_1gun_once", "mgm_en_yuksek": "mgm_en_yuksek_1gun_once"})
    d = d.merge(bir, on="tarih", how="left").dropna(subset=["en_yuksek", "en_dusuk"], how="all")
    d.insert(0, "sehir", sehir)
    return d


def hazirla(sehir, bugun):
    """Şehrin arşivleri eksikse tamamlamayı dener. Hazırsa True döner."""
    import veri_indir_sehirler as vi
    from veri_indir_modeller import indir
    b = SEHIRLER[sehir]
    klasor = VERI / "modeller" if sehir == "ankara" else VERI / "modeller" / sehir
    try:
        for m in sistem.MODELLER:
            if not (klasor / f"{m}.csv").exists():
                print(f"   {m} arşivi eksik, indiriliyor", flush=True)
                indir(m, sehir, b["lat"], b["lon"])
        vi.meteostat(b["istasyon"])
        if not (VERI / f"gozlem_{b['istasyon']}.csv").exists():
            vi.ogimet(b["istasyon"], bugun)
        return True
    except Exception as e:
        print(f"   {b['ad']} için arşiv tamamlanamadı, bugün atlanıyor: {e}", flush=True)
        return False


def test_sonuclari(sehirler, yenile=False):
    eski = json.loads(TEST_DOSYA.read_text(encoding="utf-8")) if TEST_DOSYA.exists() else []
    if not yenile and {r["sehir"] for r in eski} >= set(sehirler):
        return [r for r in eski if r["sehir"] in sehirler]
    satirlar = [r for r in eski if r["sehir"] in sehirler and not yenile]
    for s in [s for s in sehirler if yenile or s not in {r["sehir"] for r in eski}]:
        print(f"  geçmiş test: {s}", flush=True)
        satirlar += sistem.geriye_test(s)
    TEST_DOSYA.write_text(json.dumps(satirlar, ensure_ascii=False), encoding="utf-8")
    return satirlar


BUGUN_USTA = {}


def main():
    bugun = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    print(f"== {bugun}", flush=True)
    kayit = kayit_yukle()
    ileri, karne, gecmis, iklim = [], [], [], []
    basarili = []
    for s, b in SEHIRLER.items():
        print(f"-- {b['ad']}", flush=True)
        if not hazirla(s, bugun):
            continue
        try:
            gozlem_guncelle(s, bugun)
        except Exception as e:  # ölçüm güncellenemezse eski ölçümlerle devam
            print(f"   ölçümler güncellenemedi: {e}", flush=True)
        time.sleep(8)  # Ogimet'i yormamak için
        obs = sistem.gozlem(s)
        try:
            satirlar = sistem.canli_tahmin(s, bugun, obs)
            kodlar = sistem.hava_kodlari(s, bugun)
        except Exception as e:
            print(f"   {b['ad']} için tahmin alınamadı, bugün atlanıyor: {e}", flush=True)
            continue
        mgm_yol = VERI / "mgm" / f"{s}_{bugun.isoformat()}.csv"
        try:
            mgm = kaynaklar.mgm_tahmin(bugun, b["il"])
            mgm.to_csv(mgm_yol, index=False)
        except Exception as e:  # MGM okunamazsa bizim tahmin yine de yayınlanır
            print(f"   MGM okunamadı: {e}", flush=True)
            mgm = pd.read_csv(mgm_yol) if mgm_yol.exists() else pd.DataFrame(columns=["tarih", "mgm_en_dusuk", "mgm_en_yuksek", "mgm_hadise"])
        met_yol = VERI / "mgm" / f"met_{s}_{bugun.isoformat()}.csv"
        try:
            met = kaynaklar.met_tahmin(bugun, b["lat"], b["lon"])
            met.to_csv(met_yol, index=False)
        except Exception as e:  # MET Norway okunamazsa tahmin yine de yayınlanır
            print(f"   MET Norway okunamadı: {e}", flush=True)
            met = pd.read_csv(met_yol) if met_yol.exists() else pd.DataFrame(columns=["tarih", "met_en_dusuk", "met_en_yuksek", "met_yagis_mm"])
        mt = met.set_index("tarih")
        m = mgm.set_index("tarih")
        for r in satirlar:
            tr = mt.loc[r["tarih"]] if r["tarih"] in mt.index else None
            r["met_en_yuksek"] = temiz(tr["met_en_yuksek"]) if tr is not None else None
            r["met_en_dusuk"] = temiz(tr["met_en_dusuk"]) if tr is not None else None
            r["met_yagis_mm"] = temiz(tr["met_yagis_mm"]) if tr is not None else None
            r["hava_kodu"] = kodlar.get(r["tarih"])
            mr = m.loc[r["tarih"]] if r["tarih"] in m.index else None
            r["mgm_en_yuksek"] = temiz(mr["mgm_en_yuksek"]) if mr is not None else None
            r["mgm_en_dusuk"] = temiz(mr["mgm_en_dusuk"]) if mr is not None else None
            r["mgm_hadise"] = mr["mgm_hadise"] if mr is not None and isinstance(mr["mgm_hadise"], str) else None
            if r["mgm_en_yuksek"] is not None:
                r["tur"] = "Bizim sistem ve MGM"
        ileri += satirlar
        try:
            BUGUN_USTA[s] = sistem.bugun_tahmin(s, bugun, obs)
        except Exception as e:
            print(f"   bugün tahmini üretilemedi: {e}", flush=True)
        yeni_kayit = pd.DataFrame([{"sehir": s, "tahmin_tarihi": bugun.isoformat(), "tarih": r["tarih"],
                                    "bizim_tmax": r["en_yuksek"], "bizim_tmin": r["en_dusuk"], "bizim_yagis": r["yagis_olasiligi"],
                                    "mgm_en_yuksek": r["mgm_en_yuksek"], "mgm_en_dusuk": r["mgm_en_dusuk"], "mgm_hadise": r["mgm_hadise"],
                                    "met_en_yuksek": r["met_en_yuksek"], "met_en_dusuk": r["met_en_dusuk"], "met_yagis_mm": r["met_yagis_mm"]}
                                   for r in satirlar if r["kac_gun_sonra"] <= 7])
        if len(kayit):
            kayit = kayit[~((kayit["sehir"] == s) & (kayit["tahmin_tarihi"] == bugun.isoformat()))]
        kayit = pd.concat([kayit, yeni_kayit], ignore_index=True)
        k, eslesen = puanla(kayit, s, obs)
        karne += k
        gecmis.append(gecmis_tablo(s, obs, eslesen))
        iklim += sistem.iklim_tablosu(s, bugun, obs)
        yarin = satirlar[0]
        print(f"   yarın: {yarin['en_dusuk']}°/{yarin['en_yuksek']}° (MGM {yarin['mgm_en_dusuk']}/{yarin['mgm_en_yuksek']}), "
              f"{len(satirlar)} gün tahmin, {len(k)} karne satırı", flush=True)
        basarili.append(s)
    if not basarili:
        raise SystemExit("Hiçbir şehir için tahmin üretilemedi; panel güncellenmemeli.")
    kayit.to_csv(KAYIT, index=False)

    def yaz(ad, veri):
        (WEB / f"{ad}.json").write_text(json.dumps(veri, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    yaz("ileri", [{k: temiz(v) for k, v in r.items()} for r in ileri])
    yaz("karne", [{k: temiz(v) for k, v in r.items()} for r in karne])
    yaz("iklim", iklim)
    yaz("test", test_sonuclari(basarili))
    pd.concat(gecmis).to_csv(WEB / "gecmis.csv", index=False, float_format="%.1f")
    import yayin
    yayin.yukle([{k: temiz(v) for k, v in r.items()} for r in ileri], BUGUN_USTA)  # telefon widget'ı için
    import html_rapor
    html_rapor.main()  # Tahmin_Masasi.html (tek başına açılan sürüm)
    print(f"Yayınlanan şehirler: {', '.join(SEHIRLER[s]['ad'] for s in basarili)}", flush=True)
    print(f"web/ dosyaları yazıldı: {len(ileri)} ileri, {len(karne)} karne, {sum(len(g) for g in gecmis)} gözlem satırı "
          f"({datetime.now():%H:%M})", flush=True)


if __name__ == "__main__":
    main()
