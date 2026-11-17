#!/usr/bin/env python3
"""RF Gözcü gece yükleyicisi.

1. Biten günlerin CSV dosyalarını sıkıştırır (.csv.gz).
2. Sıkıştırılmış dosyaları ve olaylar.log'u rclone ile Google Drive'a kopyalar.
3. Drive'da aynı boyutta olduğu DOĞRULANAN ve `tutma_gun`'den eski dosyaları
   Pi'den siler. Doğrulanmayan hiçbir dosyaya dokunmaz.
4. Sonucu YUKLEME_DURUMU.txt dosyasına yazar; hata varsa YUKLEME_HATASI oluşturur.

Çalıştırma:  python yukle.py          (systemd zamanlayıcısı her gece çalıştırır)
"""
import gzip
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

KLASOR = Path(__file__).resolve().parent
AYAR = yaml.safe_load((KLASOR / "config.yaml").read_text())
VERI = Path(AYAR.get("veri_klasoru", "~/rfgozcu/data")).expanduser()
HEDEF = AYAR.get("rclone_hedef", "gdrive:rf-gozcu/logs")
TUTMA_GUN = int(AYAR.get("tutma_gun", 7))
DURUM = KLASOR / "YUKLEME_DURUMU.txt"
HATA = KLASOR / "YUKLEME_HATASI"


def rclone(*args):
    return subprocess.run(["rclone", *args], capture_output=True, text=True, timeout=1800)


def bugun():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def biten_gunleri_sikistir():
    for csv_dosya in sorted(VERI.glob("*.csv")):
        if csv_dosya.stem >= bugun():          # bugünün dosyası hâlâ yazılıyor
            continue
        gz = csv_dosya.with_suffix(".csv.gz")
        with open(csv_dosya, "rb") as k, gzip.open(gz, "wb") as h:
            shutil.copyfileobj(k, h)
        csv_dosya.unlink()


def main():
    zaman = datetime.now(timezone.utc).isoformat(timespec="seconds")
    biten_gunleri_sikistir()

    sonuc = rclone("copy", str(VERI), HEDEF, "--include", "*.csv.gz", "--include", "olaylar.log")
    if sonuc.returncode != 0:
        mesaj = sonuc.stderr.strip().splitlines()[-1] if sonuc.stderr.strip() else "bilinmeyen hata"
        ipucu = ""
        if "invalid_grant" in sonuc.stderr or "token" in sonuc.stderr.lower():
            ipucu = "\nGoogle izni dolmuş olabilir. Yenilemek için: rclone config reconnect gdrive:"
        HATA.write_text(f"{zaman} YÜKLEME BAŞARISIZ: {mesaj}{ipucu}\n")
        DURUM.write_text(f"Son deneme: {zaman}\nDurum: BAŞARISIZ\n{mesaj}{ipucu}\n")
        print(HATA.read_text())
        return

    # Drive'daki dosyaların boyutlarını al, sadece doğrulananları sil
    liste = rclone("lsjson", HEDEF)
    uzaktaki = {d["Name"]: d["Size"] for d in json.loads(liste.stdout or "[]")} if liste.returncode == 0 else {}
    sinir = (datetime.now(timezone.utc) - timedelta(days=TUTMA_GUN)).strftime("%Y-%m-%d")
    silinen, bekleyen = 0, 0
    for gz in sorted(VERI.glob("*.csv.gz")):
        dogrulandi = uzaktaki.get(gz.name) == gz.stat().st_size
        if not dogrulandi:
            bekleyen += 1
        elif gz.name[:10] < sinir:
            gz.unlink()
            silinen += 1

    HATA.unlink(missing_ok=True)
    DURUM.write_text(f"Son başarılı yükleme: {zaman}\n"
                     f"Drive'da doğrulanmamış dosya: {bekleyen}\n"
                     f"Pi'den silinen eski dosya: {silinen}\n")
    print(DURUM.read_text())


if __name__ == "__main__":
    main()
