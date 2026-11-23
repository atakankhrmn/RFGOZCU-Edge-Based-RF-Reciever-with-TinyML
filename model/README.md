# RF Gözcü model eğitimi

Model eğitimi Windows bilgisayarda yapılır, Colab kullanılmaz. Komutlar proje klasöründe (`rfgozcu/`) PowerShell'de çalıştırılır.

## Kurulum (ilk sefer)

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python -m pip install -r model\requirements.txt
```

Pi'ye şifresiz bağlanmak için SSH anahtarı gerekir. Bir kez kurulur; ikinci komutta Pi şifresi bir kez sorulur:

```powershell
ssh-keygen -t ed25519
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh rfgozcu@rfgozcu.local "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

`rfgozcu.local` çözülmezse Pi'nin adresi kullanılır. Doğrudan Ethernet'te bu ya `192.168.137.x` ya da IPv6 yerel adres olur (örn. `fe80::...%12`).

## Adımlar

| # | Komut | Ne yapar |
|---|---|---|
| 0 | `powershell -ExecutionPolicy Bypass -File model\veri_indir.ps1` | Drive'daki `.csv.gz` dosyalarını `logs/` klasörüne, istasyon bilgisini `model/istasyon.yaml` dosyasına alır. İki yol da gitignore'da. Daha kolay yol: Drive web arayüzünde `rf-gozcu/logs` klasörünü zip olarak indirip `logs/` klasörüne açmak. Bu durumda `istasyon.yaml` elle yazılır. |
| 1 | `.\.venv\Scripts\python model\veri_oku.py` | Filtrelerden sonra kalan satır sayısını, gün listesini, RSSI ve mesafe özetini yazdırır. |
| 2 | `.\.venv\Scripts\python model\egitim.py` | Güne göre ayırır, baseline ve MLP'yi eğitir. Sonuçları `output/gercek/` klasörüne yazar. |
| 3 | `.\.venv\Scripts\python model\degerlendirme.py` | Anomali skorunu ve eşiği hesaplar, 10/25/50/100 km kaydırma testini yapar, ROC/AUC çıkarır. |
| 4 | `.\.venv\Scripts\python model\donustur.py` | Modeli int8 LiteRT'ye dönüştürür, float32 ile RMSE farkını ölçer. |

Her betik `--veri`, `--istasyon` ve `--model`/`--cikti` seçeneklerini alır. Varsayılanlar `logs`, `model/istasyon.yaml` ve `output/gercek` klasörleridir.

`model/istasyon.yaml` dosyasında `enlem`, `boylam`, `zemin_rakimi_m` ve `anten_yerden_yukseklik_m` alanları bulunmalıdır. Pi'deki `config.yaml`'da `zemin_rakimi_m` yoksa önce oraya eklenmelidir.

## Sentetik deneme (gerçek veri olmadan)

```powershell
.\.venv\Scripts\python model\sentetik.py --cikti output\sentetik
.\.venv\Scripts\python model\egitim.py --veri output\sentetik\veri --istasyon output\sentetik\istasyon.yaml --cikti output\sentetik\model
.\.venv\Scripts\python model\degerlendirme.py --veri output\sentetik\veri --istasyon output\sentetik\istasyon.yaml --model output\sentetik\model
.\.venv\Scripts\python model\donustur.py --veri output\sentetik\veri --istasyon output\sentetik\istasyon.yaml --model output\sentetik\model
```

Sentetik veri uydurmadır. Yalnızca kodun çalıştığını gösterir, sonuçları raporda kullanılmaz.

## Dosyalar

| Dosya | İçerik |
|---|---|
| `ozellikler.py` | Mesafe, azimut, yükseklik açısı ve özellik matrisi. Pi'deki çıkarım servisi de bu dosyayı kullanacak. Yalnızca numpy ve pyyaml'a bağlıdır. |
| `veri_oku.py` | CSV okuma, filtreler (oturum 1, havada, RSSI > −49 dBFS, NIC ≥ 7, mesafe ≤ 450 km), iz bölme, güne göre ayırma |
| `egitim.py` | Baseline (en küçük kareler) ve MLP (13 → 32 → 16 → 1) |
| `degerlendirme.py` | 60 saniyelik pencere ortalaması, z-skoru, %1 yanlış alarm eşiği, sahte konum testi |
| `donustur.py` | int8 LiteRT dönüşümü ve karşılaştırma |
| `paket.py` | Kaydedilmiş modeli yükleyip tahmin yapar (keras ya da tflite) |
| `sentetik.py` | Deneme verisi üretir |

Çıktı klasörü (`output/gercek/`) şu dosyaları içerir: `normalizasyon.json`, `model.keras`, `model_int8.tflite`, `metrikler.json`, `degerlendirme.json`, `donusum.json`, `mesafe_rssi.png`, `yone_gore_hata.png`, `ogrenme_egrisi.png`, `roc.png`.
