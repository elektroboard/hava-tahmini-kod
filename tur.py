"""Tahmin satırından hava ikonu türü (widget ve yayın için ortak)."""
import re


def tur_bul(r):
    """Satırdan ikon türü: gunes, az-bulut, parcali, bulut, yagmur, kar, firtina, sis."""
    h = (r.get("mgm_hadise") or "").lower().replace("i̇", "i")
    tur = None
    if h:
        if re.search(r"gök gürültü|fırtına", h):
            tur = "firtina"
        elif re.search(r"kar|dolu", h):
            tur = "kar"
        elif re.search(r"yağmur|sağanak|çisenti|yağış", h):
            tur = "yagmur"
        elif "sis" in h or "pus" in h:
            tur = "sis"
        elif "az bulutlu" in h:
            tur = "az-bulut"
        elif "parçalı" in h:
            tur = "parcali"
        elif "bulutlu" in h:
            tur = "bulut"
        elif "açık" in h:
            tur = "gunes"
    if tur is None:
        k = r.get("hava_kodu")
        k = -1 if k is None else int(k)
        tur = ("gunes" if k == 0 else "az-bulut" if k == 1 else "parcali" if k == 2 else "bulut" if k == 3
               else "sis" if k in (45, 48) else "kar" if k in (71, 73, 75, 77, 85, 86)
               else "yagmur" if k in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82)
               else "firtina" if k >= 95 else "bulut")
    p = r.get("yagis_olasiligi")
    if p is not None and p >= 50 and tur in ("gunes", "az-bulut", "parcali", "bulut"):
        tur = "kar" if (r.get("en_yuksek") or 9) <= 1 else "yagmur"
    return tur


AD = {"gunes": "Açık", "az-bulut": "Az bulutlu", "parcali": "Parçalı bulutlu", "bulut": "Bulutlu",
      "yagmur": "Yağmurlu", "kar": "Karlı", "firtina": "Gök gürültülü", "sis": "Sisli"}


def kod_ad(k):
    """WMO hava kodu -> Türkçe kısa ad (anlık hava için)."""
    k = int(k)
    if k == 0:
        return "Açık"
    if k == 1:
        return "Az bulutlu"
    if k == 2:
        return "Parçalı bulutlu"
    if k == 3:
        return "Bulutlu"
    if k in (45, 48):
        return "Sisli"
    if k in (71, 73, 75, 77, 85, 86):
        return "Karlı"
    if k >= 95:
        return "Gök gürültülü"
    if k >= 80:
        return "Sağanak"
    if k >= 51:
        return "Yağmurlu"
    return "Bulutlu"
