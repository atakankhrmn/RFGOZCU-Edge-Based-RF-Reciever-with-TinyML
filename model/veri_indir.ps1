# RF Gözcü: Drive'daki günlük veriyi ve istasyon bilgisini Pi üzerinden bilgisayara alır.
#
# Bilgisayardaki rclone'un ayrı bir Google iznine ihtiyacı olmasın diye Pi'deki
# rclone kullanılır. Dosyalar Pi'de RAM'deki /dev/shm klasörüne iner (SD karta
# yazılmaz), scp ile bilgisayara gelir, sonra /dev/shm temizlenir.
# Pi'deki ~/rfgozcu/data klasörüne DOKUNULMAZ.
#
# Kullanım (proje klasöründe):
#   powershell -ExecutionPolicy Bypass -File model\veri_indir.ps1
#   powershell -ExecutionPolicy Bypass -File model\veri_indir.ps1 -Pi "rfgozcu@fe80::da3a:ddff:fe3b:6cfa%12"

param(
    [string]$Pi = "rfgozcu@rfgozcu.local",
    [string]$Hedef = "logs"
)
$ErrorActionPreference = "Stop"
$Proje = Split-Path -Parent $PSScriptRoot
$HedefYol = Join-Path $Proje $Hedef
New-Item -ItemType Directory -Force $HedefYol | Out-Null

# scp, IPv6 adresini köşeli parantez içinde ister
$Kullanici, $Adres = $Pi -split "@", 2
$ScpPi = if ($Adres -match ":") { "$Kullanici@[$Adres]" } else { $Pi }

Write-Host "1/3 Drive'daki dosyalar Pi'nin RAM'ine (/dev/shm) indiriliyor..."
ssh $Pi "rm -rf /dev/shm/rfg_indir && mkdir -p /dev/shm/rfg_indir && rclone copy gdrive:rf-gozcu/logs /dev/shm/rfg_indir --include '*.csv.gz' && ls /dev/shm/rfg_indir | wc -l"
if ($LASTEXITCODE -ne 0) { throw "Pi'de rclone başarısız (Drive izni dolmuş olabilir: rclone config reconnect gdrive:)" }

Write-Host "2/3 Dosyalar bilgisayara kopyalanıyor -> $HedefYol"
scp -q "${ScpPi}:/dev/shm/rfg_indir/*.csv.gz" "$HedefYol\"
$scpKod = $LASTEXITCODE
ssh $Pi "rm -rf /dev/shm/rfg_indir"
if ($scpKod -ne 0) { throw "scp başarısız" }

Write-Host "3/3 İstasyon bilgisi alınıyor -> model\istasyon.yaml (yalnızca istasyon bloğu; ekrana yazılmaz)"
$py = "import os,sys,yaml`na=yaml.safe_load(open(os.path.expanduser('~/rfgozcu/kaydedici/config.yaml')))`nsys.stdout.write(yaml.safe_dump({'istasyon': a.get('istasyon') or {}}))`n"
$yaml = $py | ssh $Pi "~/rfgozcu/venv/bin/python -"
if ($LASTEXITCODE -ne 0) { throw "config.yaml okunamadı" }
[System.IO.File]::WriteAllText((Join-Path $Proje "model\istasyon.yaml"), ($yaml -join "`n") + "`n", (New-Object System.Text.UTF8Encoding $false))

$dosyalar = Get-ChildItem $HedefYol -Filter *.csv.gz
Write-Host ("Tamam: {0} gün, toplam {1:N1} MB" -f $dosyalar.Count, (($dosyalar | Measure-Object Length -Sum).Sum / 1MB))
