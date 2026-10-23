"""
Yerel web sunucusu (Flask)
==========================
SADECE 127.0.0.1 (kendi bilgisayarın) üzerinde çalışır — dışarıya açık değildir.
Arayüze JSON verir; portföy düzenlemesini kaydeder. Hiçbir veri dışarı gitmez.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from . import assistant, mailbox, reconcile, sources, watcher
from .analysis import full_analysis
from .portfolio import load_portfolio, restore_portfolio, save_portfolio
from .statement import parse_statement

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "data" / "reports"

app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path="")

# Basit bellek-içi cache (arayüz hızlı açılsın, yfinance'i her tıkta yormayalım)
_cache = {"data": None, "ts": 0}
_lock = threading.Lock()
# Arayüz 10 sn'de bir sorar; ama kaynaktan (fintables/Yahoo) gerçek veriyi en fazla
# 60 sn'de bir çekeriz. Fon fiyatı günde 1, BIST/altın ~15 dk gecikmeli güncellendiği
# için bu hem canlı hissettirir hem de ağı/CPU'yu yormaz, engellenme riski oluşturmaz.
_TTL = 60


def _get_analysis(force: bool = False) -> dict:
    with _lock:
        if not force and _cache["data"] and (time.time() - _cache["ts"] < _TTL):
            return _cache["data"]
        data = full_analysis()
        _cache["data"] = data
        _cache["ts"] = time.time()
        _save_report(data)
        return data


def _save_report(data: dict) -> None:
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        from datetime import date
        (REPORTS_DIR / f"rapor-{date.today().isoformat()}.txt").write_text(
            data["report_text"], encoding="utf-8")
    except Exception:
        pass


@app.after_request
def _no_cache(resp):
    """Arayüz dosyalarını önbelleğe aldırma.

    Uygulama penceresi (EdgeWebView2) HTML/JS/CSS'i agresif önbelleğe alıyor;
    kod güncellendiğinde pencere ESKİ sürümü göstermeye devam ediyor ve bu,
    düzeltilmiş hatalar hâlâ duruyormuş gibi görünmesine yol açıyor.
    Yerelde çalıştığı için önbelleğin kazancı yok, zararı var.
    """
    resp.headers["Cache-Control"] = "no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/")
def index():
    return send_from_directory(str(WEB_DIR), "index.html")


@app.route("/api/dashboard")
def dashboard():
    force = request.args.get("refresh") == "1"
    try:
        return jsonify({"ok": True, **_get_analysis(force)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/portfolio", methods=["GET", "POST"])
def portfolio():
    if request.method == "POST":
        data = request.get_json(force=True)
        save_portfolio(data)
        _cache["data"] = None  # değişti, yeniden hesapla
        return jsonify({"ok": True})
    return jsonify(load_portfolio())


@app.route("/api/symbols")
def symbols():
    """Hisse arama — düzenleme penceresindeki otomatik tamamlama bunu kullanır.
    `q` koda veya şirket adına göre eşleşir (Türkçe duyarlı)."""
    q = request.args.get("q", "")
    try:
        limit = max(1, min(int(request.args.get("limit", 12)), 50))
    except ValueError:
        limit = 12
    try:
        return jsonify({"ok": True, "results": sources.search_bist(q, limit)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "results": []}), 500


@app.route("/api/ai/status", methods=["GET", "POST"])
def ai_status():
    """Anahtar var mı / anahtarı kaydet. Anahtar yalnızca bu makinede
    data/secrets.json içinde tutulur, hiçbir yere gönderilmez."""
    if request.method == "POST":
        key = (request.get_json(force=True) or {}).get("api_key", "")
        if not key.strip():
            return jsonify({"ok": False, "error": "Anahtar boş."}), 400
        assistant.save_api_key(key)
        return jsonify({"ok": True, "configured": True})
    return jsonify({"ok": True, "configured": assistant.has_api_key(),
                    "model": assistant.MODEL})


@app.route("/api/ai/ask", methods=["POST"])
def ai_ask():
    """Portföy sorusunu Claude'a sorar; yanıtı akış hâlinde döndürür.

    DIŞARI VERİ GİDEN TEK UÇ BURASI — sadece kullanıcı soru sorduğunda çalışır.
    """
    body = request.get_json(force=True) or {}
    question = (body.get("question") or "").strip()
    history = body.get("history") or []
    if not question:
        return jsonify({"ok": False, "error": "Soru boş."}), 400
    if not assistant.has_api_key():
        return jsonify({"ok": False, "error": "no_key"}), 428

    try:
        data = _get_analysis(False)          # akış başlamadan önce veriyi al
    except Exception as e:
        return jsonify({"ok": False, "error": f"Portföy verisi alınamadı: {e}"}), 500

    from flask import Response

    def generate():
        try:
            for chunk in assistant.stream_answer(question, data, history):
                yield "data: " + json.dumps({"t": chunk}, ensure_ascii=False) + "\n\n"
        except Exception as e:                # hata da akışın içinden bildirilir
            yield "data: " + json.dumps({"error": str(e)}, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"done": True}) + "\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --------------------------------------------------------------------------- #
#  Ekstre ile mutabakat (e-postadan ya da yüklenen dosyadan)
# --------------------------------------------------------------------------- #
_last_statement = {"parsed": None}     # onay adımında yeniden ayrıştırmamak için


@app.route("/api/mail/config", methods=["GET", "POST"])
def mail_config():
    """IMAP ayarları. Şifre YALNIZCA yazılır, hiçbir zaman geri döndürülmez."""
    cfg = assistant._load_secrets().get("imap") or {}
    if request.method == "POST":
        body = request.get_json(force=True) or {}
        new = {
            "host": (body.get("host") or mailbox.DEFAULT_HOST).strip(),
            "port": int(body.get("port") or mailbox.DEFAULT_PORT),
            "email": (body.get("email") or "").strip(),
            "sender": (body.get("sender") or mailbox.DEFAULT_SENDER).strip(),
            "folder": (body.get("folder") or "INBOX").strip(),
            "password": body.get("password") or cfg.get("password") or "",
        }
        if not new["email"] or not new["password"]:
            return jsonify({"ok": False, "error": "E-posta ve şifre gerekli."}), 400
        s = assistant._load_secrets()
        s["imap"] = new
        assistant._save_secrets(s)
        watcher.clear_error()      # ayar değişti; eski "tanımlı değil" hatası düşsün
        cfg = new
    return jsonify({"ok": True, "configured": bool(cfg.get("email") and cfg.get("password")),
                    "email": cfg.get("email", ""), "sender": cfg.get("sender", mailbox.DEFAULT_SENDER),
                    "host": cfg.get("host", mailbox.DEFAULT_HOST)})


@app.route("/api/statement/sync", methods=["POST"])
def statement_sync():
    """E-postadaki en yeni ekstreyi çeker, ayrıştırır ve FARKI döndürür.
    Hiçbir şey uygulanmaz — kullanıcı onaylayana kadar portföy değişmez."""
    cfg = assistant._load_secrets().get("imap") or {}
    if not (cfg.get("email") and cfg.get("password")):
        return jsonify({"ok": False, "error": "no_config"}), 428
    try:
        found = mailbox.fetch_latest_statement(cfg)
        parsed = parse_statement(found["data"])
    except LookupError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    _last_statement["parsed"] = parsed
    d = reconcile.diff(parsed, load_portfolio())
    return jsonify({"ok": True, "kaynak": found.get("subject") or found.get("filename"),
                    "eposta_tarihi": found.get("date"), **d,
                    "changes": [{k: v for k, v in c.items() if not k.startswith("_")}
                                for c in d["changes"]]})


@app.route("/api/statement/upload", methods=["POST"])
def statement_upload():
    """Elle yüklenen PDF ekstre — e-posta yolu kullanılmıyorsa."""
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "Dosya yok."}), 400
    try:
        parsed = parse_statement(f.read())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    _last_statement["parsed"] = parsed
    d = reconcile.diff(parsed, load_portfolio())
    return jsonify({"ok": True, "kaynak": f.filename, **d,
                    "changes": [{k: v for k, v in c.items() if not k.startswith("_")}
                                for c in d["changes"]]})


@app.route("/api/statement/apply", methods=["POST"])
def statement_apply():
    """Yalnızca kullanıcının onayladığı değişiklikleri uygular."""
    parsed = _last_statement.get("parsed")
    if not parsed:
        return jsonify({"ok": False, "error": "Önce ekstreyi oku."}), 400
    ids = (request.get_json(force=True) or {}).get("accept") or []
    new_pf = reconcile.apply(load_portfolio(), parsed, ids)
    save_portfolio(new_pf)
    _cache["data"] = None
    return jsonify({"ok": True, "applied": len(ids)})


@app.route("/api/statement/refresh", methods=["POST"])
def statement_refresh():
    """'Portföyü güncelle' düğmesi: postayı sorgular, en güncel ekstreyi bulur,
    güvenli değişiklikleri UYGULAR. Pozisyon kapatmalar onaya kalır (bkz. watcher)."""
    try:
        res = watcher.check_once(force=True)
    except LookupError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except RuntimeError as e:
        msg = str(e)
        return jsonify({"ok": False, "error": msg}), (428 if "tanımlı değil" in msg else 500)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    if res.get("_parsed"):
        _last_statement["parsed"] = res["_parsed"]   # onay adımı için sakla
    if res.get("applied"):
        _cache["data"] = None                        # portföy değişti, yeniden hesapla
    return jsonify({"ok": True, **{k: v for k, v in res.items() if not k.startswith("_")}})


@app.route("/api/statement/auto", methods=["GET", "POST"])
def statement_auto():
    """Otomatik izlemeyi aç/kapat ve durumunu göster."""
    if request.method == "POST":
        body = request.get_json(force=True) or {}
        watcher.set_enabled(bool(body.get("enabled")), body.get("interval"))
    return jsonify({"ok": True, **watcher.status()})


@app.route("/api/statement/undo", methods=["POST"])
def statement_undo():
    """Son otomatik güncellemeyi geri alır."""
    if not restore_portfolio():
        return jsonify({"ok": False, "error": "Geri alınacak yedek yok."}), 404
    _cache["data"] = None
    return jsonify({"ok": True})


@app.route("/api/report.txt")
def report_txt():
    data = _get_analysis(False)
    from flask import Response
    return Response(data["report_text"], mimetype="text/plain; charset=utf-8")


def run(host="127.0.0.1", port=8765):
    app.run(host=host, port=port, threaded=True, debug=False, use_reloader=False)
