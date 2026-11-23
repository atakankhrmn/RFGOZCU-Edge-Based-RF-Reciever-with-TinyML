# RF Gözcü: İlerleme Günlüğü

Son güncelleme: 23 Kasım 2026. Projenin ne olduğu ve kurallar için `CLAUDE.md`'ye bak; bu dosya şimdiye kadar ne yapıldığını, neden yapıldığını ve sırada ne olduğunu anlatır.

## 1. Güncel durum

- Pi evde, 2. kat balkonda çalışıyor. Anten dikey, kısa çubuklar ~6.9 cm.
- readsb kazancı **49.6 dB'de sabit**. Veri toplama **oturum 1** olarak sürüyor.
- Kaydedici (`rf-logger`) ve gece yükleyicisi (`rf-uploader.timer`, 03:30) kurulu ve test edildi.
- Google Drive izni 7 günde doluyor; 6 günde bir `rclone config reconnect gdrive:` ile yenileniyor.
- Model 21 günlük gerçek veriyle eğitildi ve değerlendirildi (23.11.2026). Sonuçlar Hafta 8 bölümünde. Model dosyaları bilgisayarda `output/gercek/` klasöründe; henüz Pi'ye gönderilmedi.
- Mod yöneticisi, Pi'deki çıkarım servisi ve birleşik web arayüzü henüz yazılmadı.

### Doldurulması gereken bilgiler

Bunlar sohbette netleşmedi; bilen biri doldursun:

- [ ] Oturum 1'in başladığı tarih ve saat: `__.11.2026`
- [ ] PPR3'teki sarı yerler (`[XX.X]` → 49.6, `[DD.11.2026]` → başlangıç tarihi) dolduruldu ve rapor teslim edildi mi?
- [ ] Fan şu an takılı mı, çıkarıldı mı, 3.3 V'a (pin 1) mı alındı?
- [ ] Zemin rakımı ve anten yüksekliği `config.yaml`'a yazıldı mı? (2. kat ≈ yerden 7 m + zemin rakımı)
- [ ] Son Drive izni yenileme tarihi: `__.11.2026`
- [ ] GitHub reposu açıldı mı? Adresi:
- [ ] SD kart imajı alındı mı, nerede duruyor?

## 2. Sıradaki işler

Öncelik sırasıyla:

1. **Veri toplamayı sağlıklı sürdürmek** (en az 14, tercihen 21 gün). Günlük kontrol: yükleme durumu, satır sayısı, `olaylar.log`, sıcaklık.
2. **Eğitimi son veriyle tekrarlamak.** Veri toplama sürdükçe yeni günler `logs/` klasörüne eklenip `model/README.md`'deki adımlar yeniden çalıştırılabilir.
3. **Pi'de ölçüm ve çıkarım servisi** (`rf-infer`): `model_int8.tflite` Pi'ye kopyalanır, Pi'de `ai-edge-litert` ile çıkarım süresi ölçülür. Servis `aircraft.json` → `ozellikler.py` → skor zincirini çalıştırır; 60 sn pencere ve eşik `degerlendirme.json`'dan alınır.
6. **Kural katmanı** (ani sıçrama, imkânsız hız).
7. **Mod yöneticisi:** readsb / rtl_433 / canlı sinyal arasında, aktif servisi durdurup diğerini başlatan servis.
8. **Birleşik web arayüzü:** mod seçici, uçak haritası + güven skoru, 433 MHz cihaz listesi, canlı sinyal, anten ayarı hatırlatıcısı.
9. Test (48 saat kesintisiz çalışma), replay/demo modu, final raporu ve sunum.

## 3. Tasarım kararları ve nedenleri

| Karar | Neden |
|---|---|
| TinyML = beklenen RSSI regresyonu ile sahte konum tespiti | Decoder'ın veremediği, if-else ile yazılamayan tek bilgi buydu. Sinyal yayılımı yöne ve açıya bağlı (bina, tepe, dipolün kör noktası); formül bunu bilemez. |
| Elenen TinyML fikirleri: frekansa göre sinyal sınıflandırma, modülasyon tanıma, 433 MHz cihaz sınıflandırma | İlkinde cevabı frekans zaten söylüyor; ikincisi serbest tarayıcı modu olmadan anlamsız; üçüncüsü rtl_433'ün yaptığını tekrarlıyor. |
| Model yalnızca normal veriyle eğitilir, sahte veri sadece testte | Gerçek saldırı kaydı yasal olarak alınamaz. Mesaj zamanlaması ve ilk görünme noktası gibi özellikler çıkarıldı, çünkü konum kaydırma bunları değiştirmiyor. |
| Baseline fizik formülü (log-mesafe) | Kural tabanlı sıçrama kontrolü, yavaş kaydırılan konumu tasarım gereği yakalayamaz; karşılaştırma adil olmazdı. |
| RTL-SDR Blog V3, tek alıcı | Bütçe. 433.92 ve 1090 MHz'i kapsıyor; 6 GHz'e çıkan alıcılar gereksiz pahalı. |
| Sistem yalnızca alıcı | Havacılık frekanslarında yayın yasak ve tehlikeli. |
| Gemi (AIS) modu çıkarıldı | Kapsam küçültüldü. AIS-catcher bir kez derlenip denendi (kampüsten tek mesaj alındı); `~/AIS-catcher` klasörü Pi'de kalmış olabilir, kullanılmıyor. |
| Bluetooth ile kalabalık tahmini yapılmayacak | Ekip tarafından ertelendi/bırakıldı; Bluetooth Pi'de kapatıldı. |
| Hava bandı ve deniz telsizi projeye girmedi | Türkiye'de yasal durumu belirsiz; yalnızca kısa test olarak denendi. |
| "Spektrum modu" → canlı zaman alanı (I/Q) görünümü | Ekip sinyalin dalga biçimini canlı görmek istedi. Zaman alanında aralık en fazla ~2.4 MHz olabildiği için kullanıcı merkez frekans + genişlik seçiyor. `rtl_power` ile tarama (`spektrum.py`) yalnızca prototip olarak kaldı. |
| Bulut = Google Drive + rclone | Ücretsiz, Pi'den otomatik yükleme, Colab'dan doğrudan okuma. İlk yol haritasındaki Firebase planı bırakıldı. |
| Veri UTC, günlük CSV, yalnızca biten günler yüklenir | Tutarlılık; yarım dosyanın tekrar tekrar yüklenmesini önlemek. |
| Ham veri kaydedilir, özellikler sonradan hesaplanır | Formül hatası çıkarsa 3 haftalık veri yeniden toplanmadan düzeltilebilir. |
| Uçak kimliği tuzlu hash, çağrı adı/squawk kaydedilmez | Veri minimizasyonu; yine de aynı uçağın satırları gruplanabiliyor. |
| Hava durumu modele girmiyor | 1090 MHz'de etkisi ihmal edilebilir; yalnızca Pi sıcaklığı kontrol amaçlı kaydediliyor. |

## 4. Kronoloji

### Hafta 1–2 (5–18 Ekim): fikir ve tasarım
- Proje fikri netleşti: mod seçilebilen RF alıcısı + ADS-B anomali tespiti.
- PPR1 yazıldı (06.10.2026). İncelemede bulunan tutarsızlıklar (tek alıcı–takvim çakışması, anten ayarı–RSSI çelişkisi, sahte verinin değiştirmediği özellikler, adaletsiz baseline) PPR2'de düzeltildi.

### Hafta 3 (19–25 Ekim): donanım ve ilk sinyaller
- Donanım toplandı. Maliyet: Pi 4 (4 GB) 7.405,50 TL (hocadan; piyasa fiyatı), RTL-SDR V3 kiti 6.500, kutu 385, fan 320, adaptör 550, 32 GB microSD 500. Toplam 15.660,50 TL; grubun harcaması 8.255 TL.
- Pi kurulumu: OS Lite 64-bit, SSH, Bluetooth ve triggerhappy kapalı, WiFi güç tasarrufu kapalı, journald 50 MB sınırı, `dvb_usb_rtl28xxu` kara listede.
- `rtl_test` ile alıcı doğrulandı; FM radyo SSH üzerinden bilgisayarda dinlenerek uçtan uca test edildi.
- readsb + tar1090 kuruldu. İlk test (bina içi, 19.10): 7 konumlu uçak, ~11 mesaj/sn, 32 NM'ye kadar; Flightradar24 ile doğrulandı.
- Bulut olarak Google Drive seçildi. PPR2 yazıldı (21.10.2026).

### Hafta 4 (26 Ekim – 1 Kasım): modlar, kazanç, bulut, kaydedici
- rtl_433 araba anahtarıyla doğrulandı (uzun çubuklar ~52 cm).
- Bina içi kazanç gözlemi: 20.7 dB'de hiç uçak yok; 49.6 dB'de gürültü −42.0, ortalama sinyal −29.8, tepe −25.2 dBFS (doyma yok). Aynı uçağın RSSI'ı kazançla birlikte kayıyor.
- Gözlemler: alçak uçaklar geç görünüp erken kayboluyor (bina + dipolün tepe kör noktası); Mode S'li askeri uçağın (C295) konumu gelmiyor; tar1090 menzil haritası yöne göre çok düzensiz.
- Canlı sinyal modu yazıldı (`canli_dalga/`), 433.92 MHz'de araba anahtarıyla test edildi. "En güçlü anı göster" seçeneği her 0.1 s'lik bloktaki tepe örneğin etrafını gösterir.
- rclone kuruldu. Ortak client ID 2026'da kaldırıldığı için Google Cloud Console'da kendi OAuth client'ımız oluşturuldu (Desktop app, `drive.file` kapsamı). Yayınlamak web sitesi ve gizlilik politikası gerektirdiği için **Testing modunda** kaldı; izin 7 günde doluyor.
- Kaydedici, yükleyici ve systemd birimleri yazıldı; kampüste oturum 0 olarak uçtan uca test edildi.
- Bağlantı diyagramı ve blok diyagramı hazırlandı.

### Hafta 5 (2–8 Kasım): eve taşıma ve veri toplama
- İstasyon balkona taşındı. İlk okuma (38.6 dB): 2245 mesaj/dk, güçlü sinyal 0, gürültü −43.6 dBFS; bina içine göre üç kattan fazla mesaj.
- 38.6 → 49.6 arası denendi; en çok mesaj ve en düşük gürültü 49.6'da, doyma hiç yok. Kazanç 49.6 dB'de sabitlendi, oturum 1 başlatıldı.
- PPR3 yazıldı (04.11.2026): bölüm 2.1 bağlantı diyagramı, 2.2 blok diyagramı, Table 2 kaydedici alanları, güncel Gantt.

### Hafta 8 (23–29 Kasım): model eğitim kodu
- Eğitimin Colab yerine bilgisayarda yapılmasına karar verildi. Gerekçe: veri küçük (milyonlarca satır, RAM'e sığıyor), model küçük (~1000 parametre, CPU'da dakikalar sürüyor) ve `ozellikler.py` hem eğitimde hem Pi'de aynı dosya olarak kullanılabiliyor.
- `model/` yazıldı: özellikler, okuma/filtreleme, güne göre ayırma, baseline, MLP, 60 sn pencere z-skoru, %1 yanlış alarm eşiği, 10/25/50/100 km kaydırma testi, int8 LiteRT dönüşümü.
- Sentetik veriyle deneme (14 gün, uydurma istasyon; yalnızca kodu doğrulamak için, raporda kullanılmaz):
  - Test RMSE: sabit ortalama 5.34 dB, baseline 2.43 dB, MLP 1.94 dB.
  - Yakalama oranı / AUC, baseline → MLP: 50 km'de 0.08/0.70 → 0.31/0.77; 100 km'de 0.21/0.80 → 0.48/0.85.
  - int8 model 4.8 KB, float32'ye göre RMSE kaybı 0.014 dB.
- **Gerçek veriyle ilk eğitim (23.11.2026).** Veri: 2–22 Kasım, 21 gün. Filtrelerden sonra 455.640 satır, 2.715 uçak, 11.294 geçiş. Ayırma: eğitim 2–16 Kasım (15 gün), doğrulama 17–19 Kasım, test 20–22 Kasım.
  - Test RMSE: sabit ortalama 5.13 dB, baseline 4.07 dB (a = −15.8 dBFS, n = 0.87), **MLP 2.38 dB**.
  - Baseline'ın yöne göre hatası büyük: doğuda (60–110°) ~5 dB fazla, güneyde (~155°) ~4 dB az tahmin ediyor. MLP'nin hatası bütün yönlerde ±0.5 dB içinde. MLP bina ve arazi etkisini öğrenmiş.
  - n = 0.87 serbest uzaydaki 2'den çok düşük. Yakındaki uçaklar yüksek açıda kalıyor, dipolün tepe kör noktasına giriyor ve sinyalleri zayıf geliyor. Bu da mesafe eğrisini düzleştiriyor.
  - Sahte konum testi (60 sn pencere, eşik doğrulamada %1 yanlış alarm; testte gerçekleşen: baseline %1.3, MLP %1.1). Yakalama / AUC:

    | Kaydırma | Baseline | MLP |
    |---|---|---|
    | 10 km | 0.05 / 0.54 | 0.31 / 0.77 |
    | 25 km | 0.10 / 0.58 | 0.48 / 0.85 |
    | 50 km | 0.15 / 0.62 | 0.62 / 0.91 |
    | 100 km | 0.24 / 0.78 | 0.80 / 0.96 |

  - int8 LiteRT: 4.792 bayt (float32 tflite 5.840, keras 37.538). RMSE kaybı 0.055 dB. Kategori sütunları normalize edilmeden 0/1 bırakıldı. Normalize edilince kayıp 0.21 dB'ydi.
  - Düşük NIC kontrolü güvenilir değil: test günlerindeki düşük NIC satırlarının %91'i tek bir B6 (İHA) aracına ait. Alarm oranı eğitimden eğitime %50–93 arasında değişti. Raporda genelleme yapılmamalı.
  - Veride görülenler: ~3.7 km'de, batı-güneybatıda, ~1.800 ft irtifada 507 uçaklık bir küme var (havalimanı iniş/kalkış yolu; gerçek veri, tutuldu). 202 satır −49.5 dBFS'de (readsb alt sınırı, filtrelendi). 2 Kasım dosyasında elektrik kesintisinden kalma bir NUL satırı vardı (okuyucu artık bunu temizliyor).
- Pi'ye Ethernet ile bağlanırken ICS servisinin kapalı olduğu görüldü. Pi bu durumda IPv4 almıyor, ama IPv6 yerel adresiyle (`fe80::...%<arayüz>`) erişilebiliyor.

## 5. Bilinen tuzaklar

- **`usb_claim_interface error -6`:** Alıcıyı başka bir program tutuyor. `sudo systemctl stop readsb; pkill rtl_fm; pkill rtl_sdr` ile serbest bırakılır. Veri toplama sırasında readsb durdurulmaz.
- **`ssh ... | ffplay` ve `scp` komutları bilgisayarda çalışır.** Pi'nin içinde çalıştırılınca "command not found" ya da satır devamı (`>`) beklemesi olur.
- **`rtl_test -t` çıktısındaki "No E4000 tuner found" ve "PLL not locked"** hata değildir.
- **Yükleyici bugünün dosyasını göndermez.** Yalnızca biten günleri sıkıştırıp yükler; bugünkü veri Türkiye saatiyle ertesi gece 03:30'da gider.
- **`drive.file` kapsamı:** rclone yalnızca kendi oluşturduğu klasörleri görür. Klasörler `rclone mkdir` ile açılır; Drive arayüzünden elle açılan klasörü rclone göremez.
- **İzin yenileme:** `rclone config reconnect gdrive:` → "replace token?" `y` → tarayıcı sorusuna `n` → çıkan `rclone authorize ...` satırı bilgisayarda çalıştırılır → kod Pi'ye yapıştırılır → Shared Drive `n`. Yenileme veri toplamayı bölmez; izin dolarsa yalnızca yükleme bekler, veri Pi'de kalır.
- **`rfgozcu.local` çözülmezse** IP ile bağlanılır (`hostname -I`). Windows İnternet Bağlantı Paylaşımı ile doğrudan Ethernet'te Pi `192.168.137.x` alır.
- **Windows'ta Python:** `python` Microsoft Store'u açabilir; `py` kullanılır.
- **Pi Ethernet'te bulunamıyorsa:** Windows'ta "Internet Bağlantısı Paylaşımı" (SharedAccess) servisi durmuş olabilir. Yönetici PowerShell'de `Start-Service SharedAccess` çalıştırılır, kablo çıkarılıp takılır.
- **TensorFlow 2.21 + Keras 3'te LiteRT dönüşümü** `from_concrete_functions` ile `READ_VARIABLE` hatası veriyor. `donustur.py` önce `model.export(...)` ile SavedModel üretir, dönüşümü oradan yapar.
- **RTL-SDR en yüksek kazancı 49.6 dB'dir;** geçerli değerler `rtl_test` çıktısındaki listeden seçilir.
- Yakından geçen uçaklarda doyma olup olmadığı arada bir kontrol edilmeli: `jq '.total.local.strong_signals' /run/readsb/stats.json`.

## 6. Dosyalar

Bilgisayarda (`C:\Users\ataka\Desktop\rfgozcu`):

| Dosya | Ne |
|---|---|
| `canli_dalga/canli_dalga.py`, `index.html` | Canlı sinyal sunucusu ve sayfası |
| `kaydedici/` | `kaydedici.py`, `yukle.py`, `config.example.yaml`, üç systemd birimi |
| `dalga.py` | Ham IQ kaydından statik dalga grafiği (prototip) |
| `spektrum.py` | `rtl_power` CSV'sinden spektrum + şelale (prototip) |
| `.gitignore` | Gizli dosyalar, veri, imajlar, Python artıkları |

Raporlar ve görseller: `Project Progress Report.docx` (PPR1), `PPR_2_GROUP_9.docx`, `PPR_3_GROUP_9.docx`, `connection_diagram.png`, `flow_diagram.png`, `PPR3_Gantt_Chart.png`.

Not: Sohbetin başında hazırlanan "RF Gözcü — Proje Yol Haritası" tasarım tuvali 12 haftalık ilk plandır; Firebase, gemi modu ve A/B/C rol ayrımı gibi sonradan değişen kısımlar içerir. Güncel plan bu dosya ve `CLAUDE.md`'dir.

## 7. Raporlarda kullanılan kaynaklar

[1] J. Sun, *The 1090 Megahertz Riddle*, TU Delft, 2021 · [2] Warden & Situnayake, *TinyML*, O'Reilly, 2020 · [3] readsb (wiedehopf) · [4] rtl_433 · [5] Google AI Edge, LiteRT · [6] tar1090 · [7] RTL-SDR Blog V3 quick start guide · [8] Raspberry Pi OS · [9] rclone Google Drive belgeleri · [10] aiohttp · [11] Osmocom rtl-sdr · [12] AIN, "GPS spoofing incidents increase in Middle East", 8 Kasım 2023.
