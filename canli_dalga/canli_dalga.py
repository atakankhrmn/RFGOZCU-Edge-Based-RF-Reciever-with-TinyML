#!/usr/bin/env python3
"""Canlı IQ dalga görüntüleyici.

rtl_sdr'den sürekli ham örnek okur, saniyede ~10 kez son pencereyi
WebSocket ile tarayıcıya gönderir. Tarayıcıdan gelen ayarlarla
(merkez frekans, genişlik, kazanç) alıcıyı yeniden ayarlar.

Çalıştırma (Pi'de, readsb durdurulmuşken):
    python canli_dalga.py
Tarayıcı: http://rfgozcu.local:8080
"""
import asyncio
import json
from pathlib import Path

import numpy as np
from aiohttp import web

PORT = 8080
GECERLI_HIZLAR = [0.25, 1.024, 1.4, 1.8, 2.048, 2.4]          # MHz
GECERLI_KAZANCLAR = [0.0, 0.9, 1.4, 2.7, 3.7, 7.7, 8.7, 12.5, 14.4, 15.7,
                     16.6, 19.7, 20.7, 22.9, 25.4, 28.0, 29.7, 32.8, 33.8,
                     36.4, 37.2, 38.6, 40.2, 42.1, 43.4, 43.9, 44.5, 48.0, 49.6]
SURELER = [50, 100, 200, 500, 1000]                            # mikrosaniye
GONDERIM_ARALIGI = 0.1                                         # saniye

ayar = {"merkez": 433.92, "hiz": 2.048, "kazanc": 40.2, "sure": 200, "tetik": True}
durum = {"blok": None, "hata": None, "surum": 0}
istemciler = set()
surec = None
okuyucu = None


async def alici_durdur():
    global surec, okuyucu
    if okuyucu:
        okuyucu.cancel()
        okuyucu = None
    if surec and surec.returncode is None:
        surec.terminate()
        try:
            await asyncio.wait_for(surec.wait(), 3)
        except asyncio.TimeoutError:
            surec.kill()
    surec = None


async def alici_baslat():
    global surec, okuyucu
    await alici_durdur()
    durum.update(blok=None, hata=None)
    durum["surum"] += 1
    komut = ["rtl_sdr",
             "-f", str(int(ayar["merkez"] * 1e6)),
             "-s", str(int(ayar["hiz"] * 1e6)),
             "-g", str(ayar["kazanc"]), "-"]
    surec = await asyncio.create_subprocess_exec(
        *komut, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    okuyucu = asyncio.create_task(oku(surec))


async def oku(p):
    """Her seferinde ~0.1 s'lik veri okur; en son bloğu saklar."""
    blok_bayt = int(ayar["hiz"] * 1e6 * GONDERIM_ARALIGI) * 2
    ilk = True
    try:
        while True:
            ham = await p.stdout.readexactly(blok_bayt)
            if ilk:                      # açılıştaki geçiş verisini at
                ilk = False
                continue
            x = np.frombuffer(ham, dtype=np.uint8).astype(np.float32)
            x = (x - 127.5) / 127.5
            durum["blok"] = x[0::2] + 1j * x[1::2]
    except asyncio.IncompleteReadError:
        durum["hata"] = ("Alıcı açılamadı ya da kapandı. readsb veya başka bir "
                         "program alıcıyı kullanıyor olabilir: sudo systemctl stop readsb")
    except asyncio.CancelledError:
        pass


def pencere_sec(blok):
    n = int(ayar["sure"] * ayar["hiz"])          # µs × MHz = örnek sayısı
    n = max(16, min(n, len(blok)))
    if ayar["tetik"]:
        genlik = np.abs(blok)
        tepe = int(np.argmax(genlik))
        bas = min(max(0, tepe - n // 4), len(blok) - n)
    else:
        bas = len(blok) - n
    return blok[bas:bas + n]


async def gonderici(ws):
    while not ws.closed:
        await asyncio.sleep(GONDERIM_ARALIGI)
        if durum["hata"]:
            await ws.send_json({"hata": durum["hata"], "ayar": ayar})
            continue
        blok = durum["blok"]
        if blok is None:
            continue
        p = pencere_sec(blok)
        genlik = np.abs(blok)
        await ws.send_json({
            "ayar": ayar,
            "i": np.round(p.real, 4).tolist(),
            "q": np.round(p.imag, 4).tolist(),
            "tepe": round(float(genlik.max()), 4),
            "ortalama": round(float(genlik.mean()), 4),
        })


def ayar_dogrula(yeni):
    sonuc = dict(ayar)
    if "merkez" in yeni:
        m = float(yeni["merkez"])
        if not 24 <= m <= 1766:
            raise ValueError("Merkez frekans 24 ile 1766 MHz arasında olmalı.")
        sonuc["merkez"] = round(m, 4)
    if "hiz" in yeni:
        h = float(yeni["hiz"])
        if h not in GECERLI_HIZLAR:
            raise ValueError("Geçersiz genişlik.")
        sonuc["hiz"] = h
    if "kazanc" in yeni:
        k = float(yeni["kazanc"])
        if k not in GECERLI_KAZANCLAR:
            raise ValueError("Geçersiz kazanç.")
        sonuc["kazanc"] = k
    if "sure" in yeni:
        s = int(yeni["sure"])
        if s not in SURELER:
            raise ValueError("Geçersiz süre.")
        sonuc["sure"] = s
    if "tetik" in yeni:
        sonuc["tetik"] = bool(yeni["tetik"])
    return sonuc


async def ws_isleyici(request):
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    istemciler.add(ws)
    gorev = asyncio.create_task(gonderici(ws))
    try:
        async for mesaj in ws:
            if mesaj.type != web.WSMsgType.TEXT:
                continue
            try:
                yeni = ayar_dogrula(json.loads(mesaj.data))
            except (ValueError, json.JSONDecodeError) as e:
                await ws.send_json({"uyari": str(e)})
                continue
            yeniden = any(yeni[k] != ayar[k] for k in ("merkez", "hiz", "kazanc"))
            ayar.update(yeni)
            if yeniden:
                await alici_baslat()
    finally:
        gorev.cancel()
        istemciler.discard(ws)
    return ws


async def sayfa(request):
    return web.FileResponse(Path(__file__).with_name("index.html"))


async def secenekler(request):
    return web.json_response({"hizlar": GECERLI_HIZLAR, "kazanclar": GECERLI_KAZANCLAR,
                              "sureler": SURELER, "ayar": ayar})


async def acilis(app):
    await alici_baslat()


async def kapanis(app):
    await alici_durdur()


app = web.Application()
app.router.add_get("/", sayfa)
app.router.add_get("/secenekler", secenekler)
app.router.add_get("/ws", ws_isleyici)
app.on_startup.append(acilis)
app.on_cleanup.append(kapanis)

if __name__ == "__main__":
    print(f"Açılıyor: http://rfgozcu.local:{PORT}")
    web.run_app(app, port=PORT, print=None)
