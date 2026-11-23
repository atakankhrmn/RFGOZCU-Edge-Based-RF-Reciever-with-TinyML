"""Kaydedicinin günlük CSV dosyalarını okur, temizler, özellikleri ekler.

Kullanım (özet rapor için):
    .venv\\Scripts\\python model\\veri_oku.py --veri logs --istasyon model\\istasyon.yaml
"""
import argparse
import gzip
import io
from pathlib import Path

import numpy as np
import pandas as pd

import ozellikler as oz

# Mesafe bu değerin üstündeyse bildirilen konum (ya da çözümleme) hatalı kabul edilir.
# 1090 MHz'de 11 km irtifadaki uçak için radyo ufku ~ 400 km.
MAKS_MESAFE_KM = 450
# Bir uçağın iki satırı arasında bu kadar boşluk varsa yeni bir "iz" (geçiş) başlar.
IZ_BOSLUGU_S = 300
MIN_RSSI_DBFS = -49.0


def dosyalari_bul(klasor):
    klasor = Path(klasor)
    dosyalar = sorted(list(klasor.glob("*.csv.gz")) + list(klasor.glob("*.csv")))
    # aynı gün hem .csv hem .csv.gz olarak varsa .gz'yi kullan
    gunler = {}
    for d in dosyalar:
        gun = d.name[:10]
        if gun not in gunler or d.suffix == ".gz":
            gunler[gun] = d
    return [gunler[g] for g in sorted(gunler)]


def oku(klasor, istasyon, oturum=1, min_nic=7):
    """Bütün günleri okur; filtrelenmiş ve özellikleri eklenmiş tabloyu döndürür.

    min_nic: eğitimde konumu güvenilir olmayan uçakları dışarıda bırakmak için.
    None verilirse NIC filtresi uygulanmaz (değerlendirmede düşük NIC'li
    uçakları ayrıca incelemek için).
    """
    dosyalar = dosyalari_bul(klasor)
    if not dosyalar:
        raise FileNotFoundError(f"{klasor} içinde .csv / .csv.gz dosyası yok")
    parcalar = []
    for d in dosyalar:
        ham = gzip.open(d).read() if d.suffix == ".gz" else d.read_bytes()
        # elektrik kesintisinde dosyaya NUL baytlar düşebiliyor
        ham = ham.replace(b"\x00", b"")
        t = pd.read_csv(io.BytesIO(ham), dtype={"ucak_id": str, "kategori": str, "kazanc_db": str},
                        na_values=[""], keep_default_na=False, on_bad_lines="skip")
        t["kaynak_dosya"] = d.name
        parcalar.append(t)
    df = pd.concat(parcalar, ignore_index=True)
    sayac = {"ham": len(df)}

    df["zaman"] = pd.to_datetime(df["zaman_utc"].astype(str).str.strip(), utc=True,
                                 format="ISO8601", errors="coerce")
    df = df.dropna(subset=["zaman"])
    sayac["zaman okunabilir"] = len(df)
    df["gun"] = df["zaman"].dt.strftime("%Y-%m-%d")
    for s in ["enlem", "boylam", "irtifa_baro_ft", "irtifa_geo_ft", "rssi_dbfs",
              "nic", "nac_p", "yerde", "oturum"]:
        df[s] = pd.to_numeric(df[s], errors="coerce")
    df["kategori"] = df["kategori"].fillna("").str.strip()

    df = df[df["oturum"] == oturum]
    sayac[f"oturum=={oturum}"] = len(df)
    df = df[df["yerde"] == 0]
    sayac["havada"] = len(df)
    df = df.dropna(subset=["enlem", "boylam", "rssi_dbfs"])
    # -49.5 dBFS readsb'nin alt sınırı; gerçek ölçüm değil (gerçek veride -36 ile -49.5 arası boş)
    df = df[df["rssi_dbfs"] > MIN_RSSI_DBFS]
    df["irtifa_m"] = oz.irtifa_sec(df["irtifa_geo_ft"], df["irtifa_baro_ft"])
    df = df[np.isfinite(df["irtifa_m"])]
    sayac["konum+irtifa+rssi var"] = len(df)
    if min_nic is not None:
        df = df[df["nic"] >= min_nic]
        sayac[f"nic>={min_nic}"] = len(df)

    X, mesafe = oz.ozellik_matrisi(df["enlem"].to_numpy(), df["boylam"].to_numpy(),
                                   df["irtifa_m"].to_numpy(), df["kategori"].to_numpy(),
                                   istasyon)
    df = df.copy()
    df["mesafe_km"] = mesafe / 1000.0
    for i, ad in enumerate(oz.OZELLIK_ADLARI):
        df[ad] = X[:, i]
    df = df[df["mesafe_km"] <= MAKS_MESAFE_KM]
    sayac[f"mesafe<={MAKS_MESAFE_KM} km"] = len(df)

    df = df.sort_values(["ucak_id", "zaman"]).reset_index(drop=True)
    yeni_iz = (df["ucak_id"] != df["ucak_id"].shift()) | \
              (df["zaman"].diff().dt.total_seconds() > IZ_BOSLUGU_S)
    df["iz"] = yeni_iz.cumsum()
    return df, sayac


def gune_gore_ayir(df, dogrulama_gun=None, test_gun=None):
    """Günleri zaman sırasıyla eğitim / doğrulama / test olarak ayırır.

    Rastgele satır ayırma yapılmaz: aynı uçağın 5 sn arayla yazılmış satırları
    iki tarafa düşüp sonucu olduğundan iyi gösterir.
    """
    gunler = sorted(df["gun"].unique())
    n = len(gunler)
    if n < 3:
        raise ValueError(f"Güne göre ayırmak için en az 3 gün gerekli, {n} gün var")
    test_gun = test_gun or max(1, round(n * 0.15))
    dogrulama_gun = dogrulama_gun or max(1, round(n * 0.15))
    egitim = gunler[: n - test_gun - dogrulama_gun]
    dogrulama = gunler[n - test_gun - dogrulama_gun: n - test_gun]
    test = gunler[n - test_gun:]
    return {"egitim": egitim, "dogrulama": dogrulama, "test": test}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--veri", default="logs")
    p.add_argument("--istasyon", default="model/istasyon.yaml")
    a = p.parse_args()
    df, sayac = oku(a.veri, oz.istasyon_oku(a.istasyon))
    print("Filtre adımları (satır):")
    for k, v in sayac.items():
        print(f"  {k:<24} {v:>10,}")
    print(f"\nGün sayısı: {df['gun'].nunique()}  |  farklı uçak: {df['ucak_id'].nunique():,}"
          f"  |  iz: {df['iz'].nunique():,}")
    print(df.groupby("gun").size().rename("satir").to_string())
    print("\nRSSI (dBFS):", df["rssi_dbfs"].describe().round(2).to_dict())
    print("Mesafe (km):", df["mesafe_km"].describe().round(1).to_dict())


if __name__ == "__main__":
    main()
