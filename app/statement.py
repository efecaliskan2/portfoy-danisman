"""
Midas hesap ekstresi (PDF) okuyucu
==================================
Aracı kuruma BAĞLANMAZ, şifre istemez. Yalnızca kullanıcının kendi indirdiği
PDF dosyasını yerelde okur.

GİZLİLİK: Ekstrede TCKN, ad-soyad ve adres de yer alır. Bu modül onları
BİLEREK ayrıştırmaz ve hiçbir yere yazmaz — sadece pozisyon, işlem ve nakit
alanları çıkarılır.

Ekstre metni sütun sütun, her hücre ayrı satır olarak gelir:
  - PORTFÖY ÖZETİ  -> 5 alanlık bloklar (ad, adet, ort. maliyet, K/Z, değer)
  - YATIRIM İŞLEMLERİ -> 12 alanlık bloklar (bkz. _TRADE_FIELDS)
Bu düzen bozulursa ayrıştırıcı SESSİZCE YANLIŞ SONUÇ VERMEZ; hata fırlatır.
"""

from __future__ import annotations

import re
from datetime import datetime

_TRADE_FIELDS = 12          # bir işlem satırındaki hücre sayısı
_POSITION_FIELDS = 5        # portföy özetinde bir satırdaki hücre sayısı

_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{2}(\s+\d{2}:\d{2}:\d{2})?$")


def _num(s: str | None):
    """'1.234,56 TRY' -> 1234.56 ; '-' / '' -> None (Türkçe sayı biçimi)."""
    if s is None:
        return None
    s = s.replace("TRY", "").strip()
    if not s or s == "-":
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _date(s: str):
    for fmt in ("%d/%m/%y %H:%M:%S", "%d/%m/%y"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


def _lines(pdf_path_or_bytes) -> list[str]:
    import fitz  # PyMuPDF
    if isinstance(pdf_path_or_bytes, (bytes, bytearray)):
        doc = fitz.open(stream=bytes(pdf_path_or_bytes), filetype="pdf")
    else:
        doc = fitz.open(pdf_path_or_bytes)
    out: list[str] = []
    for page in doc:
        out += [ln.strip() for ln in page.get_text().split("\n")]
    doc.close()
    return [ln for ln in out if ln]


def _index_of(lines: list[str], needle: str, start: int = 0) -> int:
    for i in range(start, len(lines)):
        if needle in lines[i]:
            return i
    return -1


# --------------------------------------------------------------------------- #
#  Bölümler
# --------------------------------------------------------------------------- #
def _parse_cash(lines: list[str]) -> float | None:
    i = _index_of(lines, "Nakit Bakiye")
    if i < 0:
        return None
    # ": 11.94 TRY" ya da sonraki satırda
    for cand in (lines[i], *lines[i + 1:i + 4]):
        m = re.search(r"([\d.,]+)\s*TRY", cand)
        if m:
            # Bu alanda ondalık AYIRICI NOKTA olabiliyor ("11.94 TRY"),
            # tablo hücrelerinden farklı. İki biçimi de destekle.
            raw = m.group(1)
            if "," in raw:
                return _num(raw)
            try:
                return float(raw)
            except ValueError:
                return None
    return None


def _parse_positions(lines: list[str]) -> list[dict]:
    start = _index_of(lines, "PORTFÖY ÖZETİ")
    end = _index_of(lines, "YATIRIM İŞLEMLERİ")
    if start < 0 or end < 0:
        return []
    head = _index_of(lines, "Toplam Değeri", start)   # başlık satırlarının sonu
    if head < 0 or head >= end:
        return []
    rows, i = [], head + 1
    while i + _POSITION_FIELDS <= end:
        name = lines[i]
        # "TLY - Tera Portföy Birinci..." biçiminde değilse bölüm bitmiştir
        if " - " not in name:
            break
        code = name.split(" - ", 1)[0].strip().upper()
        units = _num(lines[i + 1])
        avg = _num(lines[i + 2])
        value = _num(lines[i + 4])
        if units is None or avg is None:
            break
        rows.append({
            "code": code,
            "name": name.split(" - ", 1)[1].strip().rstrip("."),
            "units": units,
            "avg_cost": avg,
            "cost_try": round(units * avg, 2),
            "value": value,
        })
        i += _POSITION_FIELDS
    return rows


def _parse_trades(lines: list[str]) -> list[dict]:
    start = _index_of(lines, "YATIRIM İŞLEMLERİ")
    if start < 0:
        return []
    head = _index_of(lines, "İşlem Tutarı", start)
    if head < 0:
        return []
    stop = _index_of(lines, "HESAP İŞLEMLERİ", head)
    if stop < 0:
        stop = len(lines)

    trades, i = [], head + 1
    while i < stop:
        if not _DATE_RE.match(lines[i]):
            break                                  # bölüm bitti
        chunk = lines[i:i + _TRADE_FIELDS]
        if len(chunk) < _TRADE_FIELDS:
            break
        dt = _date(chunk[0])
        trades.append({
            "date": dt.isoformat(timespec="seconds") if dt else chunk[0],
            # "Fon Emri" -> TEFAS fonu, "Limit/Piyasa Emri" -> BIST hissesi.
            # Varlık türünü bundan güvenilir şekilde çıkarıyoruz.
            "order_type": chunk[1].strip(),
            "symbol": chunk[2].strip().upper(),
            "side": chunk[3].strip(),              # Alış / Satış
            "status": chunk[4].strip(),            # Gerçekleşti / İptal Edildi
            "filled": _num(chunk[8]) or 0.0,
            "price": _num(chunk[9]),
            "amount": _num(chunk[11]) or 0.0,      # işlem tutarı (ücret dahil)
        })
        i += _TRADE_FIELDS
    return trades


# --------------------------------------------------------------------------- #
#  Gerçekleşmiş kâr/zarar — ortalama maliyet yöntemi
# --------------------------------------------------------------------------- #
def realized_from_trades(trades: list[dict]) -> tuple[float, dict]:
    """Kronolojik sırayla ortalama maliyet tutarak kapanan kısmın K/Z'sini bulur.
    Kısmi satışları da doğru hesaplar. Dönen: (toplam, sembol bazında detay)."""
    book: dict[str, dict] = {}
    detail: dict[str, float] = {}
    for t in sorted(trades, key=lambda x: x["date"]):
        if t["status"] != "Gerçekleşti" or not t["filled"]:
            continue
        b = book.setdefault(t["symbol"], {"qty": 0.0, "cost": 0.0})
        if t["side"] == "Alış":
            b["qty"] += t["filled"]
            b["cost"] += t["amount"]
        elif t["side"] == "Satış":
            if b["qty"] <= 0:
                continue                            # açılışı ekstre dışında kalmış
            sold = min(t["filled"], b["qty"])
            unit_cost = b["cost"] / b["qty"]
            pnl = t["amount"] - unit_cost * sold
            detail[t["symbol"]] = round(detail.get(t["symbol"], 0.0) + pnl, 2)
            b["cost"] -= unit_cost * sold
            b["qty"] -= sold
    return round(sum(detail.values()), 2), detail


def parse_statement(pdf) -> dict:
    """Ekstreyi çözümler. Beklenen yapı bulunamazsa ValueError fırlatır —
    sessizce boş/yanlış veri döndürmez."""
    lines = _lines(pdf)
    if not any("Midas" in ln for ln in lines[:12]):
        raise ValueError("Bu dosya bir Midas hesap ekstresine benzemiyor.")
    positions = _parse_positions(lines)
    trades = _parse_trades(lines)
    if not positions and not trades:
        raise ValueError("Ekstrede pozisyon veya işlem bulunamadı; "
                         "dosya biçimi değişmiş olabilir.")
    total, detail = realized_from_trades(trades)

    # VARLIK TÜRÜ (fon mu hisse mi) — portföy özeti bunu söylemez. Öncelik sırası:
    #   1) İşlem satırındaki emir türü ("Fon Emri" -> fon)  — en kesin
    #   2) BIST şirket listesinde var mı (sources.get_bist_universe) — işlem yoksa
    #   3) Kod uzunluğu: TEFAS fon kodları 3 harf, BIST hisseleri 4-5 harf
    # ESKİ HATA: yalnızca (1) vardı ve işlem yoksa "hisse" varsayılıyordu. Tek günlük
    # ekstrede işlem satırı olmadığı için THF fonu hisse sanıldı -> Yahoo'da THF.IS
    # bulunamadı -> 0 TL göründü.
    kinds: dict[str, str] = {}
    for t in trades:
        kinds.setdefault(t["symbol"],
                         "fund" if "Fon" in t.get("order_type", "") else "stock")
    try:
        from .sources import get_bist_universe
        bist = {x["code"] for x in get_bist_universe()}
    except Exception:
        bist = set()
    for p in positions:
        code = p["code"]
        if code in kinds:
            p["type"] = kinds[code]
        elif bist:
            p["type"] = "stock" if code in bist else "fund"
        else:
            p["type"] = "fund" if len(code) == 3 else "stock"

    period = [ln for ln in lines[:30] if _DATE_RE.match(ln)]
    # Dönem başı "10/09/26 -" biçiminde ayrı satırda gelir. Gerçekleşmiş K/Z'nin
    # hangi tarih aralığını kapsadığını bilmek için gerekli (bkz. reconcile).
    start = next((m.group(1) for ln in lines[:30]
                  if (m := re.match(r"^(\d{2}/\d{2}/\d{2})\s*-\s*$", ln))), None)
    return {
        "period_start": start,
        "as_of": period[-1] if period else None,
        "cash_try": _parse_cash(lines),
        "positions": positions,
        "trades": trades,
        "realized_total": total,
        "realized_by_symbol": detail,
        "kinds": kinds,
    }
