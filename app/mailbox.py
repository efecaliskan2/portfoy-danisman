"""
E-posta kutusundan ekstre çekme (IMAP)
======================================
Kullanıcı Midas'tan ekstresini kendi e-postasına gönderir; bu modül posta
kutusunda YALNIZCA o e-postaları arayıp PDF ekini indirir.

GÜVENLİK / KAPSAM — bilinmesi gerekenler:
  - Gmail "Uygulama Şifresi" teknik olarak TÜM posta kutusuna okuma yetkisi
    verir; yalnızca tek göndericiye kısıtlanamaz. Bu kod bilerek dar yazılmıştır:
    sadece gönderici/konu filtresine uyan iletileri sorgular, gövde metnini
    okumaz, yalnızca PDF eklerini alır. Yetki geniş, kullanım dar.
  - Şifre yalnızca bu makinede data/secrets.json içinde durur (.gitignore'da),
    hiçbir yere gönderilmez.
  - Bağlantı IMAP over SSL (993). Salt okunurdur: posta silinmez, taşınmaz,
    okundu olarak işaretlenmez (PEEK kullanılır).
  - Sadece stdlib (imaplib, email) — yeni bağımlılık yok.
"""

from __future__ import annotations

import email
import imaplib
import re
from datetime import datetime, timedelta
from email.header import decode_header, make_header

DEFAULT_HOST = "imap.gmail.com"
DEFAULT_PORT = 993
DEFAULT_SENDER = "midas"          # gönderici adresinde aranacak parça
LOOKBACK_DAYS = 90
MAX_SCAN = 40                     # en yeni N iletiye bakılır, fazlası gereksiz


def _decode(s) -> str:
    try:
        return str(make_header(decode_header(s or "")))
    except Exception:
        return s or ""


def _pdf_parts(msg):
    """İletideki PDF eklerini (ad, bayt) olarak verir. Gövde metni OKUNMAZ."""
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        name = _decode(part.get_filename())
        ctype = (part.get_content_type() or "").lower()
        if ctype == "application/pdf" or name.lower().endswith(".pdf"):
            try:
                payload = part.get_payload(decode=True)
            except Exception:
                continue
            if payload:
                yield name or "ekstre.pdf", payload


def fetch_latest_statement(cfg: dict) -> dict:
    """En yeni Midas ekstresini bulur.

    cfg: {host, port, email, password, sender, folder}
    Dönen: {"filename", "data" (bytes), "subject", "date"}
    Bulunamazsa LookupError, bağlantı/kimlik hatasında RuntimeError fırlatır.
    """
    host = cfg.get("host") or DEFAULT_HOST
    port = int(cfg.get("port") or DEFAULT_PORT)
    user = (cfg.get("email") or "").strip()
    pwd = cfg.get("password") or ""
    sender = (cfg.get("sender") or DEFAULT_SENDER).strip()
    folder = cfg.get("folder") or "INBOX"
    if not user or not pwd:
        raise RuntimeError("E-posta adresi veya uygulama şifresi tanımlı değil.")

    try:
        conn = imaplib.IMAP4_SSL(host, port)
    except Exception as e:
        raise RuntimeError(f"Sunucuya bağlanılamadı ({host}:{port}): {e}") from e

    try:
        try:
            conn.login(user, pwd)
        except imaplib.IMAP4.error as e:
            raise RuntimeError(
                "Giriş reddedildi. Gmail kullanıyorsan normal şifre değil, "
                "iki adımlı doğrulama açıkken üretilen 16 haneli "
                "UYGULAMA ŞİFRESİ gerekir."
            ) from e

        typ, _ = conn.select(folder, readonly=True)   # readonly: hiçbir şey değişmez
        if typ != "OK":
            raise RuntimeError(f"Klasör açılamadı: {folder}")

        since = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%d-%b-%Y")
        # Önce göndericiye göre, bulunamazsa konuya göre ara.
        queries = [["SINCE", since, "FROM", sender],
                   ["SINCE", since, "SUBJECT", "ekstre"]]
        ids: list[bytes] = []
        for q in queries:
            typ, data = conn.search(None, *q)
            if typ == "OK" and data and data[0]:
                ids = data[0].split()
                if ids:
                    break
        if not ids:
            raise LookupError(
                f"Son {LOOKBACK_DAYS} günde '{sender}' göndericisinden ekstre "
                f"e-postası bulunamadı. Gönderici filtresini kontrol et.")

        # En yeniden geriye doğru tara, ilk PDF ekini al.
        for num in reversed(ids[-MAX_SCAN:]):
            typ, data = conn.fetch(num, "(BODY.PEEK[])")   # okundu işaretlemez
            if typ != "OK" or not data or not data[0]:
                continue
            msg = email.message_from_bytes(data[0][1])
            for name, payload in _pdf_parts(msg):
                return {"filename": name, "data": payload,
                        "subject": _decode(msg.get("Subject")),
                        "date": _decode(msg.get("Date"))}
        raise LookupError("Ekstre e-postaları bulundu ama PDF eki yok.")
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            conn.logout()
        except Exception:
            pass
