"""RF Gözcü özellik çıkarma.

Uçağın BİLDİRDİĞİ konumdan modelin girdilerini hesaplar. Bu dosya hem
eğitimde (bilgisayar) hem Pi'deki çıkarım servisinde kullanılır; iki tarafta
formül farklı olursa model sessizce bozulur, o yüzden yalnızca numpy ve
pyyaml'a bağımlıdır.

Özellikler (sırası OZELLIK_ADLARI'nda sabit):
  log10_mesafe_km, sin_azimut, cos_azimut, yukseklik_acisi_deg, irtifa_km,
  kategori (one-hot: A1..A7, diger)
"""
from pathlib import Path

import numpy as np
import yaml

DUNYA_YARICAPI_M = 6_371_000.0
FT_M = 0.3048

KATEGORILER = ["A1", "A2", "A3", "A4", "A5", "A6", "A7"]   # geri kalanlar "diger"
OZELLIK_ADLARI = (["log10_mesafe_km", "sin_azimut", "cos_azimut",
                   "yukseklik_acisi_deg", "irtifa_km"]
                  + [f"kat_{k}" for k in KATEGORILER] + ["kat_diger"])


def istasyon_oku(yol):
    """İstasyon bilgisini okur. Pi'deki config.yaml'ın kopyası da olabilir
    (içindeki `istasyon:` bloğu kullanılır), yalnızca o bloğu içeren bir dosya da.

    Dönen sözlük: enlem, boylam, anten_rakim_m (deniz seviyesine göre).
    Değerler hiçbir zaman ekrana yazdırılmaz.
    """
    ayar = yaml.safe_load(Path(yol).read_text(encoding="utf-8-sig"))
    ist = ayar.get("istasyon", ayar)
    eksik = [k for k in ("enlem", "boylam", "zemin_rakimi_m", "anten_yerden_yukseklik_m")
             if ist.get(k) is None]
    if eksik:
        raise ValueError(f"{yol} içinde eksik istasyon alanları: {', '.join(eksik)}")
    if float(ist["enlem"]) == 0.0 and float(ist["boylam"]) == 0.0:
        raise ValueError(f"{yol}: istasyon koordinatları hâlâ örnek değer (0, 0)")
    return {
        "enlem": float(ist["enlem"]),
        "boylam": float(ist["boylam"]),
        "anten_rakim_m": float(ist["zemin_rakimi_m"]) + float(ist["anten_yerden_yukseklik_m"]),
    }


def mesafe_azimut(enlem0, boylam0, enlem, boylam):
    """Haversine yer mesafesi (m) ve istasyondan uçağa ilk yön açısı (derece, kuzey=0)."""
    f0, l0 = np.radians(enlem0), np.radians(boylam0)
    f, l = np.radians(np.asarray(enlem, float)), np.radians(np.asarray(boylam, float))
    df, dl = f - f0, l - l0
    a = np.sin(df / 2) ** 2 + np.cos(f0) * np.cos(f) * np.sin(dl / 2) ** 2
    mesafe = 2 * DUNYA_YARICAPI_M * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    y = np.sin(dl) * np.cos(f)
    x = np.cos(f0) * np.sin(f) - np.sin(f0) * np.cos(f) * np.cos(dl)
    azimut = np.degrees(np.arctan2(y, x)) % 360
    return mesafe, azimut


def yukseklik_acisi(mesafe_m, irtifa_m, anten_rakim_m):
    """atan((h_ucak - h_anten - d²/2R) / d), derece. d²/2R dünyanın eğriliği."""
    d = np.maximum(np.asarray(mesafe_m, float), 1.0)
    return np.degrees(np.arctan((irtifa_m - anten_rakim_m - d ** 2 / (2 * DUNYA_YARICAPI_M)) / d))


def kaydir(enlem, boylam, km, yon_deg):
    """Bir noktayı verilen yönde `km` kadar taşır (sahte konum üretimi için)."""
    f1, l1 = np.radians(np.asarray(enlem, float)), np.radians(np.asarray(boylam, float))
    t = np.radians(np.asarray(yon_deg, float))
    delta = np.asarray(km, float) * 1000.0 / DUNYA_YARICAPI_M
    f2 = np.arcsin(np.sin(f1) * np.cos(delta) + np.cos(f1) * np.sin(delta) * np.cos(t))
    l2 = l1 + np.arctan2(np.sin(t) * np.sin(delta) * np.cos(f1),
                         np.cos(delta) - np.sin(f1) * np.sin(f2))
    return np.degrees(f2), (np.degrees(l2) + 540) % 360 - 180


def irtifa_sec(irtifa_geo_ft, irtifa_baro_ft):
    """Geometrik irtifa varsa onu, yoksa barometrik irtifayı metre olarak verir."""
    geo = np.asarray(irtifa_geo_ft, float)
    baro = np.asarray(irtifa_baro_ft, float)
    return np.where(np.isfinite(geo), geo, baro) * FT_M


def ozellik_matrisi(enlem, boylam, irtifa_m, kategori, istasyon):
    """Modelin girdi matrisini (n, len(OZELLIK_ADLARI)) ve mesafeyi (m) döndürür."""
    mesafe, azimut = mesafe_azimut(istasyon["enlem"], istasyon["boylam"], enlem, boylam)
    irtifa_m = np.asarray(irtifa_m, float)
    az = np.radians(azimut)
    kat = np.asarray(kategori, dtype=object)
    sutunlar = [
        np.log10(np.maximum(mesafe, 100.0) / 1000.0),
        np.sin(az),
        np.cos(az),
        yukseklik_acisi(mesafe, irtifa_m, istasyon["anten_rakim_m"]),
        irtifa_m / 1000.0,
    ]
    bilinen = np.isin(kat, KATEGORILER)
    for k in KATEGORILER:
        sutunlar.append((kat == k).astype(float))
    sutunlar.append((~bilinen).astype(float))
    return np.column_stack(sutunlar).astype(np.float32), mesafe
