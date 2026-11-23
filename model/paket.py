"""Eğitilmiş modeli ve normalizasyon değerlerini yükleyip tahmin yapar.

Tek bir klasörde durur:
    normalizasyon.json   özellik adları, x/y ortalama ve std, baseline katsayıları
    model.keras          float32 MLP (eğitim bilgisayarında)
    model_int8.tflite    Pi'ye gidecek int8 model
"""
import json
from pathlib import Path

import numpy as np

import ozellikler as oz


class Paket:
    def __init__(self, klasor, tur="keras"):
        self.klasor = Path(klasor)
        self.norm = json.loads((self.klasor / "normalizasyon.json").read_text(encoding="utf-8"))
        if self.norm["ozellik_adlari"] != oz.OZELLIK_ADLARI:
            raise ValueError("Modelin özellik listesi ozellikler.py ile uyuşmuyor")
        self.x_ort = np.array(self.norm["x_ort"], np.float32)
        self.x_std = np.array(self.norm["x_std"], np.float32)
        self.tur = tur
        self._model = None
        self._yorumlayici = None

    # --- baseline: RSSI = a - 10 n log10(d_km)
    def baseline(self, X):
        b = self.norm["baseline"]
        return b["a"] - 10 * b["n"] * X[:, 0]

    def _normalize(self, X):
        return ((X - self.x_ort) / self.x_std).astype(np.float32)

    def mlp(self, X):
        Xn = self._normalize(X)
        if self.tur == "keras":
            if self._model is None:
                import keras
                self._model = keras.models.load_model(self.klasor / "model.keras")
            yn = self._model.predict(Xn, batch_size=4096, verbose=0).ravel()
        else:
            yn = self._tflite(Xn)
        return yn * self.norm["y_std"] + self.norm["y_ort"]

    def _tflite(self, Xn):
        if self._yorumlayici is None:
            try:
                from ai_edge_litert.interpreter import Interpreter
            except ImportError:
                import tensorflow as tf
                Interpreter = tf.lite.Interpreter
            self._yorumlayici = Interpreter(model_path=str(self.klasor / "model_int8.tflite"))
            self._yorumlayici.allocate_tensors()
        y = self._yorumlayici
        g, c = y.get_input_details()[0], y.get_output_details()[0]
        cikis = np.empty(len(Xn), np.float32)
        for i in range(len(Xn)):           # model tek satır girdiyle dönüştürüldü
            x = Xn[i:i + 1]
            if g["dtype"] == np.int8:
                s, z = g["quantization"]
                x = np.clip(np.round(x / s + z), -128, 127).astype(np.int8)
            y.set_tensor(g["index"], x)
            y.invoke()
            o = y.get_tensor(c["index"])
            if c["dtype"] == np.int8:
                s, z = c["quantization"]
                o = (o.astype(np.float32) - z) * s
            cikis[i] = o.ravel()[0]
        return cikis
