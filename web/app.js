// Dağılım paleti: hepsi aynı soğuk aileden, doygunluk düşük. Mor/menekşe YOK
// (accent ile yarışıyordu). Altın ve nakit sıraya bakılmaksızın sabit renk alır.
const COLORS = ["#58a0c4", "#3da891", "#b3766f", "#7f93a6", "#c98f6a", "#4d7f9e"];
const CASH_COLOR = "#6d818d";  // nakit: sönük gri (yatırılmamış para)
const GOLD_COLOR = "#d3a259";  // altın: her zaman amber — anlamı renginden okunsun

// Küçük, tek çizgi kalınlığında ikonlar (emoji yerine).
const ICON = {
  eye: '<svg class="ico" viewBox="0 0 24 24"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="2.6"/></svg>',
  eyeOff: '<svg class="ico" viewBox="0 0 24 24"><path d="M4 4l16 16"/><path d="M9.9 5.9A9.6 9.6 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-3.3 4"/><path d="M6.4 8A16.7 16.7 0 0 0 2.5 12S6 18.5 12 18.5a9.5 9.5 0 0 0 3.4-.6"/></svg>',
  x: '<svg class="ico" viewBox="0 0 24 24"><path d="M6 6 18 18"/><path d="M18 6 6 18"/></svg>',
  alert: '<svg class="ico" viewBox="0 0 24 24"><path d="M12 8.5v4.2"/><path d="M12 16.4h.01"/><circle cx="12" cy="12" r="9"/></svg>',
};

const fmt = (n, d = 0) =>
  (n ?? 0).toLocaleString("tr-TR", { minimumFractionDigits: d, maximumFractionDigits: d });
const money = (n, d = 0) => fmt(n, d) + " ₺";
const pct = (n, d = 1) => (n >= 0 ? "+" : "") + fmt(n, d) + "%";
const cls = (n) => (n > 0 ? "pos" : n < 0 ? "neg" : "");

async function load(force = false) {
  show("loading");
  try {
    const res = await fetch("/api/dashboard" + (force ? "?refresh=1" : ""));
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "bilinmeyen hata");
    render(data);
    show("content");
  } catch (e) {
    const box = document.getElementById("loading");
    box.removeAttribute("aria-busy");
    box.innerHTML = `<div class="load-error">
      <p class="le-title">Veri alınamadı</p>
      <p class="le-msg">${esc(e.message)}</p>
      <button class="btn" id="retryBtn">Tekrar dene</button>
    </div>`;
    document.getElementById("retryBtn").addEventListener("click", () => load(true));
  }
}

function show(which) {
  document.getElementById("loading").classList.toggle("hidden", which !== "loading");
  document.getElementById("content").classList.toggle("hidden", which !== "content");
}

function render(d) {
  latestData = d;  // "Alış Ekle"de güncel fiyatı bilmek için sakla
  const v = d.valuation;
  document.getElementById("updated").textContent = "Güncelleme: " + d.date;

  // KPI
  const daily = document.getElementById("kpiDaily");
  daily.innerHTML = `<span class="${cls(v.daily_change_value)}">${money(v.daily_change_value)} (${pct(v.daily_change_pct)})</span>`;
  const pnl = document.getElementById("kpiPnl");
  const sign = (n) => (n > 0 ? "+" : "") + money(n);
  pnl.innerHTML = `<span class="${cls(v.total_pnl)}">${money(v.total_pnl)} (${pct(v.total_pnl_pct)})</span>` +
    (v.realized_pnl
      ? `<span class="kpi-sub">Kapanan pozisyonlardan
           <span class="${cls(v.realized_pnl)}">${sign(v.realized_pnl)}</span> gerçekleşmiş</span>`
      : "");
  // Nakit varsa toplam değerin altında "yatırılmış / nakit" kırılımı
  const totalSub = v.cash_value
    ? `<span class="kpi-sub">${money(v.invested_value)} yatırımda ·
         <span class="cash-t">${money(v.cash_value)} nakit</span></span>`
    : "";
  document.getElementById("kpiTotal").innerHTML = money(v.total_value) + totalSub;

  renderAlerts(d.alerts);
  renderDonut(v.items);
  renderMarket(d.market);
  renderAssets(v.items, d.alerts);
  renderReport(d);
  renderHistory(d.history);

  // Bayat veri uyarısı
  const stale = [d.market.bist, d.market.gold, ...Object.values(d.market.funds),
                 ...Object.values(d.market.stocks || {})]
    .some(x => x && x.stale);
  if (stale) {
    let warn = document.getElementById("staleWarn");
    if (!warn) {
      warn = document.createElement("div");
      warn.id = "staleWarn"; warn.className = "stale";
      warn.textContent = "⚠ Bazı veriler internet olmadığı için son bilinen değerlerden gösteriliyor.";
      document.getElementById("content").prepend(warn);
    }
  }
}

function renderDonut(items) {
  const svg = document.getElementById("donut");
  const total = items.reduce((s, i) => s + i.value, 0);
  const R = 70, C = 2 * Math.PI * R, cx = 100, cy = 100;
  let offset = 0;
  let html = `<circle cx="${cx}" cy="${cy}" r="${R}" fill="none" stroke="var(--elev)" stroke-width="22"/>`;
  const legend = [];
  const gap = items.length > 1 ? 3 : 0;  // dilimler arasında küçük nefes payı
  items.forEach((it, idx) => {
    const frac = total ? it.value / total : 0;
    const len = frac * C;
    const seg = Math.max(len - gap, 0.1);
    // Nakit sönük gri, altın amber — sıradan bağımsız, anlam renkten okunsun.
    const color = it.type === "cash" ? CASH_COLOR
      : it.type === "gold" ? GOLD_COLOR
      : COLORS[idx % COLORS.length];
    html += `<circle cx="${cx}" cy="${cy}" r="${R}" fill="none" stroke="${color}"
      stroke-width="22" stroke-dasharray="${seg} ${C - seg}"
      stroke-dashoffset="${-(offset + gap / 2)}" transform="rotate(-90 ${cx} ${cy})"
      stroke-linecap="butt"/>`;
    offset += len;
    legend.push(`<div class="legend-item"><span class="dot" style="background:${color}"></span>
      ${it.code} <span class="lv">%${fmt(it.weight, 2)}</span></div>`);
  });
  html += `<text x="${cx}" y="${cy - 2}" text-anchor="middle" fill="var(--text)"
    font-family="Space Grotesk, sans-serif" font-size="19" font-weight="600"
    letter-spacing="-0.7">${fmt(total / 1000, 1)}K</text>
    <text x="${cx}" y="${cy + 16}" text-anchor="middle" fill="var(--muted)"
    font-size="10" letter-spacing="0.3">toplam ₺</text>`;
  svg.innerHTML = html;
  document.getElementById("legend").innerHTML = legend.join("");
}

function renderMarket(m) {
  const rows = [];
  const b = m.bist;
  if (b && b.price) {
    rows.push(mrow("BIST 100", fmt(b.price),
      `Zirveden %${fmt(b.drawdown_from_peak)} · RSI ${fmt(b.rsi || 0)}`, b.daily_pct));
  }
  const g = m.gold;
  if (g && g.price) rows.push(mrow("Gram Altın", money(g.price), "Yahoo Finance", g.daily_pct));
  document.getElementById("market").innerHTML = rows.join("");
}

function mrow(name, val, meta, dpct) {
  return `<div class="mrow">
    <div><div class="mname">${name}</div><div class="mmeta">${meta}</div></div>
    <div class="mval">${val}<div class="mmeta ${cls(dpct)}">${pct(dpct)}</div></div>
  </div>`;
}

function renderAssets(items, alerts) {
  // Aktif uyarısı olan varlıkları işaretle (küçük nokta).
  const flagged = new Set((alerts || []).filter(a => a.code).map(a => a.code));
  const html = items.map(it => {
    const flag = flagged.has(it.code)
      ? `<span class="asset-flag" title="Bu varlıkla ilgili bir uyarı var">${ICON.alert}</span>` : "";
    const isCash = it.type === "cash";
    // Günlük değişim yalnızca GERÇEKTEN bilinmiyorsa gizlenir (ilk işlem günü).
    // İkinci günden itibaren normal gösterilir — rozet dursa bile.
    const noDaily = it.daily_known === false;
    const badge = it.new_listing
      ? ` <span class="badge-ipo" title="Yeni halka arz — geçmiş veri kısıtlı">yeni halka arz</span>` : "";
    // Nakitte "adet" ve "bugün %" anlamsız — yerine durumunu yaz.
    const sub = isCash
      ? "Yatırılmayı bekliyor"
      : `${it.code} · ${fmt(it.amount, it.type === "gold" ? 1 : 0)} ${it.unit}`;
    // İlk işlem gününde günlük değişim halka arz fiyatına göre ölçülür — bunu gizleme,
    // ama neye göre ölçüldüğünü de belirt.
    const ipoBasis = it.daily_basis === "ipo_price";
    const dailyTxt = `bugün <span class="${cls(it.daily_pct)}">${pct(it.daily_pct)}</span>` +
      (ipoBasis ? `<span class="ref-note" title="İlk işlem günü: önceki kapanış olmadığı için halka arz fiyatına göre hesaplandı">*</span>` : "");
    const right = isCash
      ? `%${fmt(it.weight, 2)} · <span class="cash-t">nakit</span>`
      : noDaily
        ? `%${fmt(it.weight, 2)} · <span class="muted-t">günlük veri yok</span>`
        : `%${fmt(it.weight, 2)} · ${dailyTxt}`;
    return `<div class="asset${isCash ? " asset-cash" : ""}">
      <div class="asset-top">
        <div><div class="asset-name">${it.name || it.code}${badge}${flag}</div>
          <div class="asset-code">${sub}</div></div>
        <div class="asset-val"><div class="v">${money(it.value)}</div>
          <div class="w">${right}</div></div>
      </div>
    </div>`;
  }).join("");
  document.getElementById("assets").innerHTML = html;
}

// Olay-temelli uyarılar — yalnızca varsa görünür.
function renderAlerts(alerts) {
  const el = document.getElementById("alerts");
  if (!alerts || !alerts.length) { el.innerHTML = ""; el.classList.add("hidden"); return; }
  el.classList.remove("hidden");
  el.innerHTML = `<div class="alerts-head">Uyarılar · ${alerts.length}</div>` +
    alerts.map(a => `<div class="alert alert-${a.level}">
      <span class="alert-bar"></span>
      <span class="alert-text">${a.text}</span>
    </div>`).join("");
}

function renderReport(d) {
  const v = d.valuation, m = d.market;
  const dc = v.daily_change_value;
  const yon = dc >= 0 ? "değer kazandı" : "değer kaybetti";
  const mover = v.items.reduce((a, b) =>
    Math.abs(b.daily_value_change) > Math.abs(a.daily_value_change) ? b : a);

  let html = "";

  // Özet düzyazı
  html += `<p>Bugün portföyünün toplam değeri <b>${money(v.total_value)}</b>.
    Gün içinde <span class="${cls(dc)}">${money(Math.abs(dc))} ${yon}</span>
    (<span class="${cls(dc)}">${pct(v.daily_change_pct)}</span>).
    Açılıştan bu yana toplam kâr/zararın
    <span class="${cls(v.total_pnl)}">${money(v.total_pnl)} (${pct(v.total_pnl_pct)})</span>.
    Güne en çok etki eden varlık <b>${mover.name || mover.code}</b> oldu
    (bugün <span class="${cls(mover.daily_pct)}">${pct(mover.daily_pct)}</span>).</p>`;

  if (v.realized_pnl) {
    html += `<p>Kapanan pozisyonlardan ayrıca
      <span class="${cls(v.realized_pnl)}">${money(v.realized_pnl)}</span> <b>gerçekleşmiş</b>
      kâr/zararın var. Yukarıdaki toplam kâr/zarar yalnızca hâlâ elinde tuttuğun
      varlıkları kapsar.</p>`;
  }

  if (v.cash_value) {
    html += `<p><b>Nakit durumu.</b> ${money(v.cash_value)}
      (%${fmt(v.cash_weight, 1)}) yatırılmayı bekliyor; yatırımdaki kısım
      ${money(v.invested_value)}. Nakit kısa vadede seni dalgalanmadan korur, ancak
      uzun süre beklerse enflasyon karşısında reel olarak erir.</p>`;
  }

  // Gerçek tablo: varlıklar
  html += `<table class="rtable">
    <thead><tr><th>Varlık</th><th>Değer</th><th>Ağırlık</th><th>Bugün %</th><th>Bugün ₺</th></tr></thead>
    <tbody>` +
    v.items.map(it => {
      const dv = Math.abs(it.daily_value_change) < 0.005 ? 0 : it.daily_value_change;  // çok küçükse nötr
      const dvTxt = (dv > 0 ? "+" : "") + money(dv, 2);
      const dvCls = dv > 0 ? "pos" : dv < 0 ? "neg" : "";
      // Günlük veri gerçekten yoksa 0 yerine "—" göster (sahte sıfır olmasın).
      const noDaily = it.daily_known === false;
      return `<tr>
      <td>${it.code}</td>
      <td>${money(it.value)}</td>
      <td>%${fmt(it.weight, 2)}</td>
      <td class="${noDaily ? "" : cls(it.daily_pct)}">${noDaily ? "—" : pct(it.daily_pct)}</td>
      <td class="${noDaily ? "" : dvCls}">${noDaily ? "—" : dvTxt}</td>
    </tr>`;
    }).join("") +
    `</tbody></table>`;

  // Piyasa zemini düzyazı
  const b = m.bist, g = m.gold;
  if (b && b.price) {
    const rsiTxt = b.rsi >= 70 ? "aşırı alımda" : b.rsi <= 30 ? "aşırı satımda" : "nötr bölgede";
    html += `<p><b>Piyasa zemini.</b> BIST 100 ${fmt(b.price)} seviyesinde
      (bugün <span class="${cls(b.daily_pct)}">${pct(b.daily_pct)}</span>), son zirvesinden
      %${fmt(Math.abs(b.drawdown_from_peak))} uzakta ve RSI ${fmt(b.rsi || 0)} ile ${rsiTxt}.
      ${g && g.price ? `Gram altın ${money(g.price)} (bugün <span class="${cls(g.daily_pct)}">${pct(g.daily_pct)}</span>).` : ""}</p>`;
  }

  // Fonlar düzyazı
  html += `<p><b>Fon değerlendirmesi.</b></p>`;
  Object.entries(d.signals).forEach(([code, sig]) => {
    const f = m.funds[code] || {};
    const cumle = sig.reasons.length ? sig.reasons.join(" ")
      : "Belirgin bir uyarı yok; trendle uyumlu seyrediyor.";
    html += `<p><b>${code}</b> — ${f.name || ""} · <i>eğilim: ${sig.trend}.</i> ${cumle}</p>`;
  });

  // Hisseler
  const stocks = v.items.filter(it => it.type === "stock");
  if (stocks.length) {
    html += `<p><b>Hisse değerlendirmesi.</b></p>`;
    stocks.forEach(it => {
      const s = (m.stocks || {})[it.code] || {};
      const kz = `${money(it.cost)} maliyete karşılık
        <span class="${cls(it.pnl)}">${it.pnl > 0 ? "+" : ""}${money(it.pnl)}
        (${pct(it.pnl_pct)})</span>`;
      const ipo = it.daily_basis === "ipo_price";
      html += it.daily_known === false
        ? `<p><b>${it.code}</b> — ${it.name || ""} · ${money(it.price, 2)} ·
           <i>yeni halka arz.</i> Pozisyonun ${money(it.value)} (portföyün
           %${fmt(it.weight, 1)}'i); ${kz}. Günlük değişim hesaplanamıyor: ne önceki
           kapanış ne de geçerli bir maliyet var.</p>`
        : `<p><b>${it.code}</b> — ${it.name || ""} · ${money(it.price, 2)}
           (bugün <span class="${cls(it.daily_pct)}">${pct(it.daily_pct)}</span>${ipo ? "*" : ""}).
           Pozisyonun ${money(it.value)}, portföyün %${fmt(it.weight, 1)}'i; ${kz}.
           ${ipo ? `<i>* İlk işlem günü olduğu için günlük değişim, önceki kapanış yerine
             halka arz fiyatına (${money(it.cost / it.amount, 2)}) göre hesaplandı — bu
             kazanç gerçekten bugüne ait. Yarından itibaren normal günlük hesap devreye
             girer.</i>` : ""}
           ${it.new_listing && !ipo ? "Halka arzın üzerinden az zaman geçti; ilk haftalar genelde çok oynak olur." : ""}</p>`;
    });
  }

  // Çeşitlendirme
  if (d.overlap && d.overlap.length) {
    html += `<p><b>Çeşitlendirme uyarısı.</b> İki fonun ortak tuttuğu hisseler
      (${d.overlap.join(", ")}) var. Benzer içerikleri tuttukları için bu iki fonu birlikte
      tutmak düşündüğün kadar çeşitlendirme sağlamaz; bir düşüşte birlikte düşerler.</p>`;
  }

  html += `<p class="report-foot">Bu rapor halka açık verilerle üretilmiş otomatik bir
    analizdir, yatırım tavsiyesi değildir.</p>`;

  document.getElementById("report").innerHTML = html;
}

// Sessiz tazeleme: spinner göstermeden veriyi güncelle (10 sn'de bir).
async function silentRefresh() {
  try {
    const res = await fetch("/api/dashboard");
    const data = await res.json();
    if (data.ok) render(data);
  } catch (e) { /* sessizce geç */ }
}

// ----------------------------------------------------------------------- //
//  Değer geçmişi grafiği (SVG çizgi)
// ----------------------------------------------------------------------- //
function renderHistory(history) {
  const el = document.getElementById("history");
  const chg = document.getElementById("histChange");
  if (!history || history.length < 2) {
    chg.textContent = "";
    el.innerHTML = `<p class="hist-empty">Geçmiş birikiyor — uygulamayı her açtığında
      o günün değeri kaydedilir. Birkaç gün sonra burada grafik oluşacak.</p>`;
    return;
  }

  const W = 760, H = 220, padL = 8, padR = 8, padT = 16, padB = 26;
  const vals = history.map(h => h.total);
  let min = Math.min(...vals), max = Math.max(...vals);
  if (min === max) { min -= 1; max += 1; }
  const pad = (max - min) * 0.15; min -= pad; max += pad;
  const x = i => padL + (i / (history.length - 1)) * (W - padL - padR);
  const y = v => padT + (1 - (v - min) / (max - min)) * (H - padT - padB);

  const pts = history.map((h, i) => [x(i), y(h.total)]);
  const line = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
  const area = `${line} L ${pts.at(-1)[0].toFixed(1)} ${H - padB} L ${pts[0][0].toFixed(1)} ${H - padB} Z`;

  const first = history[0].total, last = history.at(-1).total;
  const diff = last - first, dpct = first ? diff / first * 100 : 0;
  chg.innerHTML = `<span class="${cls(diff)}">${money(diff)} (${pct(dpct)})</span>
    <span class="hist-range">· ${history.length} gün</span>`;

  const lbl = (s) => { const [Y, M, D] = s.split("-"); return `${D}.${M}`; };
  const stroke = diff >= 0 ? "var(--pos)" : "var(--neg)";

  const grid = [0.25, 0.5, 0.75].map(f => {
    const gy = (padT + f * (H - padT - padB)).toFixed(1);
    return `<line x1="${padL}" x2="${W - padR}" y1="${gy}" y2="${gy}"
      stroke="rgba(255,255,255,.05)" stroke-width="1"/>`;
  }).join("");

  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="none" class="hist-svg">
    <defs><linearGradient id="hg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${stroke}" stop-opacity="0.28"/>
      <stop offset="100%" stop-color="${stroke}" stop-opacity="0"/>
    </linearGradient></defs>
    ${grid}
    <path d="${area}" fill="url(#hg)"/>
    <path d="${line}" fill="none" stroke="${stroke}" stroke-width="2.5"
      stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${pts.at(-1)[0].toFixed(1)}" cy="${pts.at(-1)[1].toFixed(1)}" r="4" fill="${stroke}"/>
    <text x="${padL}" y="${H - 6}" class="hist-axis">${lbl(history[0].date)}</text>
    <text x="${W - padR}" y="${H - 6}" text-anchor="end" class="hist-axis">${lbl(history.at(-1).date)}</text>
  </svg>`;
}

// ----------------------------------------------------------------------- //
//  Portföy düzenleme (uygulama içi)
// ----------------------------------------------------------------------- //
let editState = null;
let latestData = null;

async function openEditor() {
  const res = await fetch("/api/portfolio");
  editState = await res.json();
  renderEditRows();
  autoSyncRefresh();
  document.getElementById("editError").classList.add("hidden");
  document.getElementById("editModal").classList.remove("hidden");
}

function closeEditor() {
  document.getElementById("editModal").classList.add("hidden");
}

const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/"/g, "&quot;")
  .replace(/</g, "&lt;").replace(/>/g, "&gt;");

// Aramadan gelen fiyatlar: portföyde HENÜZ olmayan bir hissenin fiyatını da bilelim
// (yeni eklenen satırda "+ Alış" güncel fiyatı otomatik doldurabilsin).
const SYMBOL_PRICES = {};

function renderEditRows() {
  const rows = editState.holdings.map((h, i) => {
    const isCash = h.type === "cash";
    const isStock = h.type === "stock";
    const amount = isCash ? (h.amount_try ?? 0)
      : h.type === "gold" ? (h.grams ?? 0) : (h.units ?? 0);
    const amountTitle = isStock ? "lot" : isCash ? "TL tutarı" : h.type === "gold" ? "gram" : "adet";
    const hid = !!h.hidden;
    return `<tr data-i="${i}" data-hidden="${hid ? 1 : 0}" class="${hid ? "row-hidden" : ""}">
      <td>
        <select data-f="type">
          <option value="fund" ${h.type === "fund" ? "selected" : ""}>Fon</option>
          <option value="stock" ${isStock ? "selected" : ""}>Hisse</option>
          <option value="gold" ${h.type === "gold" ? "selected" : ""}>Altın</option>
          <option value="cash" ${isCash ? "selected" : ""}>Nakit</option>
        </select>
      </td>
      <td class="code-cell">
        <input data-f="code" value="${esc(h.code)}" size="9"
          ${isStock ? 'placeholder="ara…" autocomplete="off"' : ""}>
        ${isStock ? '<div class="sym-results hidden"></div>' : ""}
      </td>
      <td><input data-f="name" value="${esc(h.name)}"></td>
      <td><input data-f="amount" type="number" step="any" value="${amount}" title="${amountTitle}"></td>
      <td><input data-f="cost" type="number" step="any" value="${h.cost_try ?? 0}"
        ${isCash ? 'readonly title="Nakitte maliyet = tutar"' : ""}></td>
      <td class="row-actions">
        ${isCash ? "" : `<button class="row-buy" data-buy="${i}">+ Alış</button>
        <button class="row-sell" data-sell="${i}">− Satış</button>`}
        <button class="row-hide" data-hide="${i}"
          aria-label="${hid ? "Göster" : "Gizle"}"
          title="${hid ? "Gizli: hiçbir hesaba katılmıyor. Göstermek için tıkla."
                       : "Gizle: portföyde kalır ama toplam/K-Z hesabına girmez."}"
          >${hid ? ICON.eyeOff : ICON.eye}</button>
        <button class="row-del" data-del="${i}" aria-label="Sil" title="Satırı sil">${ICON.x}</button>
      </td>
    </tr>`;
  }).join("");
  document.getElementById("editRows").innerHTML = rows;

  document.querySelectorAll(".row-del").forEach(b =>
    b.addEventListener("click", () => { collectRows(); editState.holdings.splice(+b.dataset.del, 1); renderEditRows(); }));
  document.querySelectorAll(".row-buy").forEach(b =>
    b.addEventListener("click", () => showBuyForm(+b.dataset.buy)));
  document.querySelectorAll(".row-sell").forEach(b =>
    b.addEventListener("click", () => showSellForm(+b.dataset.sell)));
  document.querySelectorAll(".row-hide").forEach(b =>
    b.addEventListener("click", () => {
      const i = +b.dataset.hide;
      collectRows();
      editState.holdings[i].hidden = !editState.holdings[i].hidden;
      renderEditRows();
    }));
  // Tür değişince satırı yeniden çiz: hisse arama kutusu, nakit kilidi ve
  // "+ Alış" düğmesi yeni türe göre ayarlansın.
  document.querySelectorAll('#editRows [data-f="type"]').forEach(sel =>
    sel.addEventListener("change", () => { collectRows(); renderEditRows(); }));
  document.querySelectorAll("#editRows tr[data-i]").forEach(tr => {
    if (tr.querySelector(".sym-results")) attachSymbolSearch(tr);
  });
}

// Hisse kodu / şirket adı ile arama — /api/symbols (651 BIST hissesi).
function attachSymbolSearch(tr) {
  const input = tr.querySelector('[data-f="code"]');
  const box = tr.querySelector(".sym-results");
  let timer = null;
  const close = () => { box.innerHTML = ""; box.classList.add("hidden"); };

  input.addEventListener("input", () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (!q) return close();
    timer = setTimeout(async () => {
      try {
        const r = await fetch(`/api/symbols?q=${encodeURIComponent(q)}&limit=8`);
        const d = await r.json();
        if (!d.results || !d.results.length) return close();
        box.innerHTML = d.results.map(s =>
          `<button type="button" class="sym-item" data-code="${esc(s.code)}"
             data-name="${esc(s.name)}" data-price="${s.price ?? ""}">
             <b>${esc(s.code)}</b><span>${esc(s.name)}</span>
             <em>${s.price ? money(s.price, 2) : ""}</em>
           </button>`).join("");
        box.classList.remove("hidden");
        box.querySelectorAll(".sym-item").forEach(btn =>
          btn.addEventListener("mousedown", (e) => {   // blur'dan ÖNCE çalışsın
            e.preventDefault();
            input.value = btn.dataset.code;
            tr.querySelector('[data-f="name"]').value = btn.dataset.name;
            if (btn.dataset.price) SYMBOL_PRICES[btn.dataset.code] = parseFloat(btn.dataset.price);
            close();
          }));
      } catch (e) { close(); }
    }, 180);
  });
  input.addEventListener("blur", () => setTimeout(close, 150));
}

function currentPrice(code) {
  // Önce portföydeki canlı veri, yoksa aramadan gelen fiyat.
  const item = latestData?.valuation?.items?.find(it => it.code === code);
  if (item && item.type === "cash") return 1;
  if (item && item.type === "gold") return latestData.market.gold?.price ?? null;
  if (item && item.type === "stock") return latestData.market.stocks?.[code]?.price ?? null;
  const f = latestData?.market?.funds?.[code];
  if (f) return f.price;
  return SYMBOL_PRICES[code] ?? null;
}

// Portföydeki nakit satırını bul (alışı nakitten düşmek için).
function findCashHolding() {
  return editState.holdings.find(h => h.type === "cash") || null;
}

// "+ Alış": lot/gram VEYA toplam TL gir -> adedi ve maliyeti otomatik artır.
// İstersen tutarı nakit satırından düşer (aynı parayı iki kez saymayı önler).
function showBuyForm(i) {
  collectRows();
  document.querySelectorAll("#editRows tr.buy-form").forEach(r => r.remove());
  const h = editState.holdings[i];
  const price = currentPrice(h.code);
  const tr = document.querySelector(`#editRows tr[data-i="${i}"]`);
  if (!tr) return;
  const cash = findCashHolding();
  const cashAvail = cash ? (cash.amount_try || 0) : 0;
  const birim = h.type === "gold" ? "gram" : h.type === "stock" ? "lot" : "adet";

  const form = document.createElement("tr");
  form.className = "buy-form";
  form.innerHTML = `<td colspan="6"><div class="buy-row">
    <b>${esc(h.code) || "Yeni"} alış ekle:</b>
    <label>${birim}<input class="buy-qty" type="number" step="any" placeholder="0"></label>
    <label>birim fiyat ₺<input class="buy-price" type="number" step="any" value="${price ?? ""}"></label>
    <label>toplam ₺<input class="buy-total" type="number" step="any" placeholder="0"></label>
    ${cash ? `<label class="buy-cash"><input type="checkbox" class="buy-from-cash" checked>
      nakitten düş <span class="muted-t">(${money(cashAvail)})</span></label>` : ""}
    <button class="btn small buy-apply">Ekle</button>
    <button class="btn ghost small buy-cancel">Vazgeç</button>
    <span class="buy-preview"></span>
  </div></td>`;
  tr.after(form);

  const qty = form.querySelector(".buy-qty");
  const pr = form.querySelector(".buy-price");
  const tot = form.querySelector(".buy-total");
  const fromCash = form.querySelector(".buy-from-cash");
  const prev = form.querySelector(".buy-preview");
  const num = (el) => parseFloat(el.value) || 0;

  const preview = () => {
    const q = num(qty), c = num(tot);
    if (!q || !c) { prev.innerHTML = ""; return; }
    const short = fromCash && fromCash.checked && c > cashAvail + 1e-9;
    prev.innerHTML = `→ +${fmt(q, q % 1 ? 2 : 0)} ${birim}, +${money(c)} maliyet` +
      (fromCash && fromCash.checked
        ? short ? ` <span class="neg">· nakit yetersiz (${money(cashAvail)})</span>`
                : ` · nakit ${money(cashAvail - c)}'ye iner`
        : "");
  };
  // Üç alan birbirine bağlı: lot×fiyat = toplam. Hangisini yazarsan diğeri güncellenir.
  const fromQty = () => { const p = num(pr); if (p) tot.value = +(num(qty) * p).toFixed(2); preview(); };
  const fromTotal = () => { const p = num(pr); if (p) qty.value = +(num(tot) / p).toFixed(6); preview(); };
  qty.addEventListener("input", fromQty);
  pr.addEventListener("input", () => { if (num(qty)) fromQty(); else fromTotal(); });
  tot.addEventListener("input", fromTotal);
  if (fromCash) fromCash.addEventListener("change", preview);

  form.querySelector(".buy-cancel").addEventListener("click", () => form.remove());
  form.querySelector(".buy-apply").addEventListener("click", () => {
    const q = num(qty), cost = num(tot);
    const err = document.getElementById("editError");
    if (q <= 0 || cost <= 0) { qty.focus(); return; }
    if (fromCash && fromCash.checked && cost > cashAvail + 1e-9) {
      err.textContent = `Nakit yetersiz: ${money(cashAvail)} var, ${money(cost)} gerekiyor.`;
      err.classList.remove("hidden");
      return;
    }
    err.classList.add("hidden");
    if (h.type === "gold") h.grams = (h.grams || 0) + q;
    else h.units = (h.units || 0) + q;
    h.cost_try = (h.cost_try || 0) + cost;
    if (fromCash && fromCash.checked && cash) {
      cash.amount_try = +(cashAvail - cost).toFixed(2);
      cash.cost_try = cash.amount_try;   // nakitte maliyet = tutar
    }
    renderEditRows();
  });
  qty.focus();
}

// "− Satış": elle yapılınca en yorucu işlem buydu — adet düş, maliyeti oranla,
// gerçekleşmiş K/Z'yi hesapla, nakde ekle, pozisyon bittiyse satırı sil.
// Hepsini tek formda yapar (ortalama maliyet yöntemi).
function showSellForm(i) {
  collectRows();
  document.querySelectorAll("#editRows tr.buy-form").forEach(r => r.remove());
  const h = editState.holdings[i];
  const isGold = h.type === "gold";
  const held = (isGold ? h.grams : h.units) || 0;
  const birim = isGold ? "gram" : h.type === "stock" ? "lot" : "adet";
  const price = currentPrice(h.code);
  const tr = document.querySelector(`#editRows tr[data-i="${i}"]`);
  if (!tr || held <= 0) return;
  const cash = findCashHolding();

  const form = document.createElement("tr");
  form.className = "buy-form";
  form.innerHTML = `<td colspan="6"><div class="buy-row sell-row">
    <b class="neg">${esc(h.code)} satış:</b>
    <label>${birim}<input class="sell-qty" type="number" step="any" value="${held}"></label>
    <label>birim fiyat ₺<input class="sell-price" type="number" step="any" value="${price ?? ""}"></label>
    <label>toplam ₺<input class="sell-total" type="number" step="any"></label>
    ${cash ? `<label class="buy-cash"><input type="checkbox" class="sell-to-cash" checked> nakde ekle</label>` : ""}
    <button class="btn small sell-apply">Sat</button>
    <button class="btn ghost small buy-cancel">Vazgeç</button>
    <span class="buy-preview"></span>
  </div></td>`;
  tr.after(form);

  const q = form.querySelector(".sell-qty");
  const p = form.querySelector(".sell-price");
  const t = form.querySelector(".sell-total");
  const toCash = form.querySelector(".sell-to-cash");
  const prev = form.querySelector(".buy-preview");
  const num = el => parseFloat(el.value) || 0;

  const preview = () => {
    const qty = num(q), proceeds = num(t);
    if (!qty || !proceeds) { prev.innerHTML = ""; return; }
    if (qty > held + 1e-9) {
      prev.innerHTML = `<span class="neg">Elinde ${fmt(held, 2)} ${birim} var.</span>`;
      return;
    }
    const unitCost = (h.cost_try || 0) / held;
    const pnl = proceeds - unitCost * qty;
    const kalan = held - qty;
    prev.innerHTML = `→ ${money(proceeds)} tahsil · gerçekleşmiş
      <span class="${cls(pnl)}">${pnl > 0 ? "+" : ""}${money(pnl)}</span>` +
      (kalan < 1e-9 ? " · pozisyon kapanır" : ` · ${fmt(kalan, 2)} ${birim} kalır`);
  };
  const fromQty = () => { if (num(p)) t.value = +(num(q) * num(p)).toFixed(2); preview(); };
  const fromTotal = () => { if (num(p)) q.value = +(num(t) / num(p)).toFixed(6); preview(); };
  q.addEventListener("input", fromQty);
  p.addEventListener("input", () => (num(q) ? fromQty() : fromTotal()));
  t.addEventListener("input", fromTotal);
  fromQty();

  form.querySelector(".buy-cancel").addEventListener("click", () => form.remove());
  form.querySelector(".sell-apply").addEventListener("click", () => {
    const qty = num(q), proceeds = num(t);
    const err = document.getElementById("editError");
    if (qty <= 0 || proceeds <= 0) { q.focus(); return; }
    if (qty > held + 1e-9) {
      err.textContent = `Elinde ${fmt(held, 2)} ${birim} var, ${fmt(qty, 2)} satılamaz.`;
      err.classList.remove("hidden");
      return;
    }
    err.classList.add("hidden");
    const unitCost = (h.cost_try || 0) / held;
    const pnl = proceeds - unitCost * qty;
    // Gerçekleşmiş K/Z portföy kökünde birikir (açık pozisyon K/Z'sine karışmaz).
    editState.realized_pnl_try = +(((editState.realized_pnl_try || 0) + pnl)).toFixed(2);
    if (toCash && toCash.checked && cash) {
      cash.amount_try = +(((cash.amount_try || 0) + proceeds)).toFixed(2);
      cash.cost_try = cash.amount_try;
    }
    const kalan = held - qty;
    if (kalan < 1e-9) {
      editState.holdings.splice(i, 1);                 // pozisyon tamamen kapandı
    } else {
      if (isGold) h.grams = +kalan.toFixed(6); else h.units = +kalan.toFixed(6);
      h.cost_try = +((h.cost_try || 0) - unitCost * qty).toFixed(2);
    }
    renderEditRows();
  });
  q.focus();
}

function collectRows() {
  const out = [];
  document.querySelectorAll("#editRows tr").forEach(tr => {
    const typeEl = tr.querySelector('[data-f="type"]');
    if (!typeEl) return;  // inline alış-formu satırı — atla
    const g = f => tr.querySelector(`[data-f="${f}"]`).value.trim();
    const type = typeEl.value;
    const amount = parseFloat(g("amount")) || 0;
    const row = { type, code: g("code").toUpperCase(), name: g("name"), cost_try: parseFloat(g("cost")) || 0 };
    if (tr.dataset.hidden === "1") row.hidden = true;
    if (type === "gold") row.grams = amount;
    else if (type === "cash") { row.amount_try = amount; row.cost_try = amount; }  // nakitte K/Z olmaz
    else row.units = amount;
    out.push(row);
  });
  editState.holdings = out;
}

async function saveEditor() {
  collectRows();
  const err = document.getElementById("editError");
  const bad = editState.holdings.find(h => !h.code);
  if (bad) { err.textContent = "Her satırda bir kod olmalı."; err.classList.remove("hidden"); return; }
  const btn = document.getElementById("editSave");
  btn.disabled = true; btn.textContent = "Kaydediliyor…";
  try {
    await fetch("/api/portfolio", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(editState),
    });
    closeEditor();
    await load(true);  // yeni portföyle taze veri
  } catch (e) {
    err.textContent = "Kaydedilemedi: " + e.message; err.classList.remove("hidden");
  } finally {
    btn.disabled = false; btn.textContent = "Kaydet";
  }
}

function addRow() {
  collectRows();
  // Varsayılan "hisse": arama kutusu hemen gelsin, en sık eklenen tür bu.
  editState.holdings.push({ type: "stock", code: "", name: "", units: 0, cost_try: 0 });
  renderEditRows();
  const last = document.querySelector("#editRows tr:last-child [data-f='code']");
  if (last) last.focus();
}

// ----------------------------------------------------------------------- //
//  Ekstre ile mutabakat — asla sessizce uygulamaz, önce farkı gösterir
// ----------------------------------------------------------------------- //
function syncRender(d) {
  const box = document.getElementById("syncResult");
  box.classList.remove("hidden");
  if (!d.ok) {
    box.innerHTML = `<p class="sync-err">${esc(d.error)}</p>`;
    return;
  }
  const uyari = (d.warnings || []).map(w => `<p class="sync-warn">${esc(w)}</p>`).join("");
  if (!d.changes.length) {
    box.innerHTML = uyari + `<p class="sync-ok">Ekstre (${esc(d.as_of || "")}) portföyle
      uyumlu — değişiklik yok.</p>`;
    return;
  }
  box.innerHTML = uyari +
    `<p class="sync-src">Kaynak: ${esc(d.kaynak || "")}${d.as_of ? ` · ekstre ${esc(d.as_of)}` : ""}</p>` +
    d.changes.map(c => `
      <label class="sync-item sync-${esc(c.kind)}">
        <input type="checkbox" value="${esc(c.id)}" ${c.onerilen ? "checked" : ""}>
        <span><b>${esc(c.baslik)}</b><br><span class="sync-detail">${esc(c.detay)}</span></span>
      </label>`).join("") +
    `<div class="sync-foot">
       <button id="syncApply" class="btn small">Seçilenleri uygula</button>
       <span class="sync-note">İşaretsiz bırakılanlar uygulanmaz.</span>
     </div>`;
  document.getElementById("syncApply").addEventListener("click", async () => {
    const accept = [...box.querySelectorAll("input:checked")].map(i => i.value);
    const r = await fetch("/api/statement/apply", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ accept }),
    });
    const res = await r.json();
    if (!res.ok) { box.innerHTML = `<p class="sync-err">${esc(res.error)}</p>`; return; }
    box.innerHTML = `<p class="sync-ok">${res.applied} değişiklik uygulandı.</p>`;
    await openEditor();          // düzenleyiciyi yeni portföyle tazele
    await load(true);
  });
}

async function syncFromMail() {
  const box = document.getElementById("syncResult");
  box.classList.remove("hidden");
  box.innerHTML = `<p class="sync-note">E-posta kutusu taranıyor…</p>`;
  const r = await fetch("/api/statement/sync", { method: "POST" });
  if (r.status === 428) {
    box.innerHTML = `<p class="sync-err">Önce e-posta ayarlarını gir.</p>`;
    document.getElementById("syncCfg").classList.remove("hidden");
    return;
  }
  syncRender(await r.json());
}

// "Portföy güncelle" düğmesi: postayı sorgula, güvenli değişiklikleri uygula,
// kapatma önerileri varsa onay için göster.
async function syncNow() {
  const btn = document.getElementById("syncNowBtn");
  const banner = document.getElementById("syncBanner");
  btn.disabled = true;
  banner.classList.remove("hidden");
  banner.className = "sync-banner sync-b-info";
  banner.innerHTML = "Gmail'deki en güncel ekstre aranıyor…";
  try {
    const r = await fetch("/api/statement/refresh", { method: "POST" });
    const d = await r.json();
    if (!d.ok) {
      banner.className = "sync-banner sync-b-err";
      banner.innerHTML = esc(d.error) +
        (r.status === 428 ? ` <button class="btn small" id="bnCfg">Ayarları aç</button>` : "");
      const c = document.getElementById("bnCfg");
      if (c) c.addEventListener("click", () => {
        openEditor().then(() => document.getElementById("syncCfg").classList.remove("hidden"));
      });
      return;
    }
    if (!d.new && !(d.applied || []).length && !(d.pending || []).length) {
      banner.className = "sync-banner sync-b-ok";
      banner.innerHTML = `Portföy ekstreyle uyumlu — değişiklik yok.` +
        (d.as_of ? ` <span class="muted-t">(ekstre ${esc(d.as_of)})</span>` : "");
      return;
    }
    const applied = d.applied || [], pending = d.pending || [];
    banner.className = "sync-banner " + (pending.length ? "sync-b-warn" : "sync-b-ok");
    banner.innerHTML =
      (applied.length
        ? `<b>${applied.length} değişiklik uygulandı:</b> ${applied.map(esc).join(" · ")}`
        : `<b>Otomatik uygulanacak değişiklik yok.</b>`) +
      (d.as_of ? ` <span class="muted-t">(ekstre ${esc(d.as_of)})</span>` : "") +
      (pending.length
        ? `<div class="sync-pending"><b>${pending.length} değişiklik onayını bekliyor:</b>` +
          pending.map(p => `<label class="sync-item sync-${esc(p.kind)}">
             <input type="checkbox" value="${esc(p.id)}">
             <span><b>${esc(p.baslik)}</b><br><span class="sync-detail">${esc(p.detay)}</span></span>
           </label>`).join("") +
          `<button class="btn small" id="bnApply">Seçilenleri uygula</button></div>`
        : "");
    if (applied.length) await load(true);
    const ap = document.getElementById("bnApply");
    if (ap) ap.addEventListener("click", async () => {
      const accept = [...banner.querySelectorAll("input:checked")].map(i => i.value);
      if (!accept.length) return;
      const res = await (await fetch("/api/statement/apply", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accept }),
      })).json();
      banner.className = "sync-banner " + (res.ok ? "sync-b-ok" : "sync-b-err");
      banner.innerHTML = res.ok
        ? `${res.applied} değişiklik daha uygulandı.`
        : esc(res.error);
      if (res.ok) await load(true);
    });
  } catch (e) {
    banner.className = "sync-banner sync-b-err";
    banner.textContent = "Bağlantı hatası: " + e.message;
  } finally {
    btn.disabled = false;
  }
}
document.getElementById("syncNowBtn").addEventListener("click", syncNow);

async function autoSyncRefresh() {
  try {
    const s = await (await fetch("/api/statement/auto")).json();
    document.getElementById("autoSync").checked = !!s.enabled;
    const bits = [];
    if (s.enabled) bits.push(`${Math.round((s.interval || 600) / 60)} dk'da bir kontrol`);
    if (s.last_check) bits.push(`son bakış ${s.last_check}`);
    if (s.last_error) bits.push(`⚠ ${s.last_error}`);
    document.getElementById("autoInfo").textContent = bits.join(" · ");
  } catch (e) { /* yoksay */ }
}

document.getElementById("autoSync").addEventListener("change", async (e) => {
  await fetch("/api/statement/auto", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: e.target.checked }),
  });
  autoSyncRefresh();
});

document.getElementById("syncUndo").addEventListener("click", async () => {
  const box = document.getElementById("syncResult");
  box.classList.remove("hidden");
  const r = await fetch("/api/statement/undo", { method: "POST" });
  const res = await r.json();
  box.innerHTML = res.ok
    ? `<p class="sync-ok">Geri alındı — portföy önceki haline döndü.</p>`
    : `<p class="sync-err">${esc(res.error)}</p>`;
  if (res.ok) { await openEditor(); await load(true); }
});

document.getElementById("syncMail").addEventListener("click", syncFromMail);
document.getElementById("syncFile").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  const box = document.getElementById("syncResult");
  box.classList.remove("hidden");
  box.innerHTML = `<p class="sync-note">Ekstre okunuyor…</p>`;
  const fd = new FormData();
  fd.append("file", f);
  const r = await fetch("/api/statement/upload", { method: "POST", body: fd });
  syncRender(await r.json());
  e.target.value = "";
});
document.getElementById("syncCfgBtn").addEventListener("click", async () => {
  const el = document.getElementById("syncCfg");
  el.classList.toggle("hidden");
  if (!el.classList.contains("hidden")) {
    const c = await (await fetch("/api/mail/config")).json();
    document.getElementById("cfgEmail").value = c.email || "";
    document.getElementById("cfgSender").value = c.sender || "midas";
  }
});
document.getElementById("cfgSave").addEventListener("click", async () => {
  const body = {
    email: document.getElementById("cfgEmail").value,
    password: document.getElementById("cfgPass").value,
    sender: document.getElementById("cfgSender").value,
  };
  const r = await fetch("/api/mail/config", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const res = await r.json();
  const box = document.getElementById("syncResult");
  box.classList.remove("hidden");
  box.innerHTML = res.ok
    ? `<p class="sync-ok">Ayarlar kaydedildi.</p>`
    : `<p class="sync-err">${esc(res.error)}</p>`;
  document.getElementById("cfgPass").value = "";
});

// ----------------------------------------------------------------------- //
//  Portföy asistanı (Claude)
//  Dışarı veri giden TEK yer burası — yalnızca kullanıcı soru sorunca.
// ----------------------------------------------------------------------- //
const aiHistory = [];
let aiBusy = false;

async function aiInit() {
  try {
    const s = await (await fetch("/api/ai/status")).json();
    document.getElementById("aiSetup").classList.toggle("hidden", !!s.configured);
    document.getElementById("aiPanel").classList.toggle("hidden", !s.configured);
  } catch (e) { /* asistan yoksa panel gizli kalsın */ }
}

function aiAppend(role, text) {
  const log = document.getElementById("aiLog");
  const el = document.createElement("div");
  el.className = "ai-msg ai-" + role;
  el.textContent = text;
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
  return el;
}

// Claude'un markdown'ı için asgari biçimleme (**kalın**, satır sonları).
function aiFormat(t) {
  return esc(t)
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/^- (.+)$/gm, "• $1")
    .replace(/\n/g, "<br>");
}

async function aiAsk(question) {
  if (aiBusy || !question.trim()) return;
  aiBusy = true;
  const send = document.getElementById("aiSend");
  send.disabled = true;
  aiAppend("user", question);
  aiHistory.push({ role: "user", text: question });
  const out = aiAppend("bot", "");
  out.classList.add("ai-typing");
  let full = "";

  try {
    const res = await fetch("/api/ai/ask", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history: aiHistory.slice(0, -1) }),
    });
    if (res.status === 428) {                       // anahtar yok
      out.textContent = "Önce bir API anahtarı gir.";
      document.getElementById("aiSetup").classList.remove("hidden");
      return;
    }
    // SSE akışını oku
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop();
      for (const p of parts) {
        const line = p.replace(/^data: /, "").trim();
        if (!line) continue;
        let msg; try { msg = JSON.parse(line); } catch { continue; }
        if (msg.error) { full += "\n\n⚠ " + msg.error; }
        else if (msg.t) { full += msg.t; }
        out.classList.remove("ai-typing");
        out.innerHTML = aiFormat(full);
        document.getElementById("aiLog").scrollTop = 1e9;
      }
    }
    aiHistory.push({ role: "assistant", text: full });
  } catch (e) {
    out.classList.remove("ai-typing");
    out.textContent = "Bağlantı hatası: " + e.message;
  } finally {
    aiBusy = false; send.disabled = false;
  }
}

document.getElementById("aiForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const inp = document.getElementById("aiInput");
  const q = inp.value;
  inp.value = "";
  aiAsk(q);
});
document.querySelectorAll(".ai-chip").forEach(b =>
  b.addEventListener("click", () => aiAsk(b.dataset.q)));
document.getElementById("aiKeySave").addEventListener("click", async () => {
  const el = document.getElementById("aiKey");
  if (!el.value.trim()) { el.focus(); return; }
  await fetch("/api/ai/status", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: el.value }),
  });
  el.value = "";
  aiInit();
});
aiInit();

// Kartlarda imleci izleyen ışık: CSS'in okuduğu --mx/--my değişkenlerini besler.
document.addEventListener("pointermove", (e) => {
  const card = e.target.closest ? e.target.closest(".card") : null;
  if (!card) return;
  const r = card.getBoundingClientRect();
  card.style.setProperty("--mx", `${e.clientX - r.left}px`);
  card.style.setProperty("--my", `${e.clientY - r.top}px`);
}, { passive: true });

document.getElementById("refreshBtn").addEventListener("click", () => load(true));
document.getElementById("editBtn").addEventListener("click", openEditor);
document.getElementById("editClose").addEventListener("click", closeEditor);
document.getElementById("editCancel").addEventListener("click", closeEditor);
document.getElementById("editSave").addEventListener("click", saveEditor);
document.getElementById("addRow").addEventListener("click", addRow);
document.getElementById("editModal").addEventListener("click", (e) => {
  if (e.target.id === "editModal") closeEditor();
});

load(false);
setInterval(silentRefresh, 10000);
