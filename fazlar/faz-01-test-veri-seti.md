# Faz 01 — Test Veri Seti ve Fixture Altyapısı

**İlgili bölümler:** §38.1
**Önkoşul:** Faz 00
**Tahmini büyüklük:** Küçük–Orta (referans veri hazırlığı elle yapılır, zaman alır)

## Amaç

Tüm sonraki fazların birim ve entegrasyon testlerinde kullanılacak PDF setini erkenden hazırlamak. Geç hazırlanan test verisi, ayrıştırıcının "sadece elimdeki PDF'te çalışır" hale gelmesine yol açar.

## Görevler

### 1. Sentetik PDF üreticisi — `tests/fixtures/generate_fixtures.py`

PyMuPDF ile programatik olarak üretilen, içeriği tam bilinen PDF'ler. Avantajı: beklenen çıktı kesin olarak bilinir.

- [ ] `synthetic_single_column.pdf` — başlık, `Abstract`, numaralı bölümler (`1. Introduction`, `2.1 Dataset`), paragraflar, madde listesi
- [ ] `synthetic_two_column.pdf` — iki sütunlu gövde, tam genişlik başlık ve tam genişlik tablo
- [ ] `synthetic_table_equation.pdf` — çizgili tablo (hücre değerleri bilinen), `(1)`, `(2)` numaralı formül satırları, `Figure 1` başlıklı gömülü PNG
- [ ] `synthetic_header_footer.pdf` — her sayfada tekrarlanan dergi adı ve sayfa numarası
- [ ] `synthetic_scanned.pdf` — metin içeren sayfanın 200 DPI render'ı, metin katmanı olmadan görsel olarak eklenmiş
- [ ] `synthetic_encrypted.pdf` — kullanıcı parolalı (boş parola ile açılmayan)
- [ ] `synthetic_encrypted_empty_pw.pdf` — yalnızca sahip parolalı (boş parola ile açılabilen) — §28
- [ ] `corrupt.pdf` — geçerli PDF'in ilk ~2 KB'ı + rastgele bayt
- [ ] `not_a_pdf.PDF` — büyük harf uzantılı, aslında metin dosyası (uzantı eşleşmesi + bozuk dosya testi)
- [ ] `subdir/synthetic_single_column.pdf` — kökteki ile **aynı ad, farklı içerik** (§6.2 çakışma)
- [ ] `duplicate_copy.pdf` — kökteki bir PDF ile **aynı içerik, farklı ad** (§8.2 önbellek paylaşımı)

Üretici deterministik olmalı (sabit metin, sabit tarih metadata'sı), böylece hash'ler testlerde sabit kalır. Üretilen dosyalar git'e eklenebilir veya `conftest.py`'de oturum başında üretilebilir. Öneri: **git'e ekle**, üreticiyi de sakla.

### 2. Gerçek makaleler — `tests/fixtures/real/`

§38.1'in istediği gerçekçi set. Lisansı paylaşıma uygun (ör. arXiv CC-BY) makaleler seçilir.

- [ ] 4 metin tabanlı tek sütunlu makale
- [ ] 3 çift sütunlu makale (en az biri tablo ve formül yoğun)
- [ ] 2 taranmış PDF (gerçek tarama veya yüksek kaliteli sentetik)
- [ ] Büyük dosyalar git'e alınmayacaksa `tests/fixtures/real/SOURCES.md` içinde indirme bağlantıları ve SHA-256 değerleri

### 3. Referans veri — `tests/fixtures/reference/<ad>.yaml`

3 gerçek makale için elle hazırlanır (§38.1):

```yaml
source: real/paper_a.pdf
sha256: "..."
bibliographic:
  title: "..."
  authors: ["...", "..."]
  year: 2023
  venue: "..."
  doi: "10.xxxx/..."
tables:            # en az 2
  - number: "3"
    page: 7
    header: ["Model", "Accuracy", "F1"]
    rows: [["Bi-LSTM", "0.99", "0.99"]]
equations:         # en az 3
  - number: "1"
    page: 4
    latex: "z = \\frac{x-\\mu}{s}"
results:           # en az 5
  - model: "Bi-LSTM"
    metric: "accuracy"
    value: 0.99
    page: 15
    table: "Table 9"
```

Bu şemanın Pydantic modeli `tests/reference_schema.py` içinde tanımlanır. Faz 14'teki doğruluk ölçümü bu dosyaları kullanır.

### 4. `tests/conftest.py`

- [ ] `fixtures_dir`, `synthetic_pdf(name)` fixture'ları
- [ ] `tmp_input_copy` — fixture'ları geçici bir giriş klasörüne kopyalar (giriş klasörünün değişmediği testleri için)
- [ ] `tmp_output` — geçici çıktı klasörü
- [ ] `input_snapshot(path) -> dict[relpath, sha256]` yardımcısı (§38 kriter 17 için)
- [ ] `requires_tesseract`, `requires_ollama` pytest işaretleri; ortamda yoksa `skip`

## Testler

- Üretici iki kez çalıştırıldığında aynı SHA-256 değerleri üretilir
- Tüm referans YAML'ları şemaya uyar

## Tamamlanma Kriterleri

- [ ] Sentetik set üretilmiş ve beklenen özellikleri doğrulanmış (şifreli olan açılmıyor, bozuk olan hata veriyor, taranmışın metin katmanı boş)
- [ ] Gerçek makaleler ve 3 referans YAML hazır
- [ ] `requires_tesseract` / `requires_ollama` işaretleri çalışıyor
