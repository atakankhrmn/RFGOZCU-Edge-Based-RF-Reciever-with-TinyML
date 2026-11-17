#!/usr/bin/env python3
"""RF Gözcü veri kaydedici.

readsb'nin aircraft.json dosyasını her saniye okur; konumu taze olan her
uçak için en fazla `aralik_s` saniyede bir satır yazar. Her UTC günü için
ayrı bir CSV dosyası oluşturur. Satırlar SD kartı yormamak için toplu
halde (her `yazma_araligi_s` saniyede bir) diske yazılır.

Çalıştırma:  python kaydedici.py
"""
import csv
import hashlib
import json
import re
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

KLASOR = Path(__file__).resolve().parent
AYAR = yaml.safe_load((KLASOR / "config.yaml").read_text())

AIRCRAFT_JSON = Path(AYAR.get("aircraft_json", "/run/readsb/aircraft.json"))
VERI = Path(AYAR.get("veri_klasoru", "~/rfgozcu/data")).expanduser()
ARALIK = float(AYAR.get("aralik_s", 5))
YAZMA_ARALIGI = float(AYAR.get("yazma_araligi_s", 30))
OTURUM = int(AYAR["oturum"])
TUZ = str(AYAR["hash_tuzu"])
OLAY_LOG = VERI / "olaylar.log"

SUTUNLAR = ["zaman_utc", "ucak_id", "enlem", "boylam", "irtifa_baro_ft", "irtifa_geo_ft",
            "yerde", "hiz_kt", "yon_deg", "dikey_hiz_fpm", "rssi_dbfs", "nic", "nac_p",
            "kategori", "mesaj", "seen_pos_s", "kazanc_db", "oturum", "pi_sicaklik_c"]


def olay(mesaj):
    """Önemli durumları (kesinti, kazanç uyarısı) ayrı bir günlüğe yazar."""
    satir = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {mesaj}\n"
    with open(OLAY_LOG, "a") as f:
        f.write(satir)
    print(satir, end="", flush=True)


def kazanc_oku():
    try:
        metin = Path("/etc/default/readsb").read_text()
        m = re.search(r"--gain\s+(\S+)", metin)
        return m.group(1).strip('"') if m else "bilinmiyor"
    except OSError:
        return "bilinmiyor"


def sicaklik_oku():
    try:
        return round(int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000, 1)
    except (OSError, ValueError):
        return ""


def ucak_id(icao):
    return hashlib.sha256((TUZ + icao.lower()).encode()).hexdigest()[:12]


def satir_uret(u, zaman, kazanc, sicaklik):
    if u.get("lat") is None or u.get("lon") is None or u.get("rssi") is None:
        return None
    if u.get("seen_pos", 99) >= 1.0:          # konum eski, RSSI ile eşleşmez
        return None
    alt = u.get("alt_baro", "")
    yerde = 1 if alt == "ground" else 0
    if yerde:
        alt = 0
    return {
        "zaman_utc": zaman, "ucak_id": ucak_id(u["hex"]),
        "enlem": u["lat"], "boylam": u["lon"],
        "irtifa_baro_ft": alt, "irtifa_geo_ft": u.get("alt_geom", ""), "yerde": yerde,
        "hiz_kt": u.get("gs", ""), "yon_deg": u.get("track", ""),
        "dikey_hiz_fpm": u.get("baro_rate", u.get("geom_rate", "")),
        "rssi_dbfs": u["rssi"], "nic": u.get("nic", ""), "nac_p": u.get("nac_p", ""),
        "kategori": u.get("category", ""), "mesaj": u.get("messages", ""),
        "seen_pos_s": u.get("seen_pos", ""), "kazanc_db": kazanc,
        "oturum": OTURUM, "pi_sicaklik_c": sicaklik,
    }


def diske_yaz(tampon):
    """Satırları gün gün ilgili CSV dosyalarına ekler."""
    gunler = {}
    for s in tampon:
        gunler.setdefault(s["zaman_utc"][:10], []).append(s)
    for gun, satirlar in gunler.items():
        dosya = VERI / f"{gun}.csv"
        yeni = not dosya.exists()
        with open(dosya, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=SUTUNLAR, lineterminator="\n")
            if yeni:
                w.writeheader()
            w.writerows(satirlar)


def main():
    VERI.mkdir(parents=True, exist_ok=True)
    olay(f"Kaydedici başladı (oturum {OTURUM}, aralık {ARALIK} s)")
    d = {"son_kayit": {}, "tampon": [], "son_yazma": time.monotonic(),
         "veri_var": True, "kazanc_uyarildi": False}
    # systemd durdururken tampondaki satırlar kaybolmasın
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        while True:
            time.sleep(1)
            bir_tur(d)
    finally:
        if d["tampon"]:
            diske_yaz(d["tampon"])
        olay("Kaydedici durdu")


def bir_tur(d):
    try:
        veri = json.loads(AIRCRAFT_JSON.read_text())
        simdi = float(veri["now"])
    except (OSError, ValueError, KeyError):
        veri, simdi = None, None

    # readsb çalışmıyorsa (mod değişti, servis durdu) kesintiyi işaretle
    taze = simdi is not None and time.time() - simdi < 10
    if not taze and d["veri_var"]:
        olay("KESINTI_BASLADI: aircraft.json güncellenmiyor (readsb kapalı olabilir)")
        d["veri_var"] = False
    elif taze and not d["veri_var"]:
        olay("KESINTI_BITTI: veri akışı yeniden başladı")
        d["veri_var"] = True

    if taze:
        kazanc = kazanc_oku()
        if kazanc in ("auto", "-10", "bilinmiyor") and not d["kazanc_uyarildi"]:
            olay(f"UYARI: kazanç sabit değil ({kazanc}). Veri toplamadan önce sabitleyin!")
            d["kazanc_uyarildi"] = True
        sicaklik = sicaklik_oku()
        zaman = datetime.fromtimestamp(simdi, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-4] + "Z"
        sk = d["son_kayit"]
        for u in veri.get("aircraft", []):
            icao = u.get("hex", "")
            if not icao or simdi - sk.get(icao, 0) < ARALIK:
                continue
            s = satir_uret(u, zaman, kazanc, sicaklik)
            if s:
                d["tampon"].append(s)
                sk[icao] = simdi
        # uzun süredir görünmeyen uçakları bellekten temizle
        if len(sk) > 2000:
            d["son_kayit"] = {k: v for k, v in sk.items() if simdi - v < 3600}

    if d["tampon"] and time.monotonic() - d["son_yazma"] >= YAZMA_ARALIGI:
        diske_yaz(d["tampon"])
        d["tampon"] = []
        d["son_yazma"] = time.monotonic()


if __name__ == "__main__":
    main()
