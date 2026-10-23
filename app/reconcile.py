"""
Ekstre ↔ portföy mutabakatı
===========================
Ayrıştırılmış ekstreyi mevcut portföyle karşılaştırır, DEĞİŞİKLİK LİSTESİ ve
önerilen yeni portföyü üretir.

TASARIM KARARI — sessizce uygulamaz:
Bu projede iki kez elle yanlış veri girildi (KTLEV satılmıştı ama uygulamada
duruyordu; maliyet piyasa değeriyle karıştırıldı). Otomatik içe aktarma sessizce
üzerine yazarsa, bayat veya biçimi değişmiş bir ekstre portföyü fark edilmeden
bozar — üstelik kullanıcı doğru sanır. Bu yüzden burada yalnızca ÖNERİ üretilir;
her değişikliği kullanıcı ayrı ayrı onaylar.

MİDAS DIŞI VARLIKLAR KORUNUR:
Ekstre yalnızca Midas'taki pozisyonları içerir. Altın (ve Midas'ta olmayan diğer
varlıklar) ekstrede görünmediği için "kapanmış" sayılmaz — dokunulmaz.
"""

from __future__ import annotations

from datetime import datetime

# Ekstrede görünmesi beklenen türler. Diğerleri (altın) Midas dışıdır.
BROKER_TYPES = {"fund", "stock"}


def _amount(h: dict) -> float:
    if h["type"] == "gold":
        return float(h.get("grams") or 0)
    if h["type"] == "cash":
        return float(h.get("amount_try") or 0)
    return float(h.get("units") or 0)


def _as_of_date(as_of: str | None):
    try:
        return datetime.strptime((as_of or "").strip(), "%d/%m/%y").date()
    except ValueError:
        return None


def _iso_date(s: str | None):
    try:
        return datetime.strptime((s or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _statement_age_days(as_of: str | None) -> int | None:
    if not as_of:
        return None
    try:
        d = datetime.strptime(as_of.strip(), "%d/%m/%y")
        return (datetime.now().date() - d.date()).days
    except ValueError:
        return None


def diff(statement: dict, portfolio: dict) -> dict:
    """Ekstre ile portföyü karşılaştırır.

    Dönen: {"changes": [...], "proposed": {...}, "warnings": [...]}
    Her değişiklik: {id, kind, code, baslik, detay, onerilen(bool)}
      kind: add | update | close | cash | realized
      `onerilen` = kutunun varsayılan olarak işaretli gelip gelmeyeceği.
    """
    changes: list[dict] = []
    warnings: list[str] = []

    age = _statement_age_days(statement.get("as_of"))
    if age is not None and age > 1:
        warnings.append(
            f"Ekstre {statement.get('as_of')} tarihli ({age} gün önce). Bu tarihten "
            f"sonraki işlemler ekstrede YOKTUR; pozisyon kapatma önerilerini "
            f"dikkatli onayla.")

    holdings = [dict(h) for h in portfolio.get("holdings", [])]
    by_code = {h.get("code", "").upper(): h for h in holdings}
    st_pos = {p["code"].upper(): p for p in statement.get("positions", [])}

    # 1) Ekstredeki pozisyonlar -> ekle veya güncelle
    for code, p in st_pos.items():
        cur = by_code.get(code)
        if cur is None:
            changes.append({
                "id": f"add:{code}", "kind": "add", "code": code,
                "baslik": f"{code} eklenecek",
                "detay": f"{p['units']:g} {'adet' if p['type'] == 'fund' else 'lot'} · "
                         f"maliyet {p['cost_try']:,.2f} ₺".replace(",", "."),
                "onerilen": True,
                "_row": {"type": p["type"], "code": code, "name": p.get("name") or code,
                         "cost_try": p["cost_try"],
                         "units": p["units"]},
            })
            continue
        old_amt, old_cost = _amount(cur), float(cur.get("cost_try") or 0)
        type_fix = p.get("type") and cur.get("type") != p["type"]
        if (abs(old_amt - p["units"]) > 1e-6 or abs(old_cost - p["cost_try"]) > 0.01
                or type_fix):
            detay = (f"{old_amt:g} → {p['units']:g} · maliyet "
                     f"{old_cost:,.2f} → {p['cost_try']:,.2f} ₺").replace(",", ".")
            if type_fix:
                tr = {"fund": "fon", "stock": "hisse"}
                detay += (f" · tür düzeltmesi: {tr.get(cur.get('type'), cur.get('type'))}"
                          f" → {tr.get(p['type'], p['type'])}")
            changes.append({
                "id": f"upd:{code}", "kind": "update", "code": code,
                "baslik": f"{code} güncellenecek",
                "detay": detay,
                "onerilen": True,
                "_row": {**cur, "units": p["units"], "cost_try": p["cost_try"],
                         "type": p.get("type") or cur.get("type")},
            })

    # 2) Portföyde olup ekstrede olmayan aracı-kurum varlıkları -> kapanmış olabilir
    st_date = _as_of_date(statement.get("as_of"))
    for h in holdings:
        code = h.get("code", "").upper()
        if h.get("type") not in BROKER_TYPES or code in st_pos:
            continue
        # EKSTRE TARİHİNDEN SONRA EKLENEN VARLIK ATLANIR.
        # O tarihte henüz portföyde olmadığı için ekstrede görünmemesi normaldir;
        # "satılmış" sayıp silmek veri kaybı olur (BKRGY 02/09'da alındı, ekstre
        # 26/08 tarihliydi -> yanlışlıkla kapatılacaktı).
        added = _iso_date(h.get("added_on"))
        if st_date and added and added > st_date:
            warnings.append(
                f"{code} ekstre tarihinden sonra ({h['added_on']}) eklendiği için "
                f"mutabakat dışı bırakıldı.")
            continue
        changes.append({
            "id": f"close:{code}", "kind": "close", "code": code,
            "baslik": f"{code} kaldırılacak",
            "detay": f"Ekstrede yok — satılmış olabilir. "
                     f"Şu an {_amount(h):g} adet/lot kayıtlı."
                     + (" Ekstre bayat olabilir, kontrol et." if age and age > 1 else ""),
            # Bayat ekstrede kapatma önerisi RİSKLİ -> varsayılan işaretsiz
            "onerilen": not (age is not None and age > 1),
        })

    # 3) Nakit
    st_cash = statement.get("cash_try")
    cash_row = next((h for h in holdings if h.get("type") == "cash"
                     and h.get("code") == "NAKIT"), None)
    if st_cash is not None:
        cur_cash = float(cash_row.get("amount_try") or 0) if cash_row else 0.0
        if abs(cur_cash - st_cash) > 0.01:
            changes.append({
                "id": "cash", "kind": "cash", "code": "NAKIT",
                "baslik": "Nakit güncellenecek",
                "detay": f"{cur_cash:,.2f} → {st_cash:,.2f} ₺".replace(",", "."),
                "onerilen": True, "_value": st_cash,
            })

    # 4) Gerçekleşmiş K/Z — DÖNEM FARKINDA
    # Bir ekstre yalnızca KENDİ tarih aralığındaki işlemleri bilir. Tek günlük bir
    # ekstre "gerçekleşmiş 0" der; bu "toplam kazanç 0" DEMEK DEĞİL, "bu dönemde
    # kapanış yok" demektir. ESKİ HATA: ekstrenin toplamı olduğu gibi benimseniyordu
    # -> 10/09 tek günlük ekstresi +1.082,45'lik gerçek kazancı 0'a indirdi.
    # Kural:
    #   a) Ekstre, daha önce benimsenen aralığı KAPSIYORSA -> onun toplamı yetkili.
    #   b) Daha dar/sonraki bir pencereyse -> sadece `realized_through` SONRASI
    #      satışlar eklenir; maliyet bizim tuttuğumuz ortalama maliyetten gelir.
    #   c) Aralık kaydı yoksa (eski veri) -> yalnızca ARTIŞ benimsenir, asla düşürülmez.
    cur_real = float(portfolio.get("realized_pnl_try") or 0)
    r_from = _iso_date(portfolio.get("realized_from"))
    r_thru = _iso_date(portfolio.get("realized_through"))
    p_start = _as_of_date(statement.get("period_start"))
    p_end = st_date
    st_real = statement.get("realized_total")

    new_real, new_from, new_thru = None, r_from, r_thru
    if r_from is None and r_thru is None:
        if st_real is not None and st_real > cur_real + 0.01:
            new_real, new_from, new_thru = st_real, p_start, p_end
        elif st_real is not None and st_real < cur_real - 0.01:
            warnings.append(
                "Ekstredeki gerçekleşmiş K/Z mevcut kayıttan düşük; ekstre muhtemelen "
                "daha kısa bir dönemi kapsıyor. Mevcut değer korundu.")
    elif p_start and p_end and r_from and r_thru and p_start <= r_from and p_end >= r_thru:
        if st_real is not None:
            new_real, new_from, new_thru = st_real, p_start, p_end
    elif r_thru and p_end and p_end > r_thru:
        added, skipped = 0.0, []
        for t in statement.get("trades", []):
            if t.get("status") != "Gerçekleşti" or t.get("side") != "Satış":
                continue
            try:
                td = datetime.fromisoformat(t["date"]).date()
            except (ValueError, TypeError):
                continue
            if td <= r_thru:
                continue                      # bu satış zaten sayıldı
            h = by_code.get(t["symbol"])
            units = _amount(h) if h else 0
            if units > 0:
                unit_cost = float(h.get("cost_try") or 0) / units
                added += t["amount"] - unit_cost * min(t["filled"], units)
            else:
                skipped.append(t["symbol"])
        if skipped:
            warnings.append(f"Maliyeti bilinmeyen satış(lar) K/Z'ye eklenmedi: "
                            f"{', '.join(sorted(set(skipped)))}")
        if abs(added) > 0.005:
            new_real, new_thru = round(cur_real + added, 2), p_end

    if new_real is not None and abs(new_real - cur_real) > 0.01:
        changes.append({
            "id": "realized", "kind": "realized", "code": None,
            "baslik": "Gerçekleşmiş kâr/zarar güncellenecek",
            "detay": f"{cur_real:,.2f} → {new_real:,.2f} ₺".replace(",", "."),
            "onerilen": True, "_value": new_real,
            "_from": new_from.isoformat() if new_from else None,
            "_through": new_thru.isoformat() if new_thru else None,
        })

    # 5) ESKİ EKSTRE KORUMASI
    # Uygulamanın son mutabık olduğu ekstreden daha ESKİ bir ekstre, o tarihten
    # sonra satılan varlıkları geri ekler ve nakdi geriye çeker (test: 26/08
    # ekstresi, 01/09'da satılan CITAS'ı geri ekleyip nakdi 514,80 -> 11,94
    # yapmayı öneriyordu). Böyle bir ekstrede hiçbir öneri önceden işaretlenmez;
    # izleyici de onu tamamen atlar (`stale`).
    synced = _iso_date(portfolio.get("synced_as_of"))
    stale = bool(st_date and synced and st_date < synced)
    if stale:
        warnings.insert(0,
            f"Bu ekstre ({statement.get('as_of')}), uygulamanın son mutabık olduğu "
            f"ekstreden ({synced.strftime('%d/%m/%y')}) ESKİ. Öneriler işaretsiz "
            f"bırakıldı: eski bir ekstre sonradan sattığın varlıkları geri ekleyip "
            f"nakdi geriye çekebilir. Emin değilsen uygulama.")
        for c in changes:
            c["onerilen"] = False

    return {"changes": changes, "warnings": warnings, "stale": stale,
            "as_of": statement.get("as_of"), "age_days": age}


def apply(portfolio: dict, statement: dict, accepted_ids: list[str]) -> dict:
    """Yalnızca ONAYLANAN değişiklikleri uygular, yeni portföyü döndürür."""
    accepted = set(accepted_ids or [])
    d = diff(statement, portfolio)
    out = {k: v for k, v in portfolio.items() if k != "holdings"}
    holdings = [dict(h) for h in portfolio.get("holdings", [])]
    by_code = {h.get("code", "").upper(): h for h in holdings}

    for ch in d["changes"]:
        if ch["id"] not in accepted:
            continue
        if ch["kind"] == "add":
            holdings.append(ch["_row"])
        elif ch["kind"] == "update":
            cur = by_code.get(ch["code"])
            if cur:
                cur.update({k: v for k, v in ch["_row"].items() if k != "grams"})
        elif ch["kind"] == "close":
            holdings = [h for h in holdings if h.get("code", "").upper() != ch["code"]]
            by_code.pop(ch["code"], None)
        elif ch["kind"] == "cash":
            cur = next((h for h in holdings if h.get("type") == "cash"
                        and h.get("code") == "NAKIT"), None)
            if cur:
                cur["amount_try"] = ch["_value"]
                cur["cost_try"] = ch["_value"]
            else:
                holdings.append({"type": "cash", "code": "NAKIT", "name": "TL",
                                 "amount_try": ch["_value"], "cost_try": ch["_value"]})
        elif ch["kind"] == "realized":
            out["realized_pnl_try"] = ch["_value"]
            # Hangi tarih aralığının sayıldığını sakla — sonraki dar ekstreler
            # aynı satışları iki kez saymasın, kazancı da silmesin.
            if ch.get("_from"):
                out["realized_from"] = ch["_from"]
            if ch.get("_through"):
                out["realized_through"] = ch["_through"]

    # Uygulanan en yeni ekstrenin tarihini sakla -> daha eskisi "stale" sayılır.
    st_d = _as_of_date(statement.get("as_of"))
    prev = _iso_date(portfolio.get("synced_as_of"))
    if accepted and st_d and (prev is None or st_d > prev):
        out["synced_as_of"] = st_d.isoformat()

    out["holdings"] = holdings
    return out
