"""
Sistem tepsisi (system tray) simgesi
====================================
Başlangıçta pencere açmadan sessizce çalışır; saat yanındaki simgeden
uygulamayı açmayı/kapatmayı sağlar.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
import pystray

ICON_PATH = Path(__file__).resolve().parent / "icon.ico"

# Çalışan tepsi simgesi — bildirim göndermek için tutulur.
_icon_ref: "pystray.Icon | None" = None


def notify(title: str, message: str) -> bool:
    """Windows bildirim balonu gösterir. Tepsi çalışmıyorsa False döner.
    Ekstre izleyicisi bunu kullanır (bkz. app/watcher.py)."""
    if _icon_ref is None:
        return False
    try:
        _icon_ref.notify(message, title)
        return True
    except Exception:
        return False


def _make_icon_image() -> Image.Image:
    """Uygulama simgesini (app/icon.ico) yükler. Yoksa app/make_icon.py ile üretir."""
    if not ICON_PATH.exists():
        try:
            from . import make_icon
            make_icon.main()
        except Exception:
            pass
    img = Image.open(ICON_PATH)
    return img.convert("RGBA")


def run_tray(on_open, on_quit=None):
    """Tepsi simgesini çalıştırır (bu çağrı bloklar — ana thread'de çalıştır)."""
    global _icon_ref
    icon = pystray.Icon("portfoy_danisman")
    icon.icon = _make_icon_image()
    icon.title = "Portföy Danışman"
    _icon_ref = icon

    def _open(_icon, _item):
        on_open()

    def _quit(_icon, _item):
        _icon.visible = False
        _icon.stop()
        if on_quit:
            on_quit()

    icon.menu = pystray.Menu(
        pystray.MenuItem("Aç / Göster", _open, default=True),
        pystray.MenuItem("Çıkış", _quit),
    )

    def _setup(ic):
        ic.visible = True
        try:
            ic.notify("Arka planda çalışıyor. Açmak için saat yanındaki bu simgeye tıkla "
                      "(gizliyse ^ okunun altına bak).", "Portföy Danışman")
        except Exception:
            pass

    icon.run(setup=_setup)
