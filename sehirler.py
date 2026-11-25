"""Sistemin desteklediği şehirler.

il        : MGM sayfasındaki il adı
istasyon  : gerçekleşen ölçümler için WMO istasyon numarası (Ogimet / Meteostat)
lat, lon  : MGM'nin il merkezi tahmin noktası (model tahminleri bu noktadan alınır)
"""
SEHIRLER = {
    "ankara": {"ad": "Ankara", "il": "Ankara", "istasyon": "17130", "lat": 39.9727, "lon": 32.8637,
               "istasyon_adi": "Ankara Merkez (MGM'nin il merkezi istasyonu)"},
    "istanbul": {"ad": "İstanbul", "il": "İstanbul", "istasyon": "17060", "lat": 40.9819, "lon": 28.8208,
                 "istasyon_adi": "Atatürk Havalimanı (MGM'nin Florya'daki merkez noktasına 1,7 km)"},
    "izmir": {"ad": "İzmir", "il": "İzmir", "istasyon": "17220", "lat": 38.4049, "lon": 27.1895,
              "istasyon_adi": "İzmir Bölge (MGM'nin merkez noktasına 3,7 km)"},
    "konya": {"ad": "Konya", "il": "Konya", "istasyon": "17244", "lat": 37.8687, "lon": 32.4713,
              "istasyon_adi": "Konya Bölge (MGM'nin merkez noktasına 13 km)"},
}
