"""
Analiz motoru — portföyün beyni
================================
Portföyü değerler, sinyaller üretir ve GEREKÇELİ günlük rapor yazar.

Felsefe: Tek kelimelik "al/sat" emri vermez; her varlık için bir EĞİLİM
(Ekle / Tut / Azalt) ve bunun NEDENİNİ açıklar. Nihai kararı kullanıcı verir.
Bu bir yatırım tavsiyesi değildir.
"""

from __future__ import annotations

from datetime import datetime

from . import sources
from .portfolio import load_portfolio, record_snapshot, load_history


# --------------------------------------------------------------------------- #
#  Piyasa verisini topla
# --------------------------------------------------------------------------- #
def gather_market(portfolio: dict) -> dict:
    funds, stocks = {}, {}
    for h in portfolio["holdings"]:
        if h.get("hidden"):
            continue  # gizli varlık: fiyatı bile çekilmez
        if h["type"] == "fund":
            data = sources.get_fund(h["code"])
            # /info/ ucu başlık vermiyor; portföydeki tam adı kullan.
            if h.get("name"):
                data["name"] = h["name"]
            funds[h["code"]] = data
        elif h["type"] == "stock":
            # Ad boşsa get_stock fintables'tan şirket adını kendisi çeker.
            stocks[h["code"]] = sources.get_stock(h["code"], h.get("name") or None)
    return {
        "funds": funds,
        "stocks": stocks,
        "gold": sources.get_gold_gram(),
        "bist": sources.get_bist(),
    }


# --------------------------------------------------------------------------- #
#  Portföyü değerle
# --------------------------------------------------------------------------- #
def value_portfolio(portfolio: dict, market: dict) -> dict:
    items = []
    total_value = total_cost = total_prev_value = 0.0
    for h in portfolio["holdings"]:
        # GİZLİ VARLIK: portföyde kayıtlı kalır ama hiçbir yerde görünmez ve
        # toplam değer / maliyet / kâr-zarar / günlük değişim hesabına GİRMEZ.
        # (Kalan küçük bakiyeler oranları ve K/Z yüzdesini saptırmasın diye.)
        if h.get("hidden"):
            continue
        daily_basis = "prev_close"  # neye göre ölçüldü: önceki kapanış / halka arz fiyatı
        # prev_value = varlığın DÜNKÜ (referans) değeri. Günlük değişim buradan
        # çıkarılır: değer - önceki değer. "değer * yüzde" kestirmesi yanlıştır
        # (yüzde, eski değere göredir; yeni değerle çarpınca değişimi şişirir).
        if h["type"] == "fund":
            data = market["funds"].get(h["code"], {})
            price = data.get("price") or 0
            value = price * h["units"]
            prev_value = (data.get("prev_price") or price) * h["units"]
        elif h["type"] == "stock":
            data = market["stocks"].get(h["code"], {})
            price = data.get("price") or 0
            value = price * h["units"]
            if data.get("daily_pct") is not None:
                prev_value = (data.get("prev_price") or price) * h["units"]
            else:
                # İLK İŞLEM GÜNÜ: önceki kapanış yok. Günün referansı halka arz
                # fiyatıdır (= toplam maliyet). Hissenin ilk gün kazancı gerçekten
                # O GÜNE aittir; 0 saymak günlük kârı eksik gösterirdi.
                # Yarın önceki kapanış oluşunca üstteki normal hesap devralır.
                cost_basis = h.get("cost_try") or 0
                if cost_basis > 0 and price:
                    prev_value = cost_basis
                    daily_basis = "ipo_price"
                else:
                    prev_value = value
                    daily_basis = None
        elif h["type"] == "gold":
            data = market["gold"]
            price = data.get("price") or 0
            value = price * h["grams"]
            prev_value = (data.get("prev_price") or price) * h["grams"]
        elif h["type"] == "cash":
            # Nakit: piyasa verisi yok, 1 TL = 1 TL. Günlük değişimi de yok.
            data = {}
            price = 1.0
            value = float(h.get("amount_try") or 0)
            prev_value = value
        else:
            continue
        daily_known = daily_basis is not None
        daily_change = value - prev_value
        daily_pct = (daily_change / prev_value * 100) if prev_value else 0.0
        cost = h.get("cost_try", value)
        total_value += value
        total_cost += cost
        total_prev_value += prev_value
        amount = {"fund": h.get("units"), "stock": h.get("units"),
                  "gold": h.get("grams"), "cash": h.get("amount_try")}.get(h["type"])
        items.append({
            "type": h["type"],
            "code": h["code"],
            "name": h.get("name") or data.get("name"),
            "amount": amount,
            "unit": {"fund": "adet", "stock": "lot", "gold": "gram", "cash": "₺"}[h["type"]],
            "new_listing": bool(data.get("new_listing")) if h["type"] == "stock" else False,
            "daily_known": daily_known,
            "daily_basis": daily_basis,
            "price": price,
            "value": value,
            "cost": cost,
            "pnl": value - cost,
            "pnl_pct": (value - cost) / cost * 100 if cost else 0,
            "daily_pct": daily_pct,
            "daily_value_change": daily_change,
        })

    for it in items:
        it["weight"] = it["value"] / total_value * 100 if total_value else 0

    daily_change_value = sum(it["daily_value_change"] for it in items)
    cash_value = sum(it["value"] for it in items if it["type"] == "cash")
    # Kapanan pozisyonlardan gelen gerçekleşmiş K/Z (portfolio.json'da tutulur).
    realized = float(portfolio.get("realized_pnl_try") or 0)
    return {
        "items": items,
        "total_value": total_value,
        "total_cost": total_cost,
        "total_pnl": total_value - total_cost,
        "total_pnl_pct": (total_value - total_cost) / total_cost * 100 if total_cost else 0,
        "realized_pnl": realized,
        "cash_value": cash_value,
        "cash_weight": cash_value / total_value * 100 if total_value else 0,
        "invested_value": total_value - cash_value,
        "daily_change_value": daily_change_value,
        "daily_change_pct": daily_change_value / total_prev_value * 100
                            if total_prev_value else 0,
    }


# --------------------------------------------------------------------------- #
#  Sinyaller + gerekçeli yorum
# --------------------------------------------------------------------------- #
def _fund_signal(fund: dict, bist: dict) -> dict:
    """Bir fon için Ekle/Tut/Azalt eğilimi + gerekçe listesi üretir."""
    reasons = []
    score = 0  # + ekle yönlü, - azalt yönlü

    y1 = fund.get("yield_1m")
    y3 = fund.get("yield_3m")
    peer1 = (fund.get("peer", {}).get("1m") or {})

    # 1) Aşırı ısınma / ortalamaya dönüş riski
    if y1 is not None and y1 > 25:
        score -= 2
        reasons.append(f"Son 1 ayda +%{y1:.0f} gibi olağanüstü bir koşu var; "
                       f"bu seviyeler ortalamaya dönüş (sert düzeltme) riskini artırır.")
    elif y1 is not None and y1 < 0:
        score += 1
        reasons.append(f"Son 1 ay %{y1:.0f} ile geri çekilmiş; momentum soğumuş.")

    # 2) Akranlarına göre durum
    pf, pc = peer1.get("fund"), peer1.get("category")
    if pf is not None and pc is not None:
        if pf > pc * 2:
            score -= 1
            reasons.append(f"Kategori ortalaması +%{pc:.0f} iken fon +%{pf:.0f} — "
                           f"akranlarını çok aşan bu fark yüksek 'beta' demektir: "
                           f"düşüşte de daha sert düşebilir.")
        elif pf < pc:
            reasons.append(f"Son ay akran ortalamasının ({pc:.0f}%) altında kaldı (%{pf:.0f}).")

    # 3) Konsantrasyon (içerik yoğunluğu)
    top = fund.get("top_holdings", [])
    top3 = sum(h["weight"] for h in top[:3])
    if top3 >= 35:
        score -= 1
        reasons.append(f"İlk 3 hisse portföyün ~%{top3:.0f}'ini oluşturuyor — "
                       f"yoğunlaşma yüksek, tek bir hissedeki sert düşüş fonu çok etkiler.")

    # 4) Genel piyasa zemini
    dd = bist.get("drawdown_from_peak")
    if dd is not None and dd < -8:
        score -= 1
        reasons.append(f"BIST zirveden %{dd:.0f} geri çekilmiş; agresif hisse fonları "
                       f"bu ortamda endeksten daha kırılgandır.")

    if score >= 1:
        trend, color = "Ekle/Tut", "pos"
    elif score <= -2:
        trend, color = "Kâr realize et / Azalt", "warn"
    else:
        trend, color = "Tut (yönet)", "neutral"

    return {"trend": trend, "color": color, "score": score, "reasons": reasons,
            "top3_weight": top3}


def _overlap(funds: dict) -> list:
    """İki fonun ortak tuttuğu hisseleri bulur (çeşitlendirme yanılsaması riski)."""
    sets = {}
    for code, f in funds.items():
        sets[code] = {h["code"] for h in f.get("top_holdings", [])}
    codes = list(sets)
    common = []
    if len(codes) >= 2:
        common = sorted(set.intersection(*sets.values()))
    return common


# --------------------------------------------------------------------------- #
#  Olay-temelli uyarılar (sadece gerektiğinde)
# --------------------------------------------------------------------------- #
def build_alerts(valuation: dict, market: dict) -> list:
    """Yalnızca gerçekten dikkat gerektiren durumlarda uyarı üretir.
    Sakin günlerde boş liste döner -> arayüzde hiçbir şey görünmez."""
    alerts = []

    def signed(v):
        return ("+" if v >= 0 else "") + _tr(v, 0)

    # 1) Varlık bazlı sert günlük hareket (±%4)
    for it in valuation["items"]:
        dp = it.get("daily_pct") or 0
        if abs(dp) >= 4:
            up = dp > 0
            alerts.append({
                "level": "pos" if up else "warn", "code": it["code"],
                "text": f"{it['code']} bugün %{_tr(dp, 1)} ile sert {'yükseldi' if up else 'düştü'} "
                        f"({signed(it['daily_value_change'])} ₺).",
            })

    # 2) Portföy geneli büyük günlük değişim (±%2,5)
    pdp = valuation.get("daily_change_pct") or 0
    if abs(pdp) >= 2.5:
        up = pdp > 0
        alerts.append({
            "level": "pos" if up else "warn", "code": None,
            "text": f"Portföyün bugün %{_tr(pdp, 1)} {'değer kazandı' if up else 'değer kaybetti'} "
                    f"({signed(valuation['daily_change_value'])} ₺).",
        })

    # 3) BIST aşırı alım / aşırı satım ve zirveden sert düşüş
    b = market.get("bist", {})
    rsi = b.get("rsi")
    if rsi is not None:
        if rsi >= 70:
            alerts.append({"level": "warn", "code": None,
                "text": f"BIST 100 aşırı alım bölgesinde (RSI {rsi:.0f}) — kısa vadede temkinli ol."})
        elif rsi <= 30:
            alerts.append({"level": "info", "code": None,
                "text": f"BIST 100 aşırı satım bölgesinde (RSI {rsi:.0f}) — toparlanma fırsatı izlenebilir."})
    dd = b.get("drawdown_from_peak")
    if dd is not None and dd <= -10:
        alerts.append({"level": "warn", "code": None,
            "text": f"BIST 100 son zirvesinden %{_tr(abs(dd), 0)} geri çekildi; agresif hisse fonların "
                    f"daha kırılgan olabilir."})

    # 4) Fon aşırı ısınma -> kâr realizasyonu düşünülebilir (1 aylık getiri ≥ %35)
    for code, f in market.get("funds", {}).items():
        y = f.get("yield_1m")
        if y is not None and y >= 35:
            alerts.append({"level": "warn", "code": code,
                "text": f"{code} son 1 ayda +%{_tr(y, 0)} ile aşırı ısınmış — bir miktar kâr "
                        f"realizasyonu düşünülebilir."})

    # 5) Atıl nakit — yatırılmayan para enflasyon karşısında reel olarak erir (≥ %10)
    cw = valuation.get("cash_weight") or 0
    if cw >= 10:
        alerts.append({"level": "info", "code": "NAKIT",
            "text": f"Portföyünün %{_tr(cw, 1)}'i ({_tr(valuation['cash_value'])} ₺) nakitte "
                    f"bekliyor. Nakit seni düşüşten korur ama uzun süre beklerse enflasyon "
                    f"karşısında reel değer kaybeder."})

    return alerts


# --------------------------------------------------------------------------- #
#  Tam analiz + günlük rapor
# --------------------------------------------------------------------------- #
def full_analysis() -> dict:
    portfolio = load_portfolio()
    market = gather_market(portfolio)
    valuation = value_portfolio(portfolio, market)

    # Fon sinyalleri
    signals = {}
    for code, f in market["funds"].items():
        if f.get("price"):
            signals[code] = _fund_signal(f, market["bist"])

    overlap = _overlap(market["funds"])
    alerts = build_alerts(valuation, market)

    # Günlük snapshot ve geçmişten momentum
    allocation = {it["code"]: round(it["weight"], 1) for it in valuation["items"]}
    history = record_snapshot(valuation["total_value"], allocation)
    momentum = _momentum_from_history(history)

    report_text = _build_report_text(valuation, market, signals, overlap, momentum)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "valuation": valuation,
        "market": market,
        "signals": signals,
        "alerts": alerts,
        "overlap": overlap,
        "momentum": momentum,
        "report_text": report_text,
        "history": history[-60:],
    }


def _momentum_from_history(history: list) -> dict:
    if len(history) < 2:
        return {"available": False}
    last = history[-1]["total"]
    prev = history[-2]["total"]
    peak = max(h["total"] for h in history)
    return {
        "available": True,
        "vs_prev_pct": (last - prev) / prev * 100 if prev else 0,
        "drawdown_from_peak": (last - peak) / peak * 100 if peak else 0,
        "days_tracked": len(history),
    }


# --------------------------------------------------------------------------- #
#  Rapor metni (gerekçeli, Türkçe)
# --------------------------------------------------------------------------- #
def _tr(n, d=0) -> str:
    """Türkçe sayı biçimi: 18361 -> '18.361', 0.81 -> '0,81'."""
    s = f"{n:,.{d}f}"  # 18,361.00
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def _build_report_text(valuation, market, signals, overlap, momentum) -> str:
    """İndirilebilir .txt raporu — tamamen DÜZYAZI, çizgi/tire tablosu YOK."""
    P = []
    v = valuation
    tarih = datetime.now().strftime("%d.%m.%Y")
    dc = v["daily_change_value"]
    yon = "değer kazandı" if dc >= 0 else "değer kaybetti"

    P.append(f"{tarih} — Günlük Portföy Raporu")

    # Özet paragrafı
    P.append(
        f"Portföyünün toplam değeri {_tr(v['total_value'])} ₺. Bugün "
        f"{_tr(abs(dc))} ₺ {yon} (%{_tr(abs(v['daily_change_pct']),2)}). "
        f"Açılıştan bu yana toplam kâr/zararın {_tr(v['total_pnl'])} ₺ "
        f"(%{_tr(v['total_pnl_pct'],1)})."
    )

    # Gerçekleşmiş K/Z (kapanan pozisyonlar)
    if v.get("realized_pnl"):
        r = v["realized_pnl"]
        P.append(
            f"Bunun dışında kapanan pozisyonlardan {_tr(abs(r))} ₺ gerçekleşmiş "
            f"{'kâr' if r >= 0 else 'zarar'} var; yukarıdaki kâr/zarar yalnızca hâlâ "
            f"elinde tuttuğun varlıkları kapsar."
        )

    # Nakit durumu
    if v.get("cash_value"):
        P.append(
            f"Portföyünün {_tr(v['cash_value'])} ₺'si (%{_tr(v['cash_weight'], 1)}) şu an "
            f"nakitte, yatırılmayı bekliyor. Yatırılmış kısım {_tr(v['invested_value'])} ₺. "
            f"Nakit kısa vadede seni dalgalanmadan korur; ancak uzun süre beklerse "
            f"enflasyon karşısında reel olarak erir."
        )

    # Güne en çok etki eden varlık
    mover = max(v["items"], key=lambda it: abs(it["daily_value_change"]))
    P.append(
        f"Güne en çok etki eden varlık {mover['name'] or mover['code']} oldu "
        f"(bugün %{_tr(mover['daily_pct'],1)}). Dağılımın: "
        + ", ".join(f"{it['code']} %{_tr(it['weight'], 2)}" for it in v["items"]) + "."
    )

    # Piyasa zemini
    b, g = market["bist"], market["gold"]
    if b.get("price"):
        P.append(
            f"Piyasa zemini: BIST 100 {_tr(b['price'])} seviyesinde (bugün "
            f"%{_tr(b['daily_pct'],1)}), son zirvesinden %{_tr(abs(b['drawdown_from_peak']),1)} "
            f"uzakta ve RSI {b.get('rsi') or 0:.0f} ile "
            f"{'nötr' if 40 <= (b.get('rsi') or 50) <= 60 else 'aşırı' }. "
            + (f"Gram altın {_tr(g['price'])} ₺ (bugün %{_tr(g['daily_pct'],1)})." if g.get("price") else "")
        )

    # Fonlar — düzyazı
    for code, sig in signals.items():
        f = market["funds"][code]
        cumle = " ".join(sig["reasons"]) if sig["reasons"] else \
            "Belirgin bir uyarı yok; trendle uyumlu seyrediyor."
        P.append(f"{code} ({f.get('name','')}) için eğilim: {sig['trend']}. {cumle}")

    # Hisseler — düzyazı
    for it in v["items"]:
        if it["type"] != "stock":
            continue
        st = market.get("stocks", {}).get(it["code"], {})
        kz = it["pnl"]
        s = (f"{it['code']} ({it.get('name') or ''}) {_tr(it['price'], 2)} ₺ seviyesinde. "
             f"{_tr(it['amount'], 0)} lotluk pozisyonun {_tr(it['value'])} ₺ değerinde "
             f"(portföyün %{_tr(it['weight'], 1)}'i); {_tr(it['cost'])} ₺ maliyete karşılık "
             f"{_tr(abs(kz))} ₺ {'kârda' if kz >= 0 else 'zararda'} "
             f"(%{_tr(abs(it['pnl_pct']), 1)}).")
        if not it.get("daily_known"):
            s += (f" Günlük değişim hesaplanamıyor: ne önceki kapanış ne de geçerli bir "
                  f"maliyet var ({st.get('days_of_data', 0)} günlük veri).")
        elif it.get("daily_basis") == "ipo_price":
            unit_cost = it["cost"] / it["amount"] if it["amount"] else 0
            s += (f" Bugün %{_tr(it['daily_pct'], 1)}. Bu ilk işlem günü olduğu için "
                  f"günlük değişim, önceki kapanış yerine halka arz fiyatına "
                  f"({_tr(unit_cost, 2)} ₺) göre hesaplandı — kazanç gerçekten bugüne ait. "
                  f"Yarından itibaren normal günlük hesap devreye girer; RSI ve trend "
                  f"göstergeleri de veri birikince eklenir.")
        else:
            s += f" Bugün %{_tr(it['daily_pct'], 1)}."
            if it.get("new_listing"):
                s += (" Halka arzın üzerinden az zaman geçti; ilk haftalar genelde çok "
                      "oynak olur, RSI gibi göstergeler veri birikince anlamlı hale gelir.")
        P.append(s)

    if overlap:
        P.append(
            f"Çeşitlendirme uyarısı: İki fonun da ortak tuttuğu hisseler var "
            f"({', '.join(overlap)}). Benzer şeyleri tuttukları için bu iki fonu birlikte "
            f"tutmak düşündüğün kadar çeşitlendirme sağlamaz; bir düşüşte birlikte düşerler."
        )

    P.append("Not: Bu rapor halka açık verilerle üretilmiş otomatik bir analizdir, "
             "yatırım tavsiyesi değildir. Emirleri sen verirsin.")
    return "\n\n".join(P)
