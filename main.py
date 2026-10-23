"""
BIST Portföy Danışman — Masaüstü Uygulaması
===========================================
Kullanım:
  python main.py            -> Sunucuyu başlatır ve uygulama PENCERESİNİ açar.
  python main.py --tray     -> Pencere açmadan SESSİZCE çalışır; sistem tepsisine
                               (saat yanına) yerleşir. Simgeden açabilir/çıkabilirsin.

Her şey kendi bilgisayarında, lokal çalışır. İnternete yalnızca halka açık
fiyat verisini OKUMAK için çıkar; hiçbir kişisel veri dışarı gönderilmez.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

PORT = 8765
URL = f"http://127.0.0.1:{PORT}"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class _ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    """Aynı anda birden çok isteğe yanıt verir — pencere, yavaş veri çekimi
    sürerken bile anında açılır ve kilitlenmez."""
    daemon_threads = True


# --------------------------------------------------------------------------- #
#  Sunucu yardımcıları
# --------------------------------------------------------------------------- #
def _start_server():
    from app.server import app
    httpd = make_server("127.0.0.1", PORT, app, server_class=_ThreadingWSGIServer)
    httpd.serve_forever()


def _already_running() -> bool:
    """Sunucu zaten açıksa (port dolu) True döner."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def _ensure_server():
    """Sunucu çalışmıyorsa bu süreçte (arka planda) başlatır ve ayağa kalkmasını bekler."""
    if _already_running():
        return
    threading.Thread(target=_start_server, daemon=True).start()
    for _ in range(25):
        if _already_running():
            return
        time.sleep(0.2)


def _start_watcher():
    """Ekstre izleyicisini başlatır; bildirimi Windows bildirim balonuyla verir."""
    try:
        from app import watcher
    except Exception as e:
        print(f"[bilgi] ekstre izleyicisi başlatılamadı: {e}")
        return

    def notify(title, message):
        try:
            from app.tray import notify as tray_notify
            tray_notify(title, message)
        except Exception:
            print(f"[ekstre] {title}: {message}")

    watcher.start(notify=notify)


# --------------------------------------------------------------------------- #
#  Pencere
# --------------------------------------------------------------------------- #
def open_window():
    """Native uygulama penceresini açar (bu çağrı, pencere kapanana kadar bloklar)."""
    try:
        import webview
        webview.create_window("BIST Portföy Danışman", URL,
                              width=1180, height=820, min_size=(900, 640))
        webview.start()
    except Exception as e:
        print(f"[bilgi] pencere açılamadı ({e}); tarayıcıda açılıyor.")
        import webbrowser
        webbrowser.open(URL)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


def spawn_window():
    """Ayrı bir süreçte uygulama penceresini açar (tepsi 'Aç' için).
    Çalışan sunucuyu yeniden başlatmaz; sadece pencereyi gösterir."""
    subprocess.Popen([sys.executable, os.path.join(BASE_DIR, "main.py")], cwd=BASE_DIR)


# --------------------------------------------------------------------------- #
#  Giriş
# --------------------------------------------------------------------------- #
def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass

    tray_mode = "--tray" in sys.argv[1:]

    if tray_mode:
        # Sessiz mod: sunucuyu arka planda başlat, tepsiye yerleş, pencere AÇMA.
        _ensure_server()
        from app.tray import run_tray
        # Ekstre izleyicisi yalnızca tepsi modunda çalışır: sürekli açık olan
        # süreç burasıdır, pencere kapansa da arka planda dinlemeye devam eder.
        _start_watcher()
        run_tray(on_open=spawn_window, on_quit=lambda: os._exit(0))
    else:
        # Pencere modu: sunucuyu (gerekiyorsa) başlat ve pencereyi aç.
        _ensure_server()
        open_window()


if __name__ == "__main__":
    main()
