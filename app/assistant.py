"""
Portföy asistanı — Claude entegrasyonu
======================================
Uygulamanın kendi verisi üzerine soru-cevap, rapor sadeleştirme, varlık
açıklaması ve uyarı yorumlama.

GİZLİLİK — bu modül, projenin "hiçbir veri dışarı çıkmaz" ilkesinin BİLİNÇLİ
istisnasıdır (kullanıcı 2026-08 kararı):
  - Yalnızca kullanıcı bir soru sorduğunda istek gider; arka planda hiçbir şey
    gönderilmez.
  - Giden veri portföy içeriğidir (kod, adet, maliyet, değer, K/Z, ağırlık) +
    piyasa göstergeleri. Kimlik bilgisi, TCKN, ad-soyad, adres, hesap numarası
    ASLA gitmez — bunlar zaten uygulamaya hiç girmiyor (bkz. statement.py).
  - Aracı kuruma bağlanılmaz; hiçbir şifre/oturum kullanılmaz.

KAPSAM: Bu asistan analiz eder ve açıklar; "şunu al/sat" emri vermez.
Karar kullanıcıya aittir (projenin değişmez ilkesi).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# Tek model, bilinçli seçim: bu uygulamada iş rakamlar üzerinde dikkatli akıl
# yürütmek (yoğunlaşma, içerik çakışması, senaryo etkisi) ve eksik veriyi
# uydurmadan söylemek. Kullanım seyrek olduğu için kaliteyi maliyete tercih
# ediyoruz. Model seçici bilerek EKLENMEDİ — gereksiz karmaşa.
MODEL = "claude-opus-5"

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SECRETS_PATH = DATA_DIR / "secrets.json"   # yerelde kalır, repoya girmemeli

SYSTEM_PROMPT = """\
Kullanıcının yerel portföy uygulamasının içine gömülü bir portföy analistisin.
Türkçe, sade ve doğrudan konuşursun.

ELİNDEKİ VERİ
Her soruda sana kullanıcının GÜNCEL portföyü ve piyasa verisi JSON olarak verilir.
Cevaplarını YALNIZCA bu veriye ve genel finans bilgine dayandır.

DÜRÜSTLÜK KURALLARI (en önemlisi)
- Veride olmayan bir rakamı UYDURMA. Bilmiyorsan "bu veri elimde yok" de.
- Sana verilen sayıları olduğu gibi kullan; yeniden hesaplarken aritmetiğini göster.
- Bir gösterge hesaplanamamışsa (örn. yeni halka arzda RSI yok) bunu söyle,
  tahminle doldurma.
- Emin olmadığın yerde emin değilim de. Kullanıcı dürüstlüğe kesinlikten çok değer verir.

NE YAPARSIN
- Portföy hakkında soruları cevaplarsın ("bugün neden düştüm", "en riskli varlığım hangisi").
- Günün raporunu sade Türkçeye çevirir, uzun teknik metni özetlersin.
- Uyarıların (RSI, sert hareket, yoğunlaşma) ne anlama geldiğini anlatırsın.
- Tuttuğu varlıkları tanıtırsın; şirket bilgisi gerekiyorsa web araması yaparsın.
- Portföy yapısını analiz edersin: yoğunlaşma, fonların içerik çakışması, ağırlık
  dağılımı, maliyet/kâr yapısı, tek bir varlıktaki düşüşün portföye etkisi,
  senaryo hesapları. Kullanıcı "kârımı nasıl optimize ederim" diye sorarsa
  BUNLARI anlat: nerede yoğunlaşma riski var, hangi varlık portföyü sürüklüyor,
  çeşitlendirme gerçekten çeşitlendirme mi, maliyet yapısı ne söylüyor.

SINIR
Belirli bir varlığı "al" ya da "sat" diye tavsiye etmezsin ve hangi hisseye/fona
para koyacağını söylemezsin — lisanslı yatırım danışmanı değilsin. Bunun yerine
verinin ne gösterdiğini, hangi risklerin biriktiğini ve kullanıcının kendine
sorması gereken soruları ortaya koyarsın. Kullanıcı ısrar ederse bunu bir kez,
kısaca ve özür dilemeden söyle, sonra elindeki en faydalı analizi yap.
Ahlak dersi verme, uzun uyarı metinleri yazma.

BİÇİM
Kısa tut. Madde işareti ve kalın yazıyı ölçülü kullan. Rakamları Türkçe biçimde
yaz (18.361,25 ₺). Gereksiz giriş cümlesi kurma, doğrudan cevaba gir.\
"""


# --------------------------------------------------------------------------- #
#  API anahtarı — ortam değişkeni ya da yerel dosya
# --------------------------------------------------------------------------- #
def _load_secrets() -> dict:
    if SECRETS_PATH.exists():
        try:
            return json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_secrets(d: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SECRETS_PATH.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def load_api_key() -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key.strip()
    return (_load_secrets().get("anthropic_api_key") or "").strip() or None


def save_api_key(key: str) -> None:
    d = _load_secrets()
    d["anthropic_api_key"] = key.strip()
    _save_secrets(d)


def has_api_key() -> bool:
    return bool(load_api_key())


# --------------------------------------------------------------------------- #
#  Claude'a gidecek bağlam — eksiksiz ama kimlik bilgisi içermez
# --------------------------------------------------------------------------- #
def build_context(data: dict) -> dict:
    """full_analysis() çıktısından portföy bağlamı üretir.

    BİLEREK DIŞARIDA BIRAKILANLAR: portfolio.json'daki `owner`, `notes` ve
    diğer serbest metin alanları (kişisel bilgi barındırabilir).
    """
    v = data.get("valuation", {})
    m = data.get("market", {})

    def r(x, n=2):
        return round(x, n) if isinstance(x, (int, float)) else x

    holdings = []
    for it in v.get("items", []):
        holdings.append({
            "kod": it.get("code"),
            "ad": it.get("name"),
            "tur": {"fund": "fon", "stock": "hisse",
                    "gold": "altın", "cash": "nakit"}.get(it.get("type")),
            "miktar": it.get("amount"), "birim": it.get("unit"),
            "fiyat": r(it.get("price"), 4),
            "deger_try": r(it.get("value")),
            "maliyet_try": r(it.get("cost")),
            "kar_zarar_try": r(it.get("pnl")),
            "kar_zarar_pct": r(it.get("pnl_pct")),
            "agirlik_pct": r(it.get("weight")),
            "gunluk_pct": r(it.get("daily_pct")),
            "gunluk_try": r(it.get("daily_value_change")),
            "gunluk_referans": it.get("daily_basis"),
            "yeni_halka_arz": it.get("new_listing") or False,
        })

    funds = {}
    for code, f in (m.get("funds") or {}).items():
        funds[code] = {
            "ad": f.get("name"), "fiyat": r(f.get("price"), 4),
            "getiri_1ay_pct": f.get("yield_1m"), "getiri_3ay_pct": f.get("yield_3m"),
            "risk_seviyesi": f.get("risk"), "yonetim_ucreti": f.get("management_fee"),
            "yatirimci_sayisi": f.get("investor_count"),
            "en_buyuk_pozisyonlar": f.get("top_holdings", [])[:10],
            "kategori_kiyasi": f.get("peer", {}),
        }

    stocks = {}
    for code, s in (m.get("stocks") or {}).items():
        stocks[code] = {
            "ad": s.get("name"), "fiyat": r(s.get("price"), 4),
            "onceki_kapanis": r(s.get("prev_price"), 4),
            "gunluk_pct": r(s.get("daily_pct")),
            "rsi": r(s.get("rsi"), 1),
            "zirveden_dusus_pct": r(s.get("drawdown_from_peak"), 1),
            "veri_gun_sayisi": s.get("days_of_data"),
            "yeni_halka_arz": s.get("new_listing"),
        }

    hist = data.get("history") or []
    return {
        "tarih": data.get("date"),
        "ozet": {
            "toplam_deger_try": r(v.get("total_value")),
            "toplam_maliyet_try": r(v.get("total_cost")),
            "acik_kar_zarar_try": r(v.get("total_pnl")),
            "acik_kar_zarar_pct": r(v.get("total_pnl_pct")),
            "gerceklesmis_kar_zarar_try": r(v.get("realized_pnl")),
            "bugun_try": r(v.get("daily_change_value")),
            "bugun_pct": r(v.get("daily_change_pct")),
            "nakit_try": r(v.get("cash_value")),
            "yatirimdaki_try": r(v.get("invested_value")),
        },
        "varliklar": holdings,
        "fon_detaylari": funds,
        "hisse_detaylari": stocks,
        "piyasa": {
            "bist100": {
                "seviye": r((m.get("bist") or {}).get("price")),
                "gunluk_pct": r((m.get("bist") or {}).get("daily_pct")),
                "rsi": r((m.get("bist") or {}).get("rsi"), 1),
                "zirveden_dusus_pct": r((m.get("bist") or {}).get("drawdown_from_peak"), 1),
            },
            "gram_altin": {
                "fiyat": r((m.get("gold") or {}).get("price")),
                "gunluk_pct": r((m.get("gold") or {}).get("daily_pct")),
            },
        },
        "uyarilar": [a.get("text") for a in data.get("alerts", [])],
        "fon_icerik_cakismasi": data.get("overlap", []),
        "gunluk_rapor_metni": data.get("report_text"),
        "deger_gecmisi": [{"tarih": h.get("date"), "toplam": h.get("total")}
                          for h in hist[-30:]],
    }


# --------------------------------------------------------------------------- #
#  Claude çağrısı (streaming)
# --------------------------------------------------------------------------- #
def stream_answer(question: str, data: dict, history: list | None = None):
    """Soruyu portföy bağlamıyla Claude'a sorar; yanıtı parça parça üretir.

    Streaming kullanılır: uzun yanıtlarda HTTP zaman aşımı olmasın ve kullanıcı
    beklerken metnin akışını görsün.
    """
    import anthropic

    key = load_api_key()
    if not key:
        raise RuntimeError("Anthropic API anahtarı tanımlı değil.")

    client = anthropic.Anthropic(api_key=key)
    context = build_context(data)

    messages = []
    for turn in (history or [])[-8:]:          # son birkaç tur yeterli
        role = "assistant" if turn.get("role") == "assistant" else "user"
        text = (turn.get("text") or "").strip()
        if text:
            messages.append({"role": role, "content": text})

    messages.append({
        "role": "user",
        "content": (
            "Güncel portföy ve piyasa verisi (JSON):\n"
            f"{json.dumps(context, ensure_ascii=False, indent=1)}\n\n"
            f"Soru: {question.strip()}"
        ),
    })

    with client.messages.stream(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 4}],
        messages=messages,
    ) as stream:
        for event in stream:
            if event.type == "text":
                yield event.text
