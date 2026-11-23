"""Boru hattını gerçek veri olmadan denemek için SENTETİK veri üretir.

Bu veri gerçek ölçüm DEĞİLDİR; yalnızca kodun uçtan uca çalıştığını görmek
içindir. İstasyon koordinatları uydurmadır. Sonuçlar raporda kullanılmaz.

Sinyal modeli: log-mesafe yol kaybı + yöne bağlı gölge (bina) + yüksek
açıda dipol kör noktası + gürültü. MLP'nin baseline'ı yenmesi gereken
"formülün bilemediği" kısım yön ve açı terimleridir.

Kullanım:
    .venv\\Scripts\\python model\\sentetik.py --cikti output\\sentetik --gun 14
"""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

import ozellikler as oz

SAHTE_ISTASYON = {"enlem": 39.0, "boylam": 30.0,
                  "zemin_rakimi_m": 100.0, "anten_yerden_yukseklik_m": 7.0}
SUTUNLAR = ["zaman_utc", "ucak_id", "enlem", "boylam", "irtifa_baro_ft", "irtifa_geo_ft",
            "yerde", "hiz_kt", "yon_deg", "dikey_hiz_fpm", "rssi_dbfs", "nic", "nac_p",
            "kategori", "mesaj", "seen_pos_s", "kazanc_db", "oturum", "pi_sicaklik_c"]


def beklenen_rssi(mesafe_m, azimut, yukseklik_deg):
    d_km = np.maximum(mesafe_m / 1000.0, 0.5)
    rssi = 4.0 - 10 * 2.1 * np.log10(d_km)
    # güneybatı tarafında bina gölgesi (200°–260°), kenarları yumuşak
    rssi -= 9.0 * np.exp(-((((azimut - 230) + 180) % 360 - 180) / 25.0) ** 2)
    # kuzeyde hafif tepe etkisi
    rssi -= 3.0 * np.exp(-((((azimut - 10) + 180) % 360 - 180) / 40.0) ** 2)
    # dikey dipol: tepeye doğru kazanç düşer
    rssi += 12.0 * np.log10(np.maximum(np.cos(np.radians(np.clip(yukseklik_deg, 0, 89))), 0.05))
    return rssi


def bir_gun(rng, gun, ist, iz_sayisi):
    satirlar = []
    istasyon = {"enlem": ist["enlem"], "boylam": ist["boylam"],
                "anten_rakim_m": ist["zemin_rakimi_m"] + ist["anten_yerden_yukseklik_m"]}
    gun0 = datetime.strptime(gun, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    for _ in range(iz_sayisi):
        icao_benzeri = f"{rng.integers(0, 16**12):012x}"
        bas = gun0 + timedelta(seconds=float(rng.uniform(0, 86400 - 3600)))
        sure = rng.uniform(15, 60) * 60
        t = np.arange(0, sure, 5.0)
        r0 = rng.uniform(20, 350)
        e0, b0 = oz.kaydir(ist["enlem"], ist["boylam"], r0, rng.uniform(0, 360))
        yon = rng.uniform(0, 360)
        hiz = rng.uniform(380, 490)
        yol_km = hiz * 1.852 * t / 3600
        e, b = oz.kaydir(np.full_like(t, e0), np.full_like(t, b0), yol_km, np.full_like(t, yon))
        alcak = rng.random() < 0.25          # inişe/kalkışa geçen uçak
        if alcak:
            irtifa_ft = np.clip(rng.uniform(8000, 20000) + rng.choice([-1, 1]) * 1500 * t / 60, 1500, 38000)
        else:
            irtifa_ft = np.full_like(t, rng.choice(np.arange(25000, 40000, 1000)))
        irtifa_m = irtifa_ft * oz.FT_M
        mesafe, azimut = oz.mesafe_azimut(istasyon["enlem"], istasyon["boylam"], e, b)
        aci = oz.yukseklik_acisi(mesafe, irtifa_m, istasyon["anten_rakim_m"])
        rssi = beklenen_rssi(mesafe, azimut, aci) + rng.normal(0, 2.0, len(t)) + rng.normal(0, 1.0)
        alindi = (rssi > -47.0) & (aci > -0.5)
        if alindi.sum() < 5:
            continue
        kategori = rng.choice(["A3", "A3", "A3", "A2", "A1", "A5", ""], p=[.3, .2, .15, .15, .08, .07, .05])
        nic = 8 if rng.random() > 0.05 else int(rng.integers(0, 7))
        for i in np.flatnonzero(alindi):
            z = bas + timedelta(seconds=float(t[i]))
            satirlar.append({
                "zaman_utc": z.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-4] + "Z",
                "ucak_id": icao_benzeri, "enlem": round(e[i], 5), "boylam": round(b[i], 5),
                "irtifa_baro_ft": int(irtifa_ft[i]), "irtifa_geo_ft": int(irtifa_ft[i] + 300),
                "yerde": 0, "hiz_kt": round(hiz, 1), "yon_deg": round(yon, 1),
                "dikey_hiz_fpm": 0, "rssi_dbfs": round(float(np.clip(rssi[i], -49.5, -1.0)), 1),
                "nic": nic, "nac_p": 9 if nic >= 7 else 5, "kategori": kategori,
                "mesaj": int(i * 10), "seen_pos_s": 0.3, "kazanc_db": "49.6",
                "oturum": 1, "pi_sicaklik_c": 50.0,
            })
    return pd.DataFrame(satirlar, columns=SUTUNLAR).sort_values("zaman_utc")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cikti", default="output/sentetik")
    p.add_argument("--gun", type=int, default=14)
    p.add_argument("--iz", type=int, default=150, help="günlük uçak geçişi sayısı")
    p.add_argument("--tohum", type=int, default=42)
    a = p.parse_args()
    rng = np.random.default_rng(a.tohum)
    cikti = Path(a.cikti)
    (cikti / "veri").mkdir(parents=True, exist_ok=True)
    (cikti / "istasyon.yaml").write_text(
        "# SENTETİK istasyon (uydurma koordinat)\n" + yaml.safe_dump({"istasyon": SAHTE_ISTASYON}),
        encoding="utf-8")
    bas = datetime(2026, 11, 3)
    for g in range(a.gun):
        gun = (bas + timedelta(days=g)).strftime("%Y-%m-%d")
        df = bir_gun(rng, gun, SAHTE_ISTASYON, a.iz)
        df.to_csv(cikti / "veri" / f"{gun}.csv.gz", index=False, compression="gzip")
        print(f"{gun}: {len(df):,} satır")


if __name__ == "__main__":
    main()
