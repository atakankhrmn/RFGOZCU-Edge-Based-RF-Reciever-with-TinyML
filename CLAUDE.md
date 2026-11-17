# RF Gözcü

Raspberry Pi üzerinde çalışan çok modlu RF alıcısı ve ADS-B sahte konum (spoofing) tespiti.
Dokuz Eylül Üniversitesi, CME 4436 Basics of Internet of Things dönem projesi (Grup 9: Atakan Kahraman, Serkan Ayaşan, Alp Kaya; hoca Prof. Dr. Mehmet Hilal Özcanhan). Proje 05.10.2026'da başladı, 31.12.2026'da bitecek.

Geçmiş, alınan kararlar, ölçümler ve güncel durum için `ILERLEME.md` dosyasını oku.

## Proje ne yapıyor?

Tek bir RTL-SDR alıcısı olduğu için sistem aynı anda tek modda çalışır:

| Mod | Frekans | Yazılım | Durum |
|---|---|---|---|
| Uçak | 1090 MHz (ADS-B) | readsb + tar1090 | Çalışıyor |
| 433 MHz cihazlar | 433.92 MHz | rtl_433 | Donanımda doğrulandı, arayüze bağlanmadı |
| Canlı sinyal | Kullanıcının seçtiği merkez frekans, en fazla 2.4 MHz genişlik | `canli_dalga/` (rtl_sdr + aiohttp + WebSocket) | Çalışıyor |

TinyML kısmı: Uçaklar konumlarını kimlik doğrulaması olmadan kendileri yayınlar. Model, uçağın **bildirdiği konumdan** istasyonumuzda **ölçülmesi beklenen sinyal gücünü (RSSI)** tahmin eder. Ölçülen RSSI beklenenden yaklaşık 1 dakika boyunca tutarlı biçimde saparsa uçak şüpheli işaretlenir. Model yalnızca gerçek (normal) veriyle eğitilir; sahte örnekler sadece test için yazılımda üretilir.

## Donanım ve ortam

- Raspberry Pi 4 Model B, Raspberry Pi OS Lite 64-bit, ekransız, SSH ile yönetiliyor
- Makine adı ve kullanıcı: `rfgozcu` → `ssh rfgozcu@rfgozcu.local`
- RTL-SDR Blog V3 (R860 tuner; sürücüde "Rafael Micro R820T" olarak görünür), USB 2.0 portunda
- Teleskopik dipol anten, dikey. 1090 MHz için kısa çubuklar ~6.9 cm; 433.92 MHz için uzun çubuklar ~52 cm
- İstasyon İzmir'de bir konutun 2. kat balkonunda. Koordinatlar yalnızca Pi'deki `config.yaml` dosyasında
- Geliştirme bilgisayarı Windows; çalışma klasörü `C:\Users\ataka\Desktop\rfgozcu`. Python `py` komutuyla çalışır

## Pi üzerindeki düzen

```
~/rfgozcu/
├── venv/                  Python ortamı (aiohttp, numpy, pyyaml)
├── canli_dalga/
│   ├── canli_dalga.py     aiohttp sunucusu, port 8080, /ws WebSocket, /secenekler
│   └── index.html         canvas ile I/Q ve genlik çizen sayfa
├── kaydedici/
│   ├── kaydedici.py       aircraft.json → günlük CSV (rf-logger.service)
│   ├── yukle.py           gece sıkıştırma + Google Drive yüklemesi (rf-uploader.timer, 03:30 yerel saat)
│   ├── config.yaml        GİZLİ: koordinatlar, hash tuzu, oturum no
│   ├── config.example.yaml
│   ├── rf-logger.service, rf-uploader.service, rf-uploader.timer
│   ├── YUKLEME_DURUMU.txt son yüklemenin sonucu
│   └── YUKLEME_HATASI     yalnızca yükleme başarısızsa oluşur
└── data/
    ├── YYYY-AA-GG.csv     bugünün dosyası (UTC gününe göre)
    ├── YYYY-AA-GG.csv.gz  biten günler
    └── olaylar.log        başlama, durma, kesinti, kazanç uyarıları
```

Diğer yollar: readsb çıktısı `/run/readsb/aircraft.json` ve `/run/readsb/stats.json`, readsb ayarı `/etc/default/readsb`, tar1090 `http://rfgozcu.local/tar1090` (lighttpd, port 80), Drive hedefi `gdrive:rf-gozcu/logs`.

## Sık kullanılan komutlar (Pi'de)

```bash
systemctl status rf-logger readsb                 # servisler çalışıyor mu
tail -n 5 ~/rfgozcu/data/$(date -u +%F).csv       # son kayıtlar
tail ~/rfgozcu/data/olaylar.log                   # kesinti ve uyarılar
cat ~/rfgozcu/kaydedici/YUKLEME_DURUMU.txt        # son yükleme
systemctl list-timers rf-uploader.timer           # sonraki yükleme
sudo systemctl start rf-uploader                  # yüklemeyi hemen çalıştır
rclone ls gdrive:rf-gozcu/logs                    # Drive'daki dosyalar
rclone config reconnect gdrive:                   # Drive iznini yenile (6 günde bir)
jq '.last1min | {mesaj: .messages, guclu: .local.strong_signals, gurultu: .local.noise}' /run/readsb/stats.json
vcgencmd measure_temp; vcgencmd get_throttled     # sıcaklık ve yavaşlama
```

Python scriptleri Pi'de her zaman `~/rfgozcu/venv/bin/python` ile çalışır.

## Veri seti

Her uçak için en fazla 5 saniyede bir satır; yalnızca konumu 1 saniyeden taze olanlar yazılır. Sütunlar:

```
zaman_utc, ucak_id, enlem, boylam, irtifa_baro_ft, irtifa_geo_ft, yerde, hiz_kt,
yon_deg, dikey_hiz_fpm, rssi_dbfs, nic, nac_p, kategori, mesaj, seen_pos_s,
kazanc_db, oturum, pi_sicaklik_c
```

- `rssi_dbfs` modelin hedefidir (alıcının ölçümü). Konum, irtifa ve kategori uçağın yayınladığı bilgilerdir.
- `ucak_id` ICAO adresinin tuzlu SHA-256 özetidir (ilk 12 karakter).
- `oturum`: **0** kampüste yapılan test (otomatik kazanç, bina içi, farklı konum; eğitimde kullanılmaz), **1** balkondaki gerçek veri (kazanç 49.6 dB sabit). Anten ya da kazanç değişirse numara artırılır.
- Kaydedici özellik hesaplamaz; ham veriyi yazar. Özellikler eğitim aşamasında hesaplanır.

## Model tasarımı (henüz uygulanmadı)

- **Özellikler:** log10(mesafe), sin(azimut), cos(azimut), yükseklik açısı, irtifa, uçak kategorisi. Mesafe haversine ile; yükseklik açısı `atan((h_uçak − h_anten − d²/2R) / d)`, R ≈ 6371 km. `h_anten` deniz seviyesine göredir (zemin rakımı + yerden yükseklik, ikisi de `config.yaml`'da).
- **Veri ayırma:** Güne göre (ör. 10 gün eğitim, 2 doğrulama, 2 test). Rastgele ayırma yapılmaz; aynı uçağın ardışık satırları sızıntıya yol açar.
- **Baseline:** Log-mesafe yol kaybı, `RSSI ≈ a − 10·n·log10(d)`, eğitim verisine en küçük karelerle uydurulur.
- **Model:** Küçük MLP (girdi → Dense 32 → Dense 16 → 1), Keras. Normalizasyon değerleri modelle birlikte saklanır.
- **Anomali skoru:** Uçak başına son ~1 dakikadaki ortalama (ölçülen − beklenen) farkı, doğrulama setine göre z-skoru. Eşik, doğrulamada yanlış alarm ~%1 olacak şekilde.
- **Değerlendirme:** Test günlerinde konumlar 10 / 25 / 50 / 100 km kaydırılır, RSSI aynı kalır; baseline ve model için yakalama oranı ve ROC/AUC. Ek kontrol olarak NIC/NACp değeri düşük uçakların skor dağılımı.
- **Dağıtım:** int8 quantization ile LiteRT (TensorFlow Lite); Pi'de model boyutu, çıkarım süresi ve float32'ye göre RMSE kaybı ölçülür.
- **Katman 1 (kurallar):** Ani konum sıçraması, imkânsız hız. Planlandı.
- Eğitim Google Colab'da yapılır; veri Drive'dan (`rf-gozcu/logs`) okunur.

## Kesin kurallar

Veri toplama sürerken (oturum 1; en az 14, tercihen 21 gün; başlangıç tarihi `ILERLEME.md`'de):

- **Kazanca dokunma.** `sudo readsb-gain` çalıştırma; değer 49.6 dB'de sabit, `auto` asla kullanılmaz.
- **Anteni, çubuk uzunluklarını ve konumu değiştirme.** Model bu kurulumu öğreniyor.
- **readsb'yi durdurma.** Canlı sinyal sunucusu ve rtl_433 alıcıyı readsb'den alır (`usb_claim_interface error -6`). Kısa bir test şartsa önce kullanıcıya sor.
- **`apt upgrade` çalıştırma.** Sürücü değişiklikleri ölçümleri etkileyebilir.
- **`~/rfgozcu/data/` içindeki dosyaları silme ya da düzenleme.** Silmeyi yalnızca `yukle.py` yapar, o da Drive'da doğruladıktan sonra.

Her zaman:

- **`config.yaml`, `rclone.conf`, OAuth client secret ve istasyon koordinatları repoya, rapora ya da log çıktısına girmez.** `.gitignore` bunları kapsıyor; yeni bir gizli dosya eklersen oraya da ekle.
- **Hiçbir RF yayını yapılmaz.** RTL-SDR yalnızca alıcıdır. Sahte ADS-B üretimi yalnızca kayıtlı veri üzerinde, yazılımda yapılır.
- **Gerçek ICAO adresi, çağrı adı, squawk ve tescil kaydedilmez.** rtl_433 çıktısındaki cihaz `id` alanları da saklanmaz. Kumanda ve araç anahtarı kodları kaydedilip yeniden yayınlanmaz.
- Hava bandı, deniz telsizi ve AIS projenin parçası değildir; koda ya da rapora eklenmez.
- Pi çalışırken GPIO kablolarına dokunulmaz; kapatmak için `sudo poweroff`, yeşil ışık sönünce güç çekilir.

## Kod ve çalışma kuralları

- Değişken, fonksiyon, sütun adları ve yorumlar Türkçe (ASCII harflerle: `kazanc`, `sicaklik`). Raporlar İngilizce.
- Veri dosyalarındaki bütün zamanlar UTC. Türkiye saati UTC+3. Yalnızca systemd zamanlayıcısı yerel saati kullanır.
- SD kartı korumak için diske yazma toplu yapılır (kaydedici 30 saniyede bir yazar).
- Pi'de büyük derleme ve eğitim yapılmaz.
- Bilgisayardan Pi'ye dosya `scp` ile gider. `ssh` ve `scp` komutları bilgisayarda çalışır, Pi'nin içinde değil.
- Kullanıcıya açıklamalar Türkçe ve adım adım yapılır; her komutun ne işe yaradığı ve neden gerektiği söylenir.

## Takvim

W1 = 5 Ekim 2026 haftası.

| Hafta | İş |
|---|---|
| W5–W7 (2–22 Kas) | ADS-B veri toplama |
| W5–W10 | Web arayüzü |
| W7–W8 | Özellik çıkarma ve sahte veri üretimi |
| W8–W9 | Mod yöneticisi ve entegrasyon |
| W9–W10 | Model eğitimi ve baseline |
| W11 | TFLite dağıtımı |
| W11–W12 | Test ve değerlendirme |
| W12–W13 | Final raporu ve demo |
