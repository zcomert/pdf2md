# Faz 06 — Tesseract OCR ve Metin Katmanı Birleştirme

**İlgili bölümler:** §11.2 (son satır), §11.4, §26 (Tesseract satırı), §34.2
**Önkoşul:** Faz 05; sistemde Tesseract ve `eng` (tercihen `tur`) dil paketi kurulu
**Tahmini büyüklük:** Orta

## Amaç

Taranmış sayfalardan yerel OCR ile metin elde etmek, mevcut metin katmanıyla tekrarsız birleştirmek ve sonucu Faz 03'teki düzen analizine (okuma sırası, başlık tespiti) sokmak.

## Modüller

`src/ocr.py`, `src/preflight.py` (güncelleme), `src/pdf_parser.py` (entegrasyon)

## Görevler

### 1. Tesseract keşfi — `src/ocr.py`

- [ ] `find_tesseract(config) -> TesseractInfo | None`
  - `ocr.tesseract_path` verilmişse o; değilse `shutil.which("tesseract")`
  - Windows'ta PATH'te yoksa bilinen kurulum konumu (`C:\Program Files\Tesseract-OCR\`) denenir ve bulunursa kullanıcıya config'e yazması önerilir
- [ ] `tessdata` dizini: `TESSDATA_PREFIX` ortam değişkeni veya çalıştırılabilir dosyanın yanındaki `tessdata`
- [ ] `tesseract --list-langs` ile kurulu diller; `ocr.languages` içindeki eksik diller listelenir
- [ ] Sürüm bilgisi loga

### 2. Preflight güncellemesi

- [ ] `ocr.enabled: true` ve Tesseract/dil paketi yok → **uyarı** (§26), hint: kurulum bağlantısı/komutu + "taranmış sayfalar görsel modele yönlendirilecek"
- [ ] Çalışma bağlamına `ocr_available: bool` yazılır

### 3. OCR uygulama

- [ ] Yalnızca `scanned` sayfalar (FULL modunda da; §12.3 görsel çağrılar ayrı konu)
- [ ] `page.get_textpage_ocr(language="eng+tur", dpi=config.pdf.render_dpi, full=True, tessdata=...)` → `page.get_text("dict", textpage=tp)`
- [ ] Hata/zaman aşımı → `DocumentError` **değil**; sayfa uyarısı `ocr_failed: page n`, sayfa görsel model kuyruğuna aday olarak işaretlenir (`vision_trigger = "scanned_ocr_failed"`)
- [ ] OCR yok → `ocr_unavailable: page n` uyarısı, `vision_trigger = "scanned_no_ocr"`
- [ ] İstatistik: `stats.ocr_pages += 1`

### 4. Metin katmanı + OCR birleştirme

§11.4 — mevcut metin katmanı **atılmaz**:

- [ ] OCR span'leri ile metin katmanı span'leri bbox örtüşmesine (IoU veya kesişim/OCR alanı oranı ≥ 0.5) göre eşleştirilir
- [ ] Örtüşen bölgede metin katmanı tercih edilir, OCR span'i atılır
- [ ] Örtüşmeyen OCR span'leri eklenir, `source_method: "ocr"`
- [ ] Birleşik span listesi Faz 03'teki blok oluşturma → okuma sırası → başlık tespiti hattına aynı şekilde girer (kod tekrarı olmamalı: `build_blocks(spans)` ortak fonksiyon)
- [ ] Sayfa `ocr_applied = True`

### 5. OCR dil seçimi

- [ ] Varsayılan `["eng"]` (§11.4)
- [ ] Birden fazla dil `+` ile birleştirilir
- [ ] Config'te `tur` istenmiş ama kurulu değilse yalnızca kurulu dillerle devam + uyarı

### 6. `[unreadable_page]`

- [ ] OCR yok **ve** görsel model yok (Faz 07'de kontrol edilecek) → sayfa bloğu yerine `[unreadable_page]` yazılır, belge `completed_with_warnings` (§11.4). Bu fazda görsel model bilgisi olmadığından "görsel model yok" varsayımıyla davranılır; Faz 07'de yönlendirme eklenir.

### 7. Önbellek

- [ ] OCR sonucu `document.json` içinde saklandığı için prompt değişiminde yeniden yapılmaz (§30)
- [ ] OCR dilleri ve Tesseract sürümü `document.json`'ın geçerlilik anahtarına dahil edilir: OCR dilleri değişince yalnızca taranmış sayfa içeren belgelerin önbelleği geçersiz olur (öneri: `DocumentModel.ocr_signature` alanı; taranmış sayfa yoksa karşılaştırılmaz)

## Testler

- `@requires_tesseract` `synthetic_scanned.pdf`: OCR metni bilinen metnin ≥ %90'ını içerir (kelime düzeyinde basit karşılaştırma)
- Birleştirme birim testi: sahte span listeleriyle örtüşen bölgede tekrar yok, metin katmanı değeri korunmuş
- Tesseract yokken (`tesseract_path` hatalı ayarlanarak): uyarı, `[unreadable_page]`, `completed_with_warnings`, çıkış kodu 0
- Gerçek taranmış PDF'ler için Markdown elle incelenir

## Tamamlanma Kriterleri

- [ ] Taranmış PDF'lerden OCR ile metin elde edilir ve Markdown'da başlık/paragraf yapısıyla görünür (§38 kriter 10'un OCR yarısı)
- [ ] OCR uygulanan sayfalar `document.json`'da `source_method: "ocr"` ile işaretli
- [ ] Tesseract eksikliği batch'i durdurmaz
- [ ] `pytest` yeşil
