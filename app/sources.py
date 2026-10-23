"""
Veri kaynakları
===============
Tüm veriler HALKA AÇIK kaynaklardan, SADECE OKUMA amaçlı çekilir.
Hiçbir hesap/şifre kullanılmaz, hiçbir veri dışarı gönderilmez.

  - Fon (TLY, PHE ...) : api.fintables.com (resmi TEFAS verisini yansıtır)
  - Gram altın (TRY)   : Yahoo Finance (altın onsu USD * USDTRY / 31.1035)
  - BIST 100 (XU100)   : Yahoo Finance
  - BIST hissesi       : Yahoo Finance ({KOD}.IS) + şirket adı fintables'tan

Her çağrı, ağ hatasına karşı son başarılı sonucu diskte saklar (cache) ve
internet yoksa o değerlere düşer. Böylece uygulama her zaman bir şey gösterir.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_PATH = DATA_DIR / "cache.json"
SYMBOLS_PATH = DATA_DIR / "bist_symbols.json"   # tüm BIST hisse evreni (ayrı dosya:
                                                # ~200 KB, cache.json'u şişirmesin)
SYMBOLS_TTL = 12 * 3600                          # günde birkaç kez tazelemek yeter

GRAMS_PER_OUNCE = 31.1034768

_FIN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Accept-Language": "tr,en;q=0.9",
    "Origin": "https://fintables.com",
    "Referer": "https://fintables.com/",
}


# --------------------------------------------------------------------------- #
#  Basit disk cache (ağ koptuğunda son değere düşmek için)
# --------------------------------------------------------------------------- #
def _load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _cache_get(key: str):
    return _load_cache().get(key)


def _cache_put(key: str, value: dict) -> None:
    cache = _load_cache()
    value = dict(value)
    value["_cached_at"] = datetime.now().isoformat(timespec="seconds")
    cache[key] = value
    _save_cache(cache)


# --------------------------------------------------------------------------- #
#  Fonlar (fintables)
# --------------------------------------------------------------------------- #
def _fin_get(path: str) -> dict | list:
    url = "https://api.fintables.com/" + path
    r = requests.get(url, headers=_FIN_HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()


def get_fund(code: str) -> dict:
    """Bir TEFAS fonu için fiyat, getiri, içerik ve kıyas verisini döndürür."""
    code = code.upper()
    cache_key = f"fund:{code}"
    try:
        price = _fin_get(f"funds/{code}/price/?range=1A")
        info = _fin_get(f"funds/{code}/info/")
        try:
            comparison = _fin_get(f"funds/{code}/comparison/")
        except Exception:
            comparison = {}

        last = float(price.get("price"))
        prev = float(price.get("prev_price") or last)
        daily_pct = (last - prev) / prev * 100 if prev else 0.0

        # Portföy içeriği (en büyük pozisyonlar)
        holdings = []
        lp = info.get("latest_portfolio") or {}
        for item in lp.get("items", []):
            w = item.get("weight")
            if w:
                holdings.append({"code": item.get("code"), "weight": float(w)})
        holdings.sort(key=lambda x: x["weight"], reverse=True)

        # Kategori kıyası (fon vs akran ortalaması)
        peer = {}
        for period in ("1m", "3m", "6m"):
            rows = comparison.get(period) or []
            if len(rows) >= 2:
                peer[period] = {
                    "fund": _first_change(rows, code),
                    "category": _first_change(rows, None, exclude=code),
                }

        result = {
            "code": code,
            "name": info.get("title") or code,
            "price": last,
            "prev_price": prev,
            "daily_pct": daily_pct,
            "yield_1m": _num(price.get("yield_1m")),
            "yield_3m": _num(price.get("yield_3m")),
            "risk": info.get("risk"),
            "management_fee": info.get("management_fee"),
            "investor_count": info.get("investor_count"),
            "market_cap": _num(price.get("market_cap")),
            "type": info.get("type"),
            "top_holdings": holdings[:10],
            "peer": peer,
            "date": price.get("day"),
            "ok": True,
        }
        _cache_put(cache_key, result)
        return result
    except Exception as e:
        cached = _cache_get(cache_key)
        if cached:
            cached["ok"] = False
            cached["error"] = str(e)
            cached["stale"] = True
            return cached
        return {"code": code, "ok": False, "error": str(e), "price": None}


def _first_change(rows: list, code: str | None, exclude: str | None = None):
    for row in rows:
        rc = row.get("code", "")
        if code is not None and rc == code:
            return _num(row.get("change"))
        if code is None and rc != exclude:
            return _num(row.get("change"))
    return None


# --------------------------------------------------------------------------- #
#  Yahoo Finance (altın + BIST) — yfinance ile
# --------------------------------------------------------------------------- #
def _yf_series(ticker: str, period: str = "6mo"):
    import yfinance as yf
    df = yf.download(ticker, period=period, interval="1d",
                     progress=False, auto_adjust=True)
    if df is None or df.empty:
        return None
    close = df["Close"]
    if hasattr(close, "columns"):
        close = close.iloc[:, 0]
    return close.dropna()


def get_gold_gram() -> dict:
    """Gram altının TL fiyatı = (ons altın USD / 31.1035) * USDTRY."""
    cache_key = "gold:gram"
    try:
        ons = _yf_series("GC=F", "1mo")
        usdtry = _yf_series("USDTRY=X", "1mo")
        gram_now = float(ons.iloc[-1]) / GRAMS_PER_OUNCE * float(usdtry.iloc[-1])
        gram_prev = float(ons.iloc[-2]) / GRAMS_PER_OUNCE * float(usdtry.iloc[-2])
        result = {
            "name": "Gram Altın",
            "price": gram_now,
            "prev_price": gram_prev,
            "daily_pct": (gram_now - gram_prev) / gram_prev * 100,
            "ok": True,
        }
        _cache_put(cache_key, result)
        return result
    except Exception as e:
        cached = _cache_get(cache_key)
        if cached:
            cached["ok"] = False
            cached["stale"] = True
            return cached
        return {"name": "Gram Altın", "ok": False, "error": str(e), "price": None}


def get_bist() -> dict:
    """BIST 100 (XU100): güncel seviye, günlük değişim, zirveden düşüş, RSI."""
    cache_key = "index:xu100"
    try:
        s = _yf_series("XU100.IS", "6mo")
        last = float(s.iloc[-1])
        prev = float(s.iloc[-2])
        peak = float(s.max())
        drawdown = (last - peak) / peak * 100
        result = {
            "name": "BIST 100",
            "price": last,
            "prev_price": prev,
            "daily_pct": (last - prev) / prev * 100,
            "peak_6mo": peak,
            "drawdown_from_peak": drawdown,
            "rsi": _rsi(s),
            "ok": True,
        }
        _cache_put(cache_key, result)
        return result
    except Exception as e:
        cached = _cache_get(cache_key)
        if cached:
            cached["ok"] = False
            cached["stale"] = True
            return cached
        return {"name": "BIST 100", "ok": False, "error": str(e), "price": None}


# --------------------------------------------------------------------------- #
#  BIST hisse evreni (arama için) — fintables `companies/`
# --------------------------------------------------------------------------- #
_TR_LOWER = str.maketrans({"İ": "i", "I": "ı", "Ş": "ş", "Ğ": "ğ",
                           "Ü": "ü", "Ö": "ö", "Ç": "ç"})
_TR_PLAIN = str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ü": "u",
                           "ö": "o", "ç": "c", "â": "a", "î": "i", "û": "u"})


def _norm_tr(s: str) -> str:
    """Türkçe duyarlı arama anahtarı: 'Katılımevim' -> 'katilimevim'.
    Böylece kullanıcı 'katilim' yazınca da bulur (İ/ı ve aksan farkı sorun olmaz)."""
    return (s or "").translate(_TR_LOWER).lower().translate(_TR_PLAIN)


def get_bist_universe(force: bool = False) -> list:
    """Tüm BIST şirketleri: [{code, name, price}]. Diskte 12 saat önbelleklenir.

    Tek uç (`companies/`) 650+ şirketi kod, ad ve güncel fiyatla birlikte döndürür;
    hisse başına ayrı istek atmaya gerek yok.
    """
    if not force and SYMBOLS_PATH.exists():
        try:
            cached = json.loads(SYMBOLS_PATH.read_text(encoding="utf-8"))
            if time.time() - cached.get("_ts", 0) < SYMBOLS_TTL and cached.get("items"):
                return cached["items"]
        except (json.JSONDecodeError, OSError):
            pass
    try:
        raw = _fin_get("companies/")
        items = [{"code": c["code"], "name": c.get("title") or c["code"],
                  "price": _num(c.get("price"))}
                 for c in raw if c.get("code")]
        items.sort(key=lambda x: x["code"])
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SYMBOLS_PATH.write_text(
            json.dumps({"_ts": time.time(), "items": items}, ensure_ascii=False),
            encoding="utf-8")
        return items
    except Exception:
        # Ağ yoksa bayat listeyi kullan — arama çalışmaya devam etsin.
        if SYMBOLS_PATH.exists():
            try:
                return json.loads(SYMBOLS_PATH.read_text(encoding="utf-8")).get("items", [])
            except (json.JSONDecodeError, OSError):
                return []
        return []


def search_bist(query: str, limit: int = 20) -> list:
    """Koda veya şirket adına göre hisse arar; en alakalı eşleşmeler önce gelir."""
    items = get_bist_universe()
    q = _norm_tr(query).strip()
    if not q:
        return items[:limit]
    scored = []
    for it in items:
        code, name = _norm_tr(it["code"]), _norm_tr(it["name"])
        if code == q:
            rank = 0
        elif code.startswith(q):
            rank = 1
        elif name.startswith(q):
            rank = 2
        elif q in code:
            rank = 3
        elif q in name:
            rank = 4
        else:
            continue
        scored.append((rank, it["code"], it))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [it for _, _, it in scored[:limit]]


def _yf_quote(ticker: str) -> dict:
    """Yahoo anlık kotasyonu: son fiyat + ÖNCEKİ KAPANIŞ.

    NEDEN GEREKLİ: günlük bar serisi (`_yf_series`) bazen gün ATLAR — özellikle yeni
    halka arzlarda. Örn. CITAS'ta 19.08.2026 barı hiç gelmedi; seriden türetilen
    "önceki kapanış" iki gün öncesini (81,05) gösterip günlük değişimi %21 çıkardı
    (doğrusu 89,15'e göre %9,98 idi). Kotasyon ucu `previousClose`u doğru verdiği için
    günlük değişim BURADAN alınır; seri yalnızca RSI/drawdown gibi göstergelerde kullanılır.
    """
    import yfinance as yf
    out: dict = {}
    t = yf.Ticker(ticker)
    try:
        fi = t.fast_info
        out["price"] = _num(fi.get("lastPrice", fi.get("last_price")))
        out["prev_close"] = _num(fi.get("previousClose", fi.get("previous_close")))
    except Exception:
        pass
    if not out.get("price") or not out.get("prev_close"):
        try:
            info = t.info
            out["price"] = out.get("price") or _num(info.get("regularMarketPrice"))
            out["prev_close"] = out.get("prev_close") or _num(
                info.get("regularMarketPreviousClose") or info.get("previousClose"))
        except Exception:
            pass
    return out


def _stock_title(code: str) -> str | None:
    """Şirketin tam adı (fintables). Yahoo'nun kısa adı yerine bunu tercih ederiz."""
    try:
        return (_fin_get(f"companies/{code}/") or {}).get("title")
    except Exception:
        return None


def get_stock(code: str, name: str | None = None) -> dict:
    """BIST hissesi (ör. CITAS) — Yahoo Finance `{KOD}.IS`.

    YENİ HALKA ARZLARDA geçmiş seri çok kısadır. Bu durumda günlük değişim, RSI ve
    zirveden düşüş ÜRETİLMEZ (None döner) — birkaç günlük veriden gösterge uydurmak
    yanıltıcı olurdu. Arayüz bunu "yeni halka arz" olarak gösterir.
    """
    code = code.upper()
    cache_key = f"stock:{code}"
    try:
        s = _yf_series(f"{code}.IS", "6mo")     # göstergeler (RSI, zirve) için
        q = _yf_quote(f"{code}.IS")             # fiyat + önceki kapanış için (güvenilir)
        if (s is None or len(s) == 0) and not q.get("price"):
            raise ValueError(f"{code}.IS için Yahoo Finance'ta fiyat verisi yok")

        days = int(len(s)) if s is not None else 0
        last = q.get("price") or (float(s.iloc[-1]) if days else None)

        # Önceki kapanış: önce kotasyon, olmazsa seri. Tek barlık (ilk işlem günü)
        # durumda ÖNCEKİ KAPANIŞ YOKTUR -> None bırak; analiz katmanı o zaman
        # halka arz fiyatını referans alır.
        prev = q.get("prev_close")
        daily_source = "quote" if prev else None
        if not prev and days >= 2:
            prev = float(s.iloc[-2])
            daily_source = "series"
        if days < 2:
            prev, daily_source = None, None

        peak = float(s.max()) if days else last
        result = {
            "code": code,
            "name": name or _stock_title(code) or code,
            "price": last,
            "prev_price": prev,
            "daily_pct": ((last - prev) / prev * 100) if (prev and last) else None,
            "daily_source": daily_source,
            "days_of_data": days,
            "new_listing": days < 20,
            "peak_6mo": peak,
            "drawdown_from_peak": ((last - peak) / peak * 100) if days >= 5 else None,
            "rsi": _rsi(s) if days >= 15 else None,
            "ok": True,
        }
        _cache_put(cache_key, result)
        return result
    except Exception as e:
        cached = _cache_get(cache_key)
        if cached:
            cached["ok"] = False
            cached["error"] = str(e)
            cached["stale"] = True
            return cached
        return {"code": code, "name": name or code, "ok": False,
                "error": str(e), "price": None}


def _rsi(series, period: int = 14):
    try:
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        ag = gain.ewm(alpha=1 / period, min_periods=period).mean()
        al = loss.ewm(alpha=1 / period, min_periods=period).mean()
        rs = ag / al
        return float((100 - 100 / (1 + rs)).iloc[-1])
    except Exception:
        return None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
