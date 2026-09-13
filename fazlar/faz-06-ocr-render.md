# Faz 06 — Tesseract OCR ve Metin Katmanı Birleştirme

**İlgili bölümler:** §11.2 (son satır), §11.4, §26 (Tesseract satırı), §34.2
**Önkoşul:** Faz 05; sistemde Tesseract ve `eng` (tercihen `tur`) dil paketi kurulu
**Tahmini büyüklük:** Orta

## Amaç

Taranmış sayfalardan yerel OCR ile metin elde etmek, mevcut metin katmanıyla tekrarsız birleştirmek ve sonucu Faz 03'teki düzen analizine (okuma sırası, başlık tespiti) sokmak.

## Ortam

- Tesseract 5.4.0 (UB Mannheim, `winget install UB-Mannheim.TesseractOCR`) → `C:\Program Files\Tesseract-OCR`, **PATH'e eklenmez**
- Kurulu diller: `eng`, `osd`. **`tur` yok** — Türkçe taranmış belgeler için `tur.traineddata` dosyası `tessdata` klasörüne eklenmeli (yönetici yetkisi gerekir) ve config'te `ocr.languages: ["eng", "tur"]` verilmeli
- PyMuPDF OCR'ı MuPDF'e gömülü Tesseract motoruyla yapar; yalnızca `tessdata` dil dosyaları gerekir. Çalıştırılabilir dosya sürüm bilgisi ve kurulum konumunu bulmak için kullanılır

## Modüller

`src/ocr.py` (yeni); `src/pdf_parser.py`, `src/preflight.py`, `src/cache_manager.py`, `src/batch_processor.py`, `src/cli.py`, `src/layout_analyzer.py`, `src/document_model.py` güncellendi (`DOCUMENT_SCHEMA_VERSION` 1.2, `PARSER_VERSION` 0.3.0)

## Görevler

### 1. Tesseract keşfi — `src/ocr.py`

- [x] `find_tesseract(tesseract_path)` — öncelik: config `ocr.tesseract_path` (çalıştırılabilir dosya, kurulum klasörü veya `tessdata` klasörü) > PATH > **bilinen Windows konumları** (`Program Files`, `Program Files (x86)`, `LOCALAPPDATA\Programs`) > `TESSDATA_PREFIX`
- [x] Diller `tessdata/*.traineddata` dosyalarından (`osd` dil sayılmaz); sürüm `tesseract --version`
- [x] `select_languages`, `resolve_ocr_settings(ocr_config, dpi) -> (OcrSettings | None, mesajlar)`: kurulu olmayan diller atlanır; hiç kullanılabilir dil yoksa OCR yok
- [x] `OcrSettings.signature` = `tesseract:<sürüm>:<diller>:<dpi>`

### 2. Başlangıç kontrolü — `check_ocr`

- [x] OCR etkin ve Tesseract yok → **uyarı** (çıkış kodu değil), öneri: Windows/Linux/macOS kurulum komutları, Türkçe dil paketi, `ocr.tesseract_path`
- [x] Eksik dil → uyarı, kurulu dillerle devam
- [x] Bulunursa bilgi logu: sürüm, `tessdata` konumu, kullanılan diller
- [x] Seçilen `OcrSettings` batch işlemcisi üzerinden `parse_pdf`'e aktarılır (`parse_pdf` saf kalır, keşif yapmaz)

### 3. OCR uygulama — `src/pdf_parser.py`

- [x] Yalnızca `scanned` sayfalar (vektör çizilmiş metin sayfaları dahil); sıra: ham çıkarım → üst/alt bilgi → sayfa sınıfı → **OCR** → üst/alt bilgi yeniden (OCR bloklarındaki tekrarlar için) → görsel tespit (taranmış sayfalarda yok) → okuma sırası → blok türleri
- [x] `page.get_textpage_ocr(language, dpi=pdf.render_dpi, full=True, tessdata)`; kelimeler (`words`) ve satır font boyutları (`dict`) alınır
- [x] Tesseract yok/OCR kapalı → `ocr_unavailable: page n`; OCR hatası → `ocr_failed: page n` (belge devam eder); OCR metin üretmedi → `ocr_empty: page n`
- [x] `Page.ocr_applied`, `DocumentStats.ocr_pages`, OCR bloklarında `source_method: "ocr"`
- [x] OCR başarılıysa `vector_text_suspected` uyarı olmaz (bayrak sayfada kalır); içerik kaybı yoktur
- [x] OCR uygulanmamış taranmış sayfa hâlâ `[unreadable_page]` + uyarı (Faz 04); görsel model yönlendirmesi Faz 07

### 4. OCR düzeni — kelime kutularından satır ve bloklar

**Sorun (gerçek set, Shilaskar):** MuPDF, OCR kelimelerini aynı taban çizgisindeyse sütun boşluğunu gözetmeden aynı bloğa, iki yana yaslı metindeki kelimeleri ayrı bloklara koyuyordu. İlk sürümde sağ ve sol sütun metni aynı paragrafta birleşiyor, kelimeler tek tek paragraf oluyordu. Sütun boşluğu ~5 pt, kelime aralıkları 3–6 pt olduğu için boşluk genişliğiyle ayrım yapılamaz.

- [x] `whitespace_gutter(words)`: kelimelerin dikey boşluk profili. Aday x'i **satırların en fazla %20'sinde** bir kelime kesebilir (sütunları kesen başlık/yazar/özet satırları) ve her iki tarafta kelimelerin ≥%25'i bulunmalı. İki yana yaslı metnin kelime aralıkları her satırda farklı x'e düşer; tek sütunda satırların çoğu her x'te kesilir. Eşik kelime değil **satır** sayısına göre (kelime sayısına göreyken tesadüfi hizalanmalar sahte sütun üretebiliyordu; ilk denemede %5 ise Shilaskar s.1'de başlık/yazar satırları yüzünden boşluğu kaçırıyordu)
- [x] `build_ocr_blocks`: metin katmanıyla örtüşen kelimeler atılır → kelimeler sütun ve taban çizgisine (±3 pt) göre satırlara toplanır → satırlar dikey boşluk (>0,7 satır yüksekliği), girinti (>6 pt) ve font boyutu farkına (>1 pt) göre bloklara ayrılır → harf/rakam içermeyen satırlar (vektör çizim gürültüsü) atılır
- [x] Satır font boyutu: kelime satırının merkezini içeren MuPDF OCR satırından; yoksa yükseklikten tahmin
- [x] Girintiyle bölünen paragraf ilk satırları Faz 03'teki `merge_indented_first_lines` ile birleşir (kaynak bilgisi korunur; OCR ve metin katmanı blokları birleşmez)

### 5. Metin katmanı + OCR birleştirme (§11.4)

- [x] Mevcut metin katmanı atılmaz. OCR **kelimesi** alanının ≥%50'si bir metin katmanı satırıyla örtüşüyorsa atılır. Eleme kelime düzeyindedir: kenardaki dikey IEEE damgası (metin katmanında mevcut) OCR'da tek tek karakterler olarak sütun satırlarıyla aynı taban çizgisine düşüyor ve satır düzeyinde elenemiyordu ("6 majority of road…")
- [x] `merge_ocr_blocks`: ikinci güvenlik kontrolü (satır düzeyi) ve blokların eklenmesi

### 6. Önbellek

- [x] `DocumentModel.ocr_signature`: taranmış sayfa varsa `OcrSettings.signature` veya `unavailable`, yoksa `None`
- [x] `CacheManager.load_document(..., ocr_signature)`: taranmış sayfalı belgede imza farklıysa önbellek geçersiz → **Tesseract kurulunca, dil veya DPI değişince taranmış sayfalı belgeler kendiliğinden yeniden OCR'lanır**; taranmış sayfası olmayan belgeler etkilenmez

### 7. OCR DPI

- [x] `pdf.render_dpi` (varsayılan 250). Shilaskar s.1'de 250/300/400 DPI karşılaştırıldı: şüpheli birleşik kelime 10/8/8, süre 2,1/2,3/2,6 sn — anlamlı fark yok, ayrı ayar eklenmedi

## Gerçek Setteki Sonuç

- **Shilaskar** (6 sayfa vektör çizilmiş metin): önceden tüm sayfalar `[unreadable_page]`; şimdi makale metni, 2 sütunlu okuma sırası, bölüm başlıkları (`I. INTRODUCTION` … `VII. REFERENCES`), şekil başlıkları geri kazanıldı; belge `completed`, OCR ~12 sn
- **Sentetik taranmış PDF**: metnin tamamı, başlık tespiti dahil

## Bilinen Sınırlamalar

- OCR hataları: birleşik kelimeler (`ofTechnology`), yanlış harfler (`myuries`), şema/grafik içinden okunmuş anlamsız satırlar (başlık sanılabilir: `= —S«&<LCOSOCSOOSSSS`). Görsel model (Faz 07) bu sayfaları iyileştirebilir
- Sütunları kesen yazar satırlarında kelimeler satırlara karışabilir
- OCR font bilgisi yok: kalın/italik ve matematik fontu tespiti OCR sayfalarında çalışmaz; başlıklar yalnızca boyut, numara ve bilinen bölüm adıyla bulunur
- Taranmış sayfalarda tablo/formül/şekil tespiti yapılmaz (Faz 07 görsel model)
- Türkçe dil paketi bu makinede kurulu değil
- Gerçek taranmış (raster) makale test setinde hâlâ yok (Faz 01 eksik: 2 taranmış PDF)

## Testler

- [x] `test_ocr.py` — keşif (config: kurulum klasörü/çalıştırılabilir dosya/tessdata; dilsiz kurulum; bilinen konum; `TESSDATA_PREFIX`), dil seçimi, ayar çözümleme ve imza, `check_ocr` (tamam, eksik dil, bulunamadı + kurulum önerisi, kapalı); OCR düzeni: dar sütun boşluğu, tek sütunda sütun yok (rastgele kelime aralıklı gerçekçi veri), iki sütunun ayrı bloklara ayrılması, metin katmanı kelimelerinin ve gürültünün atılması + font boyutu, boşluk/girinti/boyut ile blok bölme, birleştirmede metin katmanı önceliği; **Tesseract ile:** sentetik taranmış PDF'te kelimelerin ≥%90'ı, başlık ve `source_method: ocr`; Shilaskar'da 6 sayfa OCR, okunamayan sayfa yok, uyarı yok, metin ve başlıklar, 2 sütun, damga karakterlerinin sütun satırlarına karışmaması
- [x] `test_cli_batch.py` — **Tesseract ile:** taranmış PDF `completed`, `[unreadable_page]` yok, `ocr_signature`; OCR açılınca yalnızca taranmış sayfalı belgenin önbelleğinin geçersiz olması; **Tesseract bulunamayınca** çıkış kodu değil uyarı, `ocr_unavailable`
- [x] Ortama bağlı testler (`test_full_conversion_end_to_end`, iptal, yarıda kalan kayıt) `no_ocr_config` fixture'ıyla OCR kapatılarak deterministik hale getirildi; OCR kapalıyken `ocr_unavailable` + `unreadable_page` doğrulanıyor

## Tamamlanma Kriterleri

- [x] Taranmış PDF'lerden OCR ile metin elde edilir ve Markdown'da başlık/paragraf yapısıyla görünür (§38 kriter 10'un OCR yarısı)
- [x] OCR uygulanan sayfalar `document.json` içinde `source_method: "ocr"` ile işaretli
- [x] Tesseract eksikliği batch'i durdurmaz (uyarı + `ocr_unavailable`)
- [x] `pytest` yeşil (354 geçti, atlanan yok)
