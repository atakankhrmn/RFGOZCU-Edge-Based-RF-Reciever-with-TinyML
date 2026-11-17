# rtl_sdr ile alınan ham IQ kaydından zaman alanı dalga grafiği çizer.
# Kullanım: python dalga.py ornek.bin --merkez 100.0 --hiz 2.048 --sure 200
import argparse
import numpy as np
import matplotlib.pyplot as plt

p = argparse.ArgumentParser()
p.add_argument("dosya")
p.add_argument("--merkez", type=float, required=True, help="Merkez frekans (MHz)")
p.add_argument("--hiz", type=float, required=True, help="Örnekleme hızı (MHz) = görülen bant genişliği")
p.add_argument("--sure", type=float, default=200, help="Gösterilecek süre (mikrosaniye)")
p.add_argument("--atla", type=int, default=4096, help="Baştan atlanacak örnek (açılış geçişi)")
a = p.parse_args()

ham = np.fromfile(a.dosya, dtype=np.uint8).astype(np.float32)
iq = (ham[0::2] - 127.5) / 127.5 + 1j * (ham[1::2] - 127.5) / 127.5
iq = iq[a.atla:]

n = max(10, int(a.sure * a.hiz))           # mikrosaniye × MHz = örnek sayısı
iq = iq[:n]
t = np.arange(len(iq)) / a.hiz             # mikrosaniye

alt_f, ust_f = a.merkez - a.hiz / 2, a.merkez + a.hiz / 2
fig, (ust, alt) = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
ust.plot(t, iq.real, lw=0.8, label="I (gerçek kısım)")
ust.plot(t, iq.imag, lw=0.8, label="Q (sanal kısım)", alpha=0.8)
ust.set_ylabel("Genlik")
ust.set_title(f"Zaman alanı sinyal: {alt_f:.3f}–{ust_f:.3f} MHz (merkez {a.merkez} MHz)")
ust.legend(loc="upper right")
ust.grid(alpha=0.3)
alt.plot(t, np.abs(iq), lw=0.8, color="tab:red")
alt.set_ylabel("Genlik |IQ|")
alt.set_xlabel("Zaman (µs)")
alt.grid(alpha=0.3)
plt.tight_layout()
cikti = a.dosya.rsplit(".", 1)[0] + "_dalga.png"
plt.savefig(cikti, dpi=150)
print("Kaydedildi:", cikti)
