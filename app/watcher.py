"""
Arka plan ekstre izleyicisi
===========================
Tepsi modunda çalışırken posta kutusunu belirli aralıklarla yoklar; Midas'tan
yeni bir ekstre geldiğinde portföyü kendiliğinden günceller ve bildirim verir.

NE OTOMATİK UYGULANIR, NE UYGULANMAZ
  Otomatik : pozisyon ekleme/güncelleme, nakit, gerçekleşmiş K/Z
             (bunlar ekstrenin kendi "PORTFÖY ÖZETİ" tablosundan gelir, kesindir)
  Elde kalır: POZİSYON KAPATMA (`close`) — ekstre bayatsa var olan bir varlığı
             yanlışlıkla silebilir. Bunlar kullanıcı onayına bırakılır ve
             bildirimde "N değişiklik onay bekliyor" diye söylenir.
  Ayrıca `reconcile` ekstre tarihinden sonra eklenen varlıkları hiç değerlendirmez.

Her otomatik güncellemeden ÖNCE portföyün yedeği alınır (portfolio.backup.json),
tek tıkla geri alınabilir.

Sadece stdlib + mevcut modüller; yeni bağımlılık yok.
"""

from __future__ import annotations

import threading
import time
import traceback

from . import assistant, mailbox, reconcile
from .portfolio import backup_portfolio, load_portfolio, save_portfolio
from .statement import parse_statement

DEFAULT_INTERVAL = 8 * 3600       # 8 saat — ekstre günde en fazla birkaç kez gelir
_state = {
    "running": False,
    "last_seen": None,            # işlenen son e-postanın kimliği (konu+tarih)
    "last_result": None,          # arayüzde gösterilecek son sonuç özeti
    "last_error": None,
    "last_check": None,
}


def status() -> dict:
    s = assistant._load_secrets()
    return {
        "enabled": bool(s.get("auto_sync")),
        "interval": int(s.get("auto_sync_interval") or DEFAULT_INTERVAL),
        "running": _state["running"],
        "last_check": _state["last_check"],
        "last_result": _state["last_result"],
        "last_error": _state["last_error"],
    }


def set_enabled(on: bool, interval: int | None = None) -> None:
    s = assistant._load_secrets()
    s["auto_sync"] = bool(on)
    if interval:
        s["auto_sync_interval"] = max(60, int(interval))
    assistant._save_secrets(s)


def clear_error() -> None:
    """Ayarlar değiştiğinde eski hatayı düşür — kullanıcı düzeltmiş olabilir."""
    _state["last_error"] = None


def check_once(notify=None, force: bool = False) -> dict:
    """Bir kez kontrol eder. Yeni ekstre varsa güvenli değişiklikleri uygular.

    `force=True`: kullanıcı "Portföyü güncelle" düğmesine bastığında kullanılır —
    aynı e-posta daha önce işlenmiş olsa bile yeniden mutabakat yapar (kullanıcı
    bu arada elle değişiklik yapmış olabilir).

    Dönen: {"new": bool, "applied": [...], "pending": [...], "as_of": ...}
    """
    s = assistant._load_secrets()
    cfg = s.get("imap") or {}
    _state["last_check"] = time.strftime("%d.%m.%Y %H:%M")
    if not (cfg.get("email") and cfg.get("password")):
        raise RuntimeError("E-posta ayarları tanımlı değil.")

    found = mailbox.fetch_latest_statement(cfg)
    # Buraya gelindiyse ayarlar geçerli ve bağlantı kuruldu. Eski hatayı BURADA
    # temizle: yalnızca en sonda temizlemek, "yeni e-posta yok" diye erken dönen
    # turlarda bayat hatanın arayüzde sonsuza kadar asılı kalmasına yol açıyordu.
    _state["last_error"] = None
    ident = f"{found.get('date')}|{found.get('subject')}|{len(found.get('data') or b'')}"
    if not force and ident == _state["last_seen"]:
        return {"new": False}                     # aynı e-posta, iş yok
    parsed = parse_statement(found["data"])

    portfolio = load_portfolio()
    d = reconcile.diff(parsed, portfolio)
    auto = [c for c in d["changes"] if c["kind"] != "close" and c["onerilen"]]
    # Eski ekstre (bkz. reconcile "stale"): hiçbir şey uygulanmaz, önerileri
    # "onay bekliyor" diye de bildirilmez — kullanıcıyı yanlış onaya itmesin.
    pending = [] if d.get("stale") else [c for c in d["changes"] if c not in auto]

    if auto:
        backup_portfolio()                        # geri alınabilsin
        save_portfolio(reconcile.apply(portfolio, parsed, [c["id"] for c in auto]))

    _state["last_seen"] = ident
    result = {
        "new": True, "as_of": parsed.get("as_of"),
        "kaynak": found.get("subject") or found.get("filename"),
        "applied": [c["baslik"] for c in auto],
        # Onay bekleyenler arayüzde kutulanabilsin diye kimlikleriyle birlikte
        "pending": [{"id": c["id"], "baslik": c["baslik"], "detay": c["detay"],
                     "kind": c["kind"]} for c in pending],
        "warnings": d["warnings"],
        # Onay bekleyenleri sonradan uygulayabilmek için ayrıştırılmış ekstre.
        # Alt çizgiyle başlar; API yanıtına konmaz.
        "_parsed": parsed,
    }
    _state["last_result"] = {k: v for k, v in result.items() if not k.startswith("_")}
    _state["last_error"] = None

    if notify:
        parts = []
        if auto:
            parts.append(f"{len(auto)} değişiklik uygulandı")
        if pending:
            parts.append(f"{len(pending)} değişiklik onay bekliyor")
        if parts:
            notify("Ekstre güncellendi", " · ".join(parts))
    return result


def _loop(notify):
    while True:
        s = assistant._load_secrets()
        interval = int(s.get("auto_sync_interval") or DEFAULT_INTERVAL)
        if s.get("auto_sync"):
            try:
                check_once(notify=notify)
            except Exception as e:
                # Ağ/kimlik hatası izleyiciyi öldürmemeli; bir sonraki turda dener.
                _state["last_error"] = str(e)
                traceback.print_exc()
        time.sleep(max(60, interval))


def start(notify=None) -> None:
    """İzleyiciyi arka plan iş parçacığında başlatır (yalnızca bir kez)."""
    if _state["running"]:
        return
    _state["running"] = True
    threading.Thread(target=_loop, args=(notify,), daemon=True).start()
