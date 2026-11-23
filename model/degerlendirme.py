"""Anomali skoru, eşik seçimi ve sahte konum (spoofing) değerlendirmesi.

1. Her satır için artık = ölçülen RSSI − beklenen RSSI.
2. Her uçak izinde son 60 saniyenin ortalama artığı alınır (en az MIN_SATIR satır).
3. Bu ortalama, doğrulama günlerindeki dağılıma göre z-skoruna çevrilir; skor = |z|.
4. Eşik: doğrulama günlerinde pencerelerin ~%1'i alarm verecek şekilde seçilir.
5. Test günlerinde her iz rastgele bir yönde 10/25/50/100 km kaydırılır, RSSI
   aynı kalır. Baseline ve MLP için yakalama oranı ve ROC/AUC hesaplanır.
6. Ek kontrol: NIC'i düşük uçakların skor dağılımı.

Kullanım:
    .venv\\Scripts\\python model\\degerlendirme.py --veri logs --istasyon model\\istasyon.yaml --model output\\gercek
"""
import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, roc_curve

import ozellikler as oz
import veri_oku
from paket import Paket

PENCERE = "60s"
MIN_SATIR = 6            # 5 sn'de bir satır → en az ~30 sn veri
YANLIS_ALARM = 0.01
KAYDIRMALAR_KM = [10, 25, 50, 100]
TOHUM = 7


def pencere_ortalamasi(df, artik):
    """Her satır için o uçağın son 60 sn'lik ortalama artığı (yeterli satır yoksa NaN)."""
    t = pd.DataFrame({"iz": df["iz"].to_numpy(), "zaman": df["zaman"].to_numpy(),
                      "artik": artik})
    t = t.sort_values(["iz", "zaman"])
    g = t.set_index("zaman").groupby("iz")["artik"].rolling(PENCERE)
    ort = g.mean().to_numpy()
    say = g.count().to_numpy()
    sonuc = np.where(say >= MIN_SATIR, ort, np.nan)
    # rolling sonucu iz+zaman sırasında; orijinal sıraya geri koy
    cikis = np.empty(len(t)); cikis[t.index.to_numpy()] = sonuc
    return cikis


def tahmin_et(paket, X, yontem):
    return paket.baseline(X) if yontem == "baseline" else paket.mlp(X)


def kaydirilmis_ozellikler(df, istasyon, km, rng):
    """Her izi kendi rastgele yönünde `km` kaydırır; özellikleri yeniden hesaplar."""
    izler = df["iz"].unique()
    yonler = pd.Series(rng.uniform(0, 360, len(izler)), index=izler)
    yon = yonler.loc[df["iz"]].to_numpy()
    e, b = oz.kaydir(df["enlem"].to_numpy(), df["boylam"].to_numpy(), km, yon)
    X, mesafe = oz.ozellik_matrisi(e, b, df["irtifa_m"].to_numpy(),
                                   df["kategori"].to_numpy(), istasyon)
    return X, mesafe


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--veri", default="logs")
    p.add_argument("--istasyon", default="model/istasyon.yaml")
    p.add_argument("--model", default="output/gercek")
    a = p.parse_args()
    klasor = Path(a.model)
    istasyon = oz.istasyon_oku(a.istasyon)
    paket = Paket(klasor)
    gunler = paket.norm["gunler"]

    tum, _ = veri_oku.oku(a.veri, istasyon, min_nic=None)
    dusuk_nic = tum[(tum["nic"] < 7) & tum["gun"].isin(gunler["test"])].reset_index(drop=True)
    df = tum[tum["nic"] >= 7]
    dog = df[df["gun"].isin(gunler["dogrulama"])].reset_index(drop=True)
    test = df[df["gun"].isin(gunler["test"])].reset_index(drop=True)

    sonuc = {"pencere": PENCERE, "min_satir": MIN_SATIR, "hedef_yanlis_alarm": YANLIS_ALARM}
    roc_veri = {}
    for yontem in ["baseline", "mlp"]:
        # --- doğrulama: z-skoru parametreleri ve eşik
        X = dog[oz.OZELLIK_ADLARI].to_numpy(np.float32)
        p_dog = pencere_ortalamasi(dog, dog["rssi_dbfs"].to_numpy() - tahmin_et(paket, X, yontem))
        p_dog = p_dog[np.isfinite(p_dog)]
        mu, sd = float(p_dog.mean()), float(p_dog.std())
        esik = float(np.quantile(np.abs((p_dog - mu) / sd), 1 - YANLIS_ALARM))

        def skor(tablo, Xk):
            ort = pencere_ortalamasi(tablo, tablo["rssi_dbfs"].to_numpy() - tahmin_et(paket, Xk, yontem))
            ort = ort[np.isfinite(ort)]
            return np.abs((ort - mu) / sd)

        s_normal = skor(test, test[oz.OZELLIK_ADLARI].to_numpy(np.float32))
        r = {"z_ort": mu, "z_std": sd, "esik_abs_z": esik,
             "test_yanlis_alarm": float((s_normal > esik).mean()),
             "test_normal_pencere": int(len(s_normal)), "kaydirma": {}}
        rng = np.random.default_rng(TOHUM)          # iki yöntem aynı yönleri görür
        for km in KAYDIRMALAR_KM:
            Xs, _ = kaydirilmis_ozellikler(test, istasyon, km, rng)
            s_sahte = skor(test, Xs)
            etiket = np.r_[np.zeros(len(s_normal)), np.ones(len(s_sahte))]
            skorlar = np.r_[s_normal, s_sahte]
            r["kaydirma"][f"{km}km"] = {"yakalama": float((s_sahte > esik).mean()),
                                         "auc": float(roc_auc_score(etiket, skorlar))}
            roc_veri[(yontem, km)] = roc_curve(etiket, skorlar)[:2]
        if len(dusuk_nic):
            s_nic = skor(dusuk_nic, dusuk_nic[oz.OZELLIK_ADLARI].to_numpy(np.float32))
            r["dusuk_nic"] = {"pencere": int(len(s_nic)),
                              "alarm_orani": float((s_nic > esik).mean()) if len(s_nic) else None,
                              "ort_abs_z": float(s_nic.mean()) if len(s_nic) else None}
        sonuc[yontem] = r

    (klasor / "degerlendirme.json").write_text(json.dumps(sonuc, indent=2, ensure_ascii=False),
                                               encoding="utf-8")
    # ROC grafiği
    fig, eksen = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    for ax, yontem in zip(eksen, ["baseline", "mlp"]):
        for km in KAYDIRMALAR_KM:
            fpr, tpr = roc_veri[(yontem, km)]
            ax.plot(fpr, tpr, label=f"{km} km (AUC {sonuc[yontem]['kaydirma'][f'{km}km']['auc']:.3f})")
        ax.plot([0, 1], [0, 1], "k:", lw=0.7)
        ax.set_title(yontem.upper() if yontem == "mlp" else "Baseline")
        ax.set_xlabel("yanlış alarm oranı"); ax.legend(loc="lower right")
    eksen[0].set_ylabel("yakalama oranı")
    fig.tight_layout(); fig.savefig(klasor / "roc.png", dpi=130); plt.close(fig)

    print(f"{'':<10}{'eşik |z|':>9}{'test YA':>9}" + "".join(f"{f'{k} km':>16}" for k in KAYDIRMALAR_KM))
    for yontem in ["baseline", "mlp"]:
        r = sonuc[yontem]
        print(f"{yontem:<10}{r['esik_abs_z']:>9.2f}{r['test_yanlis_alarm']:>9.3f}" + "".join(
            f"{r['kaydirma'][f'{k}km']['yakalama']:>8.2f} /{r['kaydirma'][f'{k}km']['auc']:.3f}"
            for k in KAYDIRMALAR_KM))
    print("(sütunlar: yakalama oranı / AUC;  YA = yanlış alarm)")
    for yontem in ["baseline", "mlp"]:
        if "dusuk_nic" in sonuc[yontem]:
            print(f"Düşük NIC ({yontem}):", sonuc[yontem]["dusuk_nic"])


if __name__ == "__main__":
    main()
