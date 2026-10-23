# Mimari ve geliştirici notları

Bu belge, kodu değiştirecek kişinin bilmesi gereken sözleşmeleri ve **daha önce
gerçekten hataya yol açmış** tuzakları toplar. Buradaki uyarıların çoğu teorik
değil; üretimde yanlış rakam gösterdikten sonra yazıldı.

## Dosya haritası

```
main.py            Başlatıcı: pencere / --tray modu, threaded WSGI, tek-örnek guard
serve.py           Yalnızca sunucu (port 8766) — önizleme/test
app/
  server.py        Flask + JSON API
  analysis.py      Değerleme, sinyaller, uyarılar, günlük rapor metni
  sources.py       Fiyat kaynakları + disk cache + BIST şirket evreni
  statement.py     Midas PDF ekstresi ayrıştırıcı
  reconcile.py     Ekstre ↔ portföy mutabakatı (öneri üretir, uygulamaz)
  mailbox.py       IMAP: posta kutusundan ekstre PDF'i çekme
  watcher.py       Arka plan izleyici (8 saatte bir)
  assistant.py     Claude entegrasyonu (portföy soru-cevap)
  portfolio.py     portfolio.json yükle/kaydet, yedek, günlük snapshot
  tray.py          Sistem tepsisi + bildirim
web/               index.html · style.css · app.js (vanilla, derleme yok)
data/              Kişisel veri — portfolio.example.json dışında .gitignore'da
```

## Veri sözleşmesi

```jsonc
{
  "currency": "TRY",
  "realized_pnl_try": 0,        // kapanan pozisyonlardan birikmiş K/Z
  "realized_from":   "YYYY-MM-DD",  // bu toplamın kapsadığı aralık
  "realized_through":"YYYY-MM-DD",
  "synced_as_of":    "YYYY-MM-DD",  // uygulanan en yeni ekstrenin tarihi
  "holdings": [
    { "type": "fund",  "code": "AFA", "units": 100,       "cost_try": 1000 },
    { "type": "stock", "code": "THYAO","units": 10,       "cost_try": 3000 },
    { "type": "gold",  "code": "ALTIN","grams": 1.0,      "cost_try": 6000 },
    { "type": "cash",  "code": "NAKIT","amount_try": 500, "cost_try": 500  }
  ]
}
```

Her varlıkta ayrıca `added_on` (eklenme tarihi, `save_portfolio` damgalar) ve
opsiyonel `hidden: true` bulunabilir.

- **`hidden`** → varlık dosyada kalır ama hiçbir yerde görünmez ve toplam değer /
  maliyet / K/Z / günlük değişim hesabına **girmez**; fiyatı bile çekilmez.
  Küçük artık bakiyeler oranları bozmasın diye. *Tutar anlamlı hale gelirse
  gizli bırakmak toplam değeri yanlış gösterir — bu bir kez başa geldi.*
- **Nakitte maliyet = tutar**; nakit sahte K/Z üretmez.
- **Gerçekleşmiş K/Z açık pozisyon K/Z'sine karıştırılmaz**, ayrı gösterilir.

## Fiyat kaynakları — tuzaklar

### TEFAS fonları
Resmî `tefas.gov.tr` ucu kapalı (404). `api.fintables.com` kullanılıyor; zorunlu
başlıklar olmadan **403** döner: tarayıcı `User-Agent`, `Origin: https://fintables.com`,
`Referer: https://fintables.com/`. Geçmiş günlük NAV serisi **yok** — bu yüzden
geçmişe dönük fon değer grafiği kurulamıyor (sahtesi bilerek yapılmadı).

### BIST hisseleri
Yahoo Finance `{KOD}.IS`.

> **Günlük bar serisi gün atlayabilir — günlük değişimi ondan türetme.**
> Yeni halka arzlarda görüldü: seri bir günü hiç içermedi, "önceki kapanış" iki
> gün öncesini gösterdi ve günlük değişim %21 çıktı (doğrusu %9,98 idi).
> **Çözüm:** fiyat ve önceki kapanış `_yf_quote()` ile **kotasyon ucundan**
> alınır (`fast_info.previousClose`). Bar serisi yalnızca RSI / zirveden düşüş /
> `days_of_data` için kullanılır. `result["daily_source"]` hangisinin
> kullanıldığını söyler — teşhiste ilk bakılacak alan.

### Yeni halka arzlarda gösterge üretilmez
Seri < 2 gün → `daily_pct=None`; < 5 gün → drawdown yok; < 15 gün → RSI yok;
< 20 gün → `new_listing=True`. Birkaç günlük veriden RSI uydurmak yanıltıcı olur.

> **`new_listing` ile `daily_known` karıştırılmamalı.** Rozet bilgi amaçlıdır;
> günlük değişimin gizlenmesini `daily_known` belirler. Bir ara ikisi aynı
> bayrağa bağlıydı ve hisse 20 gün boyunca "günlük veri yok" gösteriyordu.

> **İlk işlem günü:** önceki kapanış yoktur; günlük değişimin referansı **halka
> arz fiyatıdır** (= pozisyonun maliyeti). O günkü kazanç gerçekten o güne aittir,
> 0 saymak günlük kârı eksik gösterir. `item.daily_basis` = `prev_close` |
> `ipo_price` | `None`.

### Günlük değişim nasıl hesaplanır
Her varlık için `prev_value` tutulur ve **`değer − önceki değer`** kullanılır.
`değer × yüzde / 100` kestirmesi **yanlıştır** — yüzde eski değere göredir, yeni
değerle çarpınca değişim şişer (bir vakada 220,50 yerine 242,49 çıktı).

## Mutabakat güvenlik kuralları

Ekstre içe aktarma **sessizce uygulamaz**: `reconcile.diff` yalnızca öneri üretir,
her değişikliği kullanıcı ayrı onaylar. Dört kural bunu güvenli kılar:

**1. Ekstre tarihinden sonra eklenen varlığa dokunulmaz.**
Ekstre yalnızca kendi tarihine kadarki durumu bilir. `added_on` damgası ekstre
tarihinden sonraysa o varlık mutabakat dışı bırakılır. *Gerçek vaka: bir hisse
02/09'da alındı, eldeki ekstre 26/08 tarihliydi — bu kural olmasa otomatik
senkron 168 lotu silecekti.*

**2. Otomatik mod pozisyon kapatma uygulamaz.**
`watcher.check_once` yalnızca `kind != "close"` olanları uygular. Kapatmalar
kullanıcı onayına bırakılır; bildirimde "N değişiklik onay bekliyor" denir.

**3. Gerçekleşmiş K/Z dönem farkındadır.**
Bir ekstre yalnızca kendi tarih aralığını bilir. *Gerçek vaka: tek günlük bir
ekstre "gerçekleşmiş 0" dedi ve otomatik senkron birikmiş gerçek kazancı 0'a
indirdi.* `realized_from` / `realized_through` tutulur: ekstre bu aralığı
kapsıyorsa toplamı yetkilidir; daha dar bir pencereyse yalnızca `realized_through`
sonrası satışlar eklenir; aralık kaydı yoksa yalnızca artış benimsenir, asla
düşürülmez.

**4. Eski ekstre koruması (`stale`).**
Portföy, uygulanan en yeni ekstrenin tarihini `synced_as_of` olarak saklar. Ondan
eski bir ekstrede hiçbir öneri işaretli gelmez ve izleyici onu tamamen atlar.
*Gerçek vaka: eski bir ekstre, sonradan satılan bir hisseyi geri ekleyip nakdi
geriye çekmeyi öneriyordu.*

Her otomatik güncelleme öncesi `portfolio.backup.json` yazılır; tek tıkla geri alınır.

### Fon/hisse ayrımı
Öncelik: (1) işlem satırındaki emir türü (`"Fon Emri"` → fon), (2) BIST şirket
listesinde var mı (`get_bist_universe`), (3) kod uzunluğu (TEFAS fonu 3 harf,
BIST hissesi 4–5). *Gerçek vaka: tek günlük ekstrede işlem satırı olmadığı için
bir fon "hisse" sanıldı → Yahoo'da `KOD.IS` yok → **0 TL** göründü.*

### Ekstre ayrıştırıcı
PDF metni hücre hücre, her hücre ayrı satır gelir: portföy özeti 5 alanlık,
işlemler 12 alanlık bloklar. Düzen bozulursa ayrıştırıcı **sessizce yanlış sonuç
vermez, hata fırlatır**. Ekstrede TCKN/ad/adres de bulunur — bunlar **bilerek
ayrıştırılmaz**, hiçbir yere yazılmaz.

## Gizlilik sınırları

| Katman | Dışarı ne gider |
|---|---|
| Fiyat çekme | Yalnızca varlık kodları (halka açık uçlara) |
| IMAP | Hiçbir şey; salt okunur, yalnızca PDF eki indirilir |
| Claude asistanı | Portföy + piyasa bağlamı, **yalnızca soru sorulduğunda** |

Asistana giden bağlamda `owner`, `notes` gibi serbest metin alanları **bilerek
dışarıda bırakılır** (kişisel bilgi barındırabilir).

## Bilinen sınırlar

- **Para yatırma/çekme takip edilmiyor.** Değer geçmişi grafiği toplam değeri
  çizdiği için bankaya çekilen para grafikte kayıp gibi görünür. Çözüm yolu:
  ekstrenin "Hesap İşlemleri" bölümündeki yatırma/çekme satırlarını ayrıştırıp
  net sermaye akışını tutmak.
- **Geçmişe dönük fon değer grafiği yok** — kaynak geçmiş NAV vermiyor.
- **Midas API'si yok**; senkron ekstre üzerinden, kullanıcı tetiklemeli.
- Ekstre isterken **tek günlük değil, aralıklı** seçilmeli: tek gün pozisyon
  anlık görüntüsünü verir ama aradaki satış ve nakit hareketlerini göstermez.

## Geliştirirken

- Python kodu değişince **uygulama yeniden başlatılmalı** (Flask hot-reload yok).
- Arayüz dosyaları `no-store` ile sunulur; pencere eski JS'i önbellekten
  göstermez (bu daha önce "düzelttiğim hata hâlâ duruyor" sanrısına yol açtı).
- Windows'ta konsol çıktısı için `sys.stdout.reconfigure(encoding="utf-8")`.
