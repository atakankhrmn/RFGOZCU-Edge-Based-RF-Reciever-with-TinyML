"""Baseline (log-mesafe yol kaybı) ve küçük MLP eğitimi.

Veri güne göre ayrılır (eğitim / doğrulama / test). Çıktı klasörüne:
    normalizasyon.json, model.keras, metrikler.json ve grafikler yazılır.

Kullanım:
    .venv\\Scripts\\python model\\egitim.py --veri logs --istasyon model\\istasyon.yaml --cikti output\\gercek
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

import ozellikler as oz
import veri_oku

TOHUM = 42


def rmse(a, b):
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


def baseline_uydur(log_d, y):
    """En küçük kareler: y = a + b*log10(d)  →  n = -b/10."""
    A = np.column_stack([np.ones_like(log_d), log_d])
    (a, b), *_ = np.linalg.lstsq(A, y, rcond=None)
    return {"a": float(a), "n": float(-b / 10)}


def mlp_kur(girdi_boyutu):
    import keras
    keras.utils.set_random_seed(TOHUM)
    model = keras.Sequential([
        keras.Input(shape=(girdi_boyutu,)),
        keras.layers.Dense(32, activation="relu"),
        keras.layers.Dense(16, activation="relu"),
        keras.layers.Dense(1),
    ])
    model.compile(optimizer=keras.optimizers.Adam(1e-3), loss="mse")
    return model


def grafikler(cikti, df, parcalar, tahmin_b, tahmin_m, gecmis):
    test = df[df["gun"].isin(parcalar["test"])]
    # 1) mesafe - RSSI ve baseline eğrisi
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ornek = df.sample(min(len(df), 30000), random_state=TOHUM)
    ax.scatter(ornek["mesafe_km"], ornek["rssi_dbfs"], s=2, alpha=0.15, label="ölçüm")
    d = np.linspace(max(df["mesafe_km"].min(), 1), df["mesafe_km"].max(), 200)
    b = json.loads((cikti / "normalizasyon.json").read_text(encoding="utf-8"))["baseline"]
    ax.plot(d, b["a"] - 10 * b["n"] * np.log10(d), "r", label=f"baseline (n={b['n']:.2f})")
    ax.set_xscale("log"); ax.set_xlabel("mesafe (km)"); ax.set_ylabel("RSSI (dBFS)")
    ax.legend(); ax.set_title("Mesafe – RSSI"); fig.tight_layout()
    fig.savefig(cikti / "mesafe_rssi.png", dpi=130); plt.close(fig)

    # 2) yöne göre ortalama hata (test günleri)
    az = (np.degrees(np.arctan2(test["sin_azimut"], test["cos_azimut"])) % 360).to_numpy()
    kutu = (az // 15).astype(int)
    hata_b = test["rssi_dbfs"].to_numpy() - tahmin_b
    hata_m = test["rssi_dbfs"].to_numpy() - tahmin_m
    merkez = np.arange(24) * 15 + 7.5
    ort_b = [hata_b[kutu == k].mean() if (kutu == k).any() else np.nan for k in range(24)]
    ort_m = [hata_m[kutu == k].mean() if (kutu == k).any() else np.nan for k in range(24)]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(merkez, ort_b, "o-", label="baseline")
    ax.plot(merkez, ort_m, "s-", label="MLP")
    ax.axhline(0, color="k", lw=0.7)
    ax.set_xlabel("azimut (°, kuzey=0)"); ax.set_ylabel("ortalama hata (ölçülen − beklenen, dB)")
    ax.set_title("Yöne göre hata (test günleri)"); ax.legend(); fig.tight_layout()
    fig.savefig(cikti / "yone_gore_hata.png", dpi=130); plt.close(fig)

    # 3) öğrenme eğrisi
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.plot(gecmis["loss"], label="eğitim"); ax.plot(gecmis["val_loss"], label="doğrulama")
    ax.set_xlabel("epoch"); ax.set_ylabel("MSE (normalize)"); ax.legend(); fig.tight_layout()
    fig.savefig(cikti / "ogrenme_egrisi.png", dpi=130); plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--veri", default="logs")
    p.add_argument("--istasyon", default="model/istasyon.yaml")
    p.add_argument("--cikti", default="output/gercek")
    p.add_argument("--epoch", type=int, default=200)
    a = p.parse_args()
    cikti = Path(a.cikti); cikti.mkdir(parents=True, exist_ok=True)

    df, sayac = veri_oku.oku(a.veri, oz.istasyon_oku(a.istasyon))
    parcalar = veri_oku.gune_gore_ayir(df)
    X = df[oz.OZELLIK_ADLARI].to_numpy(np.float32)
    y = df["rssi_dbfs"].to_numpy(np.float32)
    maske = {k: df["gun"].isin(v).to_numpy() for k, v in parcalar.items()}
    print({k: f"{len(v)} gün, {maske[k].sum():,} satır" for k, v in parcalar.items()})

    # --- baseline
    baseline = baseline_uydur(X[maske["egitim"], 0], y[maske["egitim"]])

    # --- normalizasyon (yalnızca eğitim verisinden)
    x_ort = X[maske["egitim"]].mean(0)
    x_std = X[maske["egitim"]].std(0)
    x_std[x_std < 1e-6] = 1.0
    # kategori (one-hot) sütunları 0/1 kalır: normalize edilince seyrek kategoriler
    # ~15 gibi büyük değerler alıp int8 aralığını gereksiz yere genişletiyor
    for i, ad in enumerate(oz.OZELLIK_ADLARI):
        if ad.startswith("kat_"):
            x_ort[i], x_std[i] = 0.0, 1.0
    y_ort, y_std = float(y[maske["egitim"]].mean()), float(y[maske["egitim"]].std())
    norm = {"ozellik_adlari": oz.OZELLIK_ADLARI, "x_ort": x_ort.tolist(), "x_std": x_std.tolist(),
            "y_ort": y_ort, "y_std": y_std, "baseline": baseline, "gunler": parcalar,
            "filtreler": sayac}
    (cikti / "normalizasyon.json").write_text(json.dumps(norm, indent=2, ensure_ascii=False),
                                              encoding="utf-8")

    def hazirla(k):
        return ((X[maske[k]] - x_ort) / x_std).astype(np.float32), \
               ((y[maske[k]] - y_ort) / y_std).astype(np.float32)

    import keras
    model = mlp_kur(X.shape[1])
    Xe, ye = hazirla("egitim"); Xd, yd = hazirla("dogrulama")
    gecmis = model.fit(
        Xe, ye, validation_data=(Xd, yd), epochs=a.epoch, batch_size=512, verbose=2,
        callbacks=[keras.callbacks.EarlyStopping(patience=10, restore_best_weights=True),
                   keras.callbacks.ReduceLROnPlateau(patience=4, factor=0.5)])
    model.save(cikti / "model.keras")

    # --- metrikler
    metrik = {"baseline": baseline}
    tahminler = {}
    for k in parcalar:
        Xk, _ = hazirla(k)
        tm = model.predict(Xk, batch_size=4096, verbose=0).ravel() * y_std + y_ort
        tb = baseline["a"] - 10 * baseline["n"] * X[maske[k], 0]
        tahminler[k] = (tb, tm)
        metrik[k] = {"satir": int(maske[k].sum()),
                     "rmse_baseline_db": rmse(y[maske[k]], tb),
                     "rmse_mlp_db": rmse(y[maske[k]], tm),
                     "rmse_sabit_ortalama_db": rmse(y[maske[k]], np.full_like(tm, y_ort))}
    metrik["parametre_sayisi"] = int(model.count_params())
    (cikti / "metrikler.json").write_text(json.dumps(metrik, indent=2, ensure_ascii=False),
                                          encoding="utf-8")
    grafikler(cikti, df, parcalar, *tahminler["test"], gecmis.history)

    print(f"\nBaseline: a = {baseline['a']:.2f} dBFS, n = {baseline['n']:.2f}")
    print(f"{'küme':<10}{'satır':>9}{'sabit':>9}{'baseline':>10}{'MLP':>8}   (RMSE, dB)")
    for k in parcalar:
        m = metrik[k]
        print(f"{k:<10}{m['satir']:>9,}{m['rmse_sabit_ortalama_db']:>9.2f}"
              f"{m['rmse_baseline_db']:>10.2f}{m['rmse_mlp_db']:>8.2f}")
    print(f"MLP parametre sayısı: {metrik['parametre_sayisi']}  |  çıktı: {cikti}")


if __name__ == "__main__":
    main()
