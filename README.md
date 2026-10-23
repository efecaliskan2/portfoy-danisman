# Portföy Danışman

BIST hisseleri, TEFAS fonları, gram altın ve nakitten oluşan portföyünü **tamamen
kendi bilgisayarında** izleyen masaüstü uygulaması. Günlük değerleme, gerekçeli
analiz, olay-temelli uyarılar ve Midas hesap ekstresinden otomatik mutabakat.

> Yatırım tavsiyesi aracı değildir. Üretilen yorumlar bilgilendirme amaçlıdır;
> uygulama emir vermez, alım-satım yapmaz.

## Güvenlik ilkeleri

- **Hiçbir aracı kuruma bağlanmaz.** Şifre/hesap bilgisi istemez, tutmaz.
- **Emir vermez.** Sadece analiz eder; kararı kullanıcı verir.
- Sunucu yalnızca `127.0.0.1` üzerinde çalışır, dışarıya açık değildir.
- İnternete yalnızca **halka açık fiyat verisini okumak** için çıkar.
- İki opsiyonel istisna, ikisi de kapalı gelir ve açıkça onay ister:
  - **Portföy asistanı** → soru sorduğunda portföy verisi Anthropic API'sine gider.
  - **Ekstre senkronu** → posta kutusunda Midas ekstresi aranır (salt okunur IMAP).
- Kişisel veri (`portfolio.json`, ekstreler, raporlar) ve sırlar (`secrets.json`)
  `.gitignore` ile depo dışında tutulur.

## Özellikler

| | |
|---|---|
| **Varlık türleri** | TEFAS fonu, BIST hissesi, gram altın, nakit |
| **Değerleme** | Günlük K/Z, toplam K/Z, ağırlıklar, gerçekleşmiş K/Z ayrı tutulur |
| **Piyasa zemini** | BIST 100 seviyesi, RSI(14), zirveden düşüş; gram altın |
| **Uyarılar** | Sert günlük hareket, RSI aşırı alım/satım, fon aşırı ısınma, atıl nakit |
| **Hisse arama** | 651 BIST şirketi, Türkçe duyarlı (koda veya şirket adına göre) |
| **Alış/satış** | Lot veya toplam ₺ ile giriş; nakitten otomatik düşme, satışta K/Z hesabı |
| **Ekstre senkronu** | Midas PDF ekstresini okur, farkı çıkarır, onayınla uygular |
| **Portföy asistanı** | Claude ile kendi verin üzerine soru-cevap (opsiyonel) |

## Kurulum

```bash
pip install -r requirements.txt
python main.py
```

İlk açılışta `data/portfolio.json` yoksa `data/portfolio.example.json` kopyalanır.
Portföyünü uygulama içinden **"Portföyü Düzenle"** ile girebilirsin.

### Çalıştırma modları

| Komut | Davranış |
|---|---|
| `python main.py` | Uygulama penceresi açılır (pywebview) |
| `python main.py --tray` | Sessiz; sistem tepsisine yerleşir, ekstre izleyicisi çalışır |
| `python serve.py` | Yalnızca sunucu → `http://127.0.0.1:8766` |

## Veri kaynakları

| Veri | Kaynak |
|---|---|
| TEFAS fon fiyatı, içerik, kategori kıyası | `api.fintables.com` |
| BIST hisse fiyatı | Yahoo Finance (`KOD.IS`) |
| BIST şirket listesi | `api.fintables.com/companies/` |
| Gram altın | Yahoo Finance (ons USD × USDTRY ÷ 31,1035) |
| BIST 100 | Yahoo Finance (`XU100.IS`) |

İnternet yoksa son başarılı değerler diskten okunur ve "bayat veri" uyarısı çıkar.

## Opsiyonel: ekstre senkronu

Midas API sunmadığı için senkron **hesap ekstresi** üzerinden yapılır. Ekstreni
Midas'tan e-postana gönderirsin; uygulama onu bulup portföyü günceller.

- **Ayarlar** → Gmail adresi + **uygulama şifresi** (2 adımlı doğrulama gerekli;
  normal şifre çalışmaz). Şifre yalnızca `data/secrets.json` içinde kalır.
- IMAP bağlantısı **salt okunurdur**: posta silinmez, taşınmaz, okundu
  işaretlenmez; yalnızca gönderici filtresine uyan iletilerin PDF eki alınır.
- Elle de yükleyebilirsin: **Dosya seç** → PDF.

Güvenlik kuralları için [ARCHITECTURE.md](ARCHITECTURE.md) → "Mutabakat güvenlik
kuralları" bölümüne bak: bayat bir ekstrenin elindeki varlığı silmesini engelleyen
korumalar burada anlatılıyor.

## Opsiyonel: portföy asistanı

Anthropic API anahtarı girersen portföyün hakkında soru sorabilirsin
("bugün neden düştüm?", "yoğunlaşma riskim ne?"). Soru sorduğunda **portföy
verisi dışarı gider** — arka planda hiçbir gönderim olmaz. Kart başlığındaki
rozet bunu hatırlatır.

## Teknik

Python 3.11+ · Flask · vanilla JS (derleme adımı yok) · pywebview · pystray ·
yfinance · PyMuPDF · anthropic

Mimari, veri sözleşmeleri ve geliştirirken dikkat edilmesi gereken tuzaklar için:
**[ARCHITECTURE.md](ARCHITECTURE.md)**
