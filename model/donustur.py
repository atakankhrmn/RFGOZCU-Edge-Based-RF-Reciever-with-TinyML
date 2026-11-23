"""MLP'yi int8 LiteRT (TensorFlow Lite) modeline dönüştürür ve float32 ile karşılaştırır.

Ağırlıklar ve ara değerler int8'dir; girdi/çıktı float32 kalır (Pi'deki servis
normalize edilmiş özellik verir, normalize edilmiş RSSI alır).
Temsilî veri olarak eğitim günlerinden rastgele 2000 satır kullanılır.

Kullanım:
    .venv\\Scripts\\python model\\donustur.py --veri logs --istasyon model\\istasyon.yaml --model output\\gercek
"""
import argparse
import json
import os
import time
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np

import ozellikler as oz
import veri_oku
from paket import Paket

TOHUM = 3


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--veri", default="logs")
    p.add_argument("--istasyon", default="model/istasyon.yaml")
    p.add_argument("--model", default="output/gercek")
    p.add_argument("--test_satir", type=int, default=5000)
    a = p.parse_args()
    import keras
    import tensorflow as tf

    klasor = Path(a.model)
    paket = Paket(klasor)
    df, _ = veri_oku.oku(a.veri, oz.istasyon_oku(a.istasyon))
    rng = np.random.default_rng(TOHUM)
    egitim = df[df["gun"].isin(paket.norm["gunler"]["egitim"])]
    test = df[df["gun"].isin(paket.norm["gunler"]["test"])]
    temsil = paket._normalize(egitim[oz.OZELLIK_ADLARI].to_numpy(np.float32))
    temsil = temsil[rng.choice(len(temsil), min(2000, len(temsil)), replace=False)]

    model = keras.models.load_model(klasor / "model.keras")
    giris = tf.TensorSpec([1, len(oz.OZELLIK_ADLARI)], tf.float32)
    kayit = klasor / "_savedmodel"
    model.export(str(kayit), format="tf_saved_model", input_signature=[giris], verbose=False)

    def donusturucu_kur():
        return tf.lite.TFLiteConverter.from_saved_model(str(kayit))

    donusturucu = donusturucu_kur()
    donusturucu.optimizations = [tf.lite.Optimize.DEFAULT]
    donusturucu.representative_dataset = lambda: ([temsil[i:i + 1]] for i in range(len(temsil)))
    donusturucu.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    tflite = donusturucu.convert()
    (klasor / "model_int8.tflite").write_bytes(tflite)

    # float32 tflite da üret: boyut karşılaştırması için
    d32 = donusturucu_kur()
    (klasor / "model_float32.tflite").write_bytes(d32.convert())

    # --- karşılaştırma (test günlerinden örnek)
    ornek = test.sample(min(a.test_satir, len(test)), random_state=TOHUM)
    X = ornek[oz.OZELLIK_ADLARI].to_numpy(np.float32)
    y = ornek["rssi_dbfs"].to_numpy(np.float32)
    t_float = paket.mlp(X)
    paket8 = Paket(klasor, tur="tflite")
    bas = time.perf_counter()
    t_int8 = paket8.mlp(X)
    sure_us = (time.perf_counter() - bas) / len(X) * 1e6

    def rmse(u, v):
        return float(np.sqrt(np.mean((u - v) ** 2)))

    sonuc = {
        "boyut_bayt": {"keras": (klasor / "model.keras").stat().st_size,
                       "tflite_float32": (klasor / "model_float32.tflite").stat().st_size,
                       "tflite_int8": len(tflite)},
        "test_satir": int(len(X)),
        "rmse_float32_db": rmse(y, t_float),
        "rmse_int8_db": rmse(y, t_int8),
        "rmse_kaybi_db": rmse(y, t_int8) - rmse(y, t_float),
        "float_int8_ortalama_fark_db": float(np.mean(np.abs(t_float - t_int8))),
        "cikarim_us_bu_bilgisayar": sure_us,
    }
    (klasor / "donusum.json").write_text(json.dumps(sonuc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(sonuc, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
