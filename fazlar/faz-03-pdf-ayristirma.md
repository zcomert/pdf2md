# Faz 03 — PDF Ayrıştırma ve `document.json`

**İlgili bölümler:** §11.1–§11.3, §16.1, §16.2, §28 (parse satırları), §32.2
**Önkoşul:** Faz 02
**Tahmini büyüklük:** Büyük (projenin kalite açısından en kritik fazlarından biri)

## Amaç

PyMuPDF ile her PDF'i yapısal bir ara temsile (`document.json`) dönüştürmek: sayfa sınıfları, doğru okuma sırasında bloklar, başlık hiyerarşisi ve bölümler. Bu fazda OCR ve görsel model yoktur; tablo/formül/şekil alanları şemada **yer alır** ama Faz 05'e kadar boş kalır.

## Modüller

`src/document_model.py`, `src/pdf_parser.py`, `src/page_classifier.py`, `src/layout_analyzer.py`, `src/cache_manager.py`

## Görevler

### 1. Şema — `src/document_model.py`

Sonraki fazların ihtiyaçları baştan düşünülerek tanımlanır (şema sürümü değişince tüm önbellek geçersiz olur, bu yüzden sık değiştirmemek önemli).

- [ ] `SourceMethod` enum: `text`, `ocr`, `vision`
- [ ] `BlockType` enum: `heading`, `paragraph`, `list`, `table`, `equation`, `figure`, `algorithm`, `caption`, `footnote`, `reference`, `header_footer` (kaldırılan tekrarlar izlenebilsin diye)
- [ ] `BBox = tuple[float, float, float, float]`
- [ ] `Span` (text, font, size, bold, italic, bbox) — `document.json` boyutunu şişirmemek için yalnızca gerektiğinde saklanabilir; öneri: blok düzeyinde baskın font/size/bold tut, span listesini sakla ama `exclude_spans` seçeneği bırak
- [ ] `Block`: `id` (`p{sayfa}-b{sıra}` biçimi, §18 örneğiyle uyumlu), `type`, `page`, `bbox`, `text`, `source_method`, `heading_level: int | None`, `order: int`, `column: int | None`, `ref_id: str | None` (table/equation/figure kaydına bağlantı)
- [ ] `Page`: `number` (1 tabanlı), `width`, `height`, `page_class` (`text|mixed|scanned`), `char_count`, `image_area_ratio`, `reading_order_uncertain`, `ocr_applied`, `parse_error: str | None`
- [ ] `Section`: `id`, `title`, `level`, `number` (`2.3`), `start_block`, `end_block`, `parent_id`
- [ ] `Table`, `Equation`, `Figure` — alanları §13, §14, §15'e göre şimdiden tanımla (içleri Faz 05–07'de dolacak):
  - `Table`: id, number, caption, page, bbox, `markdown`, `html | None`, `cells: list[list[str]]`, `has_merged_cells`, `source_method`, `consistent`
  - `Equation`: §14 JSON örneğindeki alanlar
  - `Figure`: id, number, caption, page, bbox, `cache_path`, `referenced_by: list[block_id]`, `source_method`
- [ ] `Warning`: `code`, `page | None`, `message` — string gösterimi `code: detay` (state'teki `"ocr_unavailable: page 4"` biçimi)
- [ ] `DocumentModel`: `schema_version`, `parser_version`, `source` (relative_path, sha256, page_count), `pdf_metadata`, `pages`, `blocks`, `sections`, `tables`, `equations`, `figures`, `warnings`, `stats` (vision_calls, ocr_pages vb. — CSV için)

### 2. Ayrıştırıcı — `src/pdf_parser.py`

- [ ] `open_pdf(path)` — **salt okunur**: `fitz.open(path)`; hiçbir `save`/`set_metadata` çağrısı yok (§32.2)
- [ ] Şifreli: `doc.needs_pass` ise `doc.authenticate("")` dene; başarısızsa `DocumentError(parse, "encrypted")` (§28)
- [ ] Bozuk: açılış istisnası → `DocumentError(parse, ...)`
- [ ] Sayfa başına `page.get_text("dict", flags=...)` — ligatür ve boşluk koruma bayraklarını belgele; metin bozuksa `"rawdict"` yedeği (§11.1)
- [ ] Tek sayfa hatası: sayfa `parse_error` ile işaretlenir, uyarı eklenir, devam edilir (§28)
- [ ] Bold/italic: span `flags` bitleri + font adında `Bold`/`Italic` kontrolü
- [ ] Görsel bloklar: `type == 1` bloklar ve `page.get_image_info()` alanları
- [ ] PDF metadata: `doc.metadata`

### 3. Sayfa sınıflandırma — `src/page_classifier.py`

- [ ] `char_count` (boşluk hariç), `text_block_count`, `image_area_ratio` (örtüşen görseller birleşik alan olarak — üst üste görseller oranı 1'in üstüne çıkarmamalı; `min(1, ...)` + basit dikdörtgen birleşimi)
- [ ] §11.2 kuralları, eşikler config'ten
- [ ] **Kapsanmayan durum:** `char_count < min_text_chars` ve `image_area_ratio < scanned_image_ratio` → `text` + `low_text_page` uyarısı (README'deki karar tablosuna bak)

### 4. Okuma sırası — `src/layout_analyzer.py`

§11.3 algoritması:

- [ ] Sayfa genişliğinin ~%60'ından geniş bloklar "tam genişlik" sayılır (eşik sabit olarak tanımlanır)
- [ ] Sayfa, tam genişlik bloklarla dikey **bantlara** bölünür
- [ ] Her bant içinde bloklar x-merkezlerine göre sütunlara kümelenir (x0 değerleri üzerinde boşluk tabanlı bölme yeterli)
- [ ] Sütunlar soldan sağa, sütun içi üstten alta
- [ ] Bir blok birden fazla sütun aralığını kesiyor ve tam genişlik değilse → `reading_order_uncertain = True`
- [ ] `order` ve `column` alanları atanır

### 5. Üst/alt bilgi tespiti

- [ ] Sayfanın üst/alt ~%8'lik şeridindeki bloklar aday
- [ ] Rakamlar normalize edilerek (`\d+` → `#`) sayfaların ≥ %50'sinde tekrar eden metinler `header_footer` olarak işaretlenir (§16.3)
- [ ] 3 sayfadan kısa belgelerde uygulanmaz

### 6. Başlık tespiti

§16.2 — puanlama tabanlı:

- [ ] Gövde font boyutu = karakter ağırlıklı en yaygın boyut
- [ ] Sinyaller: boyut > gövde, bold, kısa satır (≤ ~15 kelime, noktayla bitmiyor), numara kalıbı (`^\d+(\.\d+)*\.?\s`, `^[IVX]+\.\s`), bilinen bölüm adları (EN + TR: `Abstract/Özet`, `Introduction/Giriş`, `Method(s)/Yöntem`, `Results/Bulgular/Sonuçlar`, `Discussion/Tartışma`, `Conclusion(s)/Sonuç`, `References/Kaynaklar`, `Acknowledg(e)ments/Teşekkür`)
- [ ] Seviye: önce numara derinliği (`2.3` → 2); numara yoksa font boyutu kümelerine göre
- [ ] Belgedeki ilk sayfanın en büyük fontlu bloğu → başlık (`title`, seviye 1); diğer başlıklar buna göre kaydırılır
- [ ] `References` sonrası paragraflar `reference` tipine alınır
- [ ] Liste tespiti: `•`, `-`, `–`, `(a)`, `1)` ile başlayan ardışık satırlar
- [ ] Bölüm ağacı (`sections[]`) oluşturulur

### 7. Önbellek — `src/cache_manager.py`

- [ ] `CacheManager(output_dir)`: `doc_dir(sha)`, `document_json_path(sha)`, `renders_dir`, `model_raw_dir`, `errors_dir`, `extraction_path(sha, plan_hash)`
- [ ] `load_document(sha) -> DocumentModel | None` — dosya yoksa, JSON bozuksa, `schema_version` veya `parser_version` farklıysa `None` (geçersiz sayılır)
- [ ] `save_document(model)` — atomik
- [ ] `force=True` iken okuma yapılmaz (§9.4)
- [ ] Tüm yollar `ensure_under_output` ile doğrulanır

### 8. Geçici CLI komutu

- [ ] Her `pending` belge için: önbellek var mı → yoksa ayrıştır → `document.json` yaz. Hatalı belgeler state'te `failed` + `error_stage`. Henüz `.md` yok.

## İleriye Dönük Tasarım

- Ayrıştırma saf fonksiyon olarak yazılmalı: `parse_pdf(path, config) -> DocumentModel`. Faz 10'da `ProcessPoolExecutor` ile paralel çalıştırılacak; bu yüzden global durum veya açık dosya nesnesi dönmemeli.
- `parse_pdf` görsel model çağırmaz. Görsel/OCR adımları Faz 06–07'de ayrı "zenginleştirme" aşamaları olarak `DocumentModel` üzerinde çalışacak.

## Testler

- `synthetic_single_column.pdf`: başlık hiyerarşisi `tests/fixtures/generate_fixtures.py` → `EXPECTED` ile aynı (makale başlığı seviye 1, `1. Introduction` seviye 2, `2.1 Dataset` seviye 3), liste bloğu tespit edilir
- `synthetic_two_column.pdf`: blok sırası sol sütun → sağ sütun; tam genişlik tablo doğru dikey konumda
- `synthetic_header_footer.pdf`: tekrarlanan metinler `header_footer`
- `synthetic_scanned.pdf`: sayfa sınıfı `scanned`
- `synthetic_encrypted.pdf` → `DocumentError(parse)`; `synthetic_encrypted_empty_pw.pdf` açılır
- `corrupt.pdf` → `DocumentError(parse)`
- `document.json` Pydantic ile yeniden yüklenir (round-trip)
- `parser_version` değişince önbellek geçersiz sayılır
- Gerçek çift sütunlu makalelerde okuma sırası elle gözden geçirilir (snapshot testi olarak blok metinlerinin ilk 40 karakterlik sırası kaydedilebilir)

## Tamamlanma Kriterleri

- [ ] Tüm sentetik ve gerçek metin tabanlı PDF'ler için `document.json` üretilir ve şemadan geçer (§38 kriter 23)
- [ ] Şifreli/bozuk PDF'ler `failed` + `error_stage: parse`, batch devam eder (§38 kriter 11)
- [ ] Aynı içerikli iki PDF tek `_cache/<sha>` klasörünü paylaşır
- [ ] `pytest` yeşil
