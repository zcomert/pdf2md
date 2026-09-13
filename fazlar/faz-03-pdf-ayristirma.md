# Faz 03 — PDF Ayrıştırma ve `document.json`

**İlgili bölümler:** §11.1–§11.3, §16.1, §16.2, §28 (parse satırları), §32.2
**Önkoşul:** Faz 02
**Tahmini büyüklük:** Büyük (projenin kalite açısından en kritik fazlarından biri)

## Amaç

PyMuPDF ile her PDF'i yapısal bir ara temsile (`document.json`) dönüştürmek: sayfa sınıfları, doğru okuma sırasında bloklar, başlık hiyerarşisi ve bölümler. Bu fazda OCR ve görsel model yoktur; tablo/formül/şekil alanları şemada **yer alır** ama Faz 05'e kadar boş kalır.

## Modüller

`src/document_model.py`, `src/pdf_parser.py`, `src/page_classifier.py`, `src/layout_analyzer.py`, `src/cache_manager.py`, `src/batch_processor.py` (ayrıştırma aşaması)

## Görevler

### 1. Şema — `src/document_model.py`

- [x] `SourceMethod` (`text`, `ocr`, `vision`), `BlockType` (§16.1 türleri + `header_footer`), `PageClass`
- [x] `Line`: metin, bbox, baskın font/boyut, kalın/italik. **Span listesi saklanmaz**; satır düzeyi Faz 05 (formül satırları, numaralar) ve Faz 09 (kanıt konumu) için yeterlidir. Span ayrıntısı gereken fazlar PDF'i yeniden okur
- [x] `Block`: `id` (`p{sayfa}-b{sayfa içi sıra}`), `type`, `page`, `bbox`, `text` (satırlar `\n` ile), `lines`, `source_method`, baskın `font`/`size`/`bold`/`italic`, `heading_level`, `order` (belge geneli), `column` (0/1, tam genişlik `None`), `ref_id`
- [x] `Page`: `number`, boyutlar, `page_class`, `char_count`, `body_char_count`, `text_block_count`, `image_area_ratio`, `drawing_count`, `columns`, `gutter_x`, `reading_order_uncertain`, `vector_text_suspected`, `ocr_applied`, `parse_error`
- [x] `Section`: `id`, `title`, `level`, `number`, `heading_block_id`, `start_order`, `end_order`, `parent_id`
- [x] `Table`, `Equation`, `Figure` (§13–§15 alanları, Faz 05–07'de dolacak), `DocumentWarning` (`code: page n` gösterimi), `DocumentStats`
- [x] `DocumentModel`: `schema_version`, `parser_version`, `parse_config_hash`, `source`, `pdf_metadata`, `title`, `pages`, `blocks`, `sections`, `tables`, `equations`, `figures`, `warnings`, `stats`

**Not:** `source.relative_path` belgenin ilk ayrıştırıldığı yoldur. Aynı içerikli kopyalar önbelleği paylaştığı için belgenin güncel yolu her zaman state kaydından alınmalıdır.

### 2. Ayrıştırıcı — `src/pdf_parser.py`

- [x] `open_pdf(path)` — `fitz.open(path, filetype="pdf")` salt okunur; `save`/`set_metadata` yok (§32.2). `filetype="pdf"` uzantısı `.pdf` olan görsel/metin dosyalarının başka biçimde açılmasını engeller
- [x] Şifreli: boş parola denenir, olmazsa `DocumentError(parse)`; bozuk dosya veya sıfır sayfa → `DocumentError(parse)`. MuPDF mesajındaki mutlak dosya yolu hata metninden çıkarılır
- [x] `get_text("dict")` bayrakları: boşluk korunur, sayfa dışı metin atılır, **ligatürler açılır** (ﬁ → fi), görseller gömülmez (bellek; konumlar `get_image_info` ile). Sıfır genişlikli karakterler (U+200B vb.) temizlenir
- [x] Bold/italic: span `flags` bitleri + font adında `Bold/Black/Heavy/Semibold`, `Italic/Oblique`; satırın ≥%80'i
- [x] Tek sayfa hatası → `parse_error` + `page_parse_error` uyarısı, belge devam eder (§28); `is_repaired` → `pdf_repaired`
- [x] **`rawdict` yedeği yerine uyarı:** `rawdict` aynı karakter eşlemesini kullandığı için bozuk metni düzeltmez. Sayfada U+FFFD oranı > %5 ise `garbled_text` uyarısı verilir; bu sayfalar Faz 07'de görsel modele adaydır
- [x] `parse_pdf(path, relative_path, sha256, pdf_config) -> DocumentModel` saf fonksiyon (Faz 10 süreç havuzu)

### 3. Sayfa sınıflandırma — `src/page_classifier.py`

- [x] `image_area_ratio`: görsellerin sayfaya kırpılmış **birleşik** alanı (örtüşme iki kez sayılmaz)
- [x] §11.2 kuralları, eşikler config'ten
- [x] **Karakter sayısı olarak gövde metni** (`body_char_count`: üst/alt bilgi ve kenar damgaları hariç) kullanılır. Aksi halde her sayfadaki indirme damgası (Shilaskar: sayfa başına 138 karakter) sayfayı `text` gösterir
- [x] Kapsanmayan durum: az metin + düşük görsel oranı → `text` + `low_text_page`
- [x] **Vektör çizilmiş metin:** gövde < `min_text_chars` ve çizim sayısı ≥ 200 → `scanned` + `vector_text_suspected` (fazlar/README karar tablosu). Eşik gerçek setten: vektör metin sayfalarında 635–5972 çizim, normal grafik sayfalarında yüzlerce çizimle binlerce karakter. Çizim sayımı yalnızca 1000 karakterden az metni olan sayfalarda yapılır

### 4. Okuma sırası — `src/layout_analyzer.py`

- [x] **Sütun boşluğu tespiti** (`detect_gutter`): yalnızca sayfa genişliğinin %25–48'i genişliğindeki satırlar; aday x'i satırların en fazla %5'i kesebilir, her iki tarafta en az %20 ve en az 4 satır olmalı, **her iki taraf ortak bir sol kenara hizalı** olmalı
- [x] **Belge geneli sütun boşluğu** (`document_gutter`): sayfaların en az yarısında birbirine yakın boşluk bulunduysa, az metinli sayfalarda bu değer satırları kesmiyorsa kullanılır
- [x] Sütun boşluğunu kesen bloklar ayırıcıdır ve sayfayı bantlara böler; her bantta sol sütun sonra sağ sütun, sütun içinde yukarıdan aşağı
- [x] `reading_order_uncertain`: yalnızca **çok satırlı** ve içerik genişliğinin %60'ından dar bir metin bloğu boşluğu kestiğinde (ortalanmış tek satırlık başlıklar belirsizlik sayılmaz; gereksiz görsel model çağrısını önler)
- [x] Üst/alt bilgi blokları sayfanın başına/sonuna konur
- [x] **Girintili ilk satır birleştirme:** Elsevier PDF'lerinde paragrafın girintili ilk satırı ayrı blok gelir; aynı sütunda boşluksuz devam eden, sola dayalı, aynı biçimli blokla birleştirilir
- [x] **Stil değişiminde bölme:** MuPDF başlığı ve paragrafı tek blokta birleştirebildiği için boyut (±0,5 pt), kalınlık veya italiklik değişiminde blok bölünür

**Eşiklerin gerekçeleri (gerçek setten):** İlk sürümdeki "sayfa yarısından dar tüm satırlar" yaklaşımı tam genişlik tablo içeren sayfalarda (Imran s.8, tablo hücreleri boşluğu kesiyor) sütunları bulamıyor, tek sütunlu Berardi'de ise paragraf son satırları ve tablo hücreleri yüzünden sahte iki sütun buluyordu.

### 5. Üst/alt bilgi tespiti

- [x] Adaylar: üst/alt %8 şerit, sol/sağ %6 kenar şeridi veya tamamen dikey metin (kenar damgaları)
- [x] Rakamlar `#` ile normalize edilir; sayfaların **en az %40'ında** tekrarlanan metin `header_footer` (tek/çift sayfada dönüşümlü başlıklar ve tek sayılı sayfa sayıları %50'nin altında kalabildiği için)
- [x] 3 sayfadan kısa belgelerde uygulanmaz

### 6. Başlık ve blok türü tespiti

- [x] Gövde font boyutu: karakter ağırlıklı en yaygın boyut (0,5 pt yuvarlama)
- [x] Başlık puanı ≥ 3: boyut farkı (+1/+2, gövdeden 1 pt küçükse −2), kalın (+2), numara (+2; italik numaralı alt başlık +1), bilinen bölüm adı (+3, EN+TR), tamamen büyük harf (+1); noktayla biten (−2), 18 kelimeden uzun (−3), 2 satırdan fazla (−2); rakam oranı > %30 veya 3 satırdan fazla ise aday değil
- [x] Numara kalıbı: `1.`, `2.3.`, `II.`, `A.` + büyük harfle başlayan başlık. Harf/roma rakamı numarası yalnızca kalın, italik veya büyük fontla sayılır (yazar baş harfleriyle karışmasın)
- [x] Harf aralıklı başlıklar normalize edilir (`A B S T R A C T` → `ABSTRACT`)
- [x] **Yayıncı etiketleri** (`OPEN`, `RESEARCH Open Access`, `ORIGINAL MANUSCRIPT`, `Review paper`, `ARTICLE INFO`…) başlık değildir
- [x] **Ön bilgi temizliği:** Belge başlığı bulunduysa, ilk sayfada ilk numaralı veya bilinen bölüm başlığından önceki numarasız adaylar (yazar satırı, kurum) paragraftır
- [x] **Belge başlığı** (`_detect_title`), sırasıyla:
  1. PDF metadata `title` ile eşleşen (harf/rakam karşılaştırması) ardışık ilk sayfa blokları
  2. Değilse: ilk sayfanın üst yarısında, **dergi adı olmayan** (sayfanın üst şeridindeki künye satırının veya metadata `subject`'in başında geçmeyen), bilinen bölüm adı ve numaralı başlık olmayan en büyük fontlu ardışık bloklar; gövdeden en az 1,5 pt büyük ve sonraki sayfalardaki her metinden en az 0,5 pt büyük olmalı
  - Gerekçe: Elsevier'de dergi adı (13,95 pt) makale başlığından (13,45 pt) büyük
- [x] **Seviyeler:** belge başlığı 1, diğerleri +1 kaydırılır. Numaralı başlıkta seviye = numara derinliği (roma 1, harf 2). Numarasızda seviye-1 boyutu, bilinen bölüm adları ve tek düzeyli numaralı başlıkların **en yaygın** boyutudur; daha küçük boyutlar sırasıyla 2, 3… (numaralı alt başlıklarla aynı boyuttaysa onların seviyesi)
- [x] `caption`: `Table|Figure|Fig.|Şekil|Algorithm…` + numara + noktalama veya büyük harf. `Table 1 summarizes…` gibi metin içi atıflar başlık değildir
- [x] `list`: `•`, `-`, `(a)`, `(ii)`, `1)`, `1.` ile başlayan ve başlık olmayan bloklar
- [x] `footnote`: gövdeden ≥1 pt küçük ve sayfanın alt %20'sinde
- [x] `reference`: `References/Bibliography/Kaynaklar/Kaynakça` başlığından sonra, aynı veya üst seviyede yeni başlığa kadar
- [x] `figure`: görsel blokları (metni boş)
- [x] Bölüm ağacı (`build_sections`)

### 7. Önbellek — `src/cache_manager.py`

- [x] `doc_dir`, `document_json_path`, `renders_dir`, `model_raw_dir`, `errors_dir`, `extraction_path`; SHA-256 ve plan hash biçimi doğrulanır, yollar `ensure_under_output` ile kontrol edilir
- [x] `load_document(sha, parse_config_hash, force)` — dosya yoksa, JSON bozuksa, `schema_version`/`parser_version`/`parse_config_hash` farklıysa veya kaynak sha uyuşmuyorsa `None`
- [x] `parse_config_hash`: ayrıştırmayı etkileyen config alanları (`min_text_chars`, `mixed_image_ratio`, `scanned_image_ratio`); `render_dpi` gibi alanlar etkilemez
- [x] `save_document` — atomik, **girintisiz JSON** (satır koordinatları dosyanın çoğunu oluşturur; boyut ~%45 azalır: gerçek sette 6,2 MB → 3,6 MB)

### 8. CLI — ayrıştırma aşaması (`src/batch_processor.py`)

- [x] Keşiften sonra `pending`/`processing` belgeler (ve `--retry-failed` ile `failed`, `--force` ile hepsi) için: önbellek → yoksa `processing` + `attempts+1` → ayrıştır → önbelleğe yaz → `pending` + uyarılar
- [x] `DocumentError` → `failed` + `error_stage`; önbellek yazım hatası → `failed(write)`; beklenmeyen istisna traceback ile loglanır ve `failed(parse)` (tek PDF batch'i durdurmaz)
- [x] Belge başına log: sayfa sayısı, sayfa sınıfı dağılımı, süre, uyarı sayısı
- [x] Konsol özeti: `Ayrıştırma: N ayrıştırıldı, M önbellekten, K başarısız, L seçilmedi`; başarısız varsa çıkış kodu 1
- [x] Durum Faz 04'e kadar `pending` kalır (henüz `.md` yok)

## Bilinen Sınırlamalar (sonraki fazlara devredilenler)

- **Satır içi matematik parçaları:** LaTeX PDF'lerinde (Polle) üst/alt simgeler ayrı bloklar olarak gelir (`yi`, `j, yi`) ve bazıları `list` sanılabilir (`j) with …`). Formül bölgeleri Faz 05'te tespit edilip Faz 07'de görsel modelle işlenecek
- **Tablo hücreleri paragraf bloğu olarak kalır:** Faz 05 tablo bölgelerini `table` bloğuna dönüştürecek. Tablo başlığı hücreleri (ör. Polle'de kalın `Method`) şu an başlık sanılabiliyor
- **Tablo içeren iki sütunlu sayfalarda** çok satırlı hücreler `reading_order_uncertain` işaretleyebilir (Rahman s.7–9, Goodman s.14–18); Faz 05 tablo bölgeleri çıkarıldıktan sonra yeniden değerlendirilecek
- **Satır sonu tirelemesi** (`pre- trained`) blok metninde korunur; birleştirme Faz 04 Markdown üretiminde
- **Üç sütunlu düzenler** desteklenmez (akademik makalelerde nadir); tek sütun olarak sıralanır

## Testler

- [x] `test_page_classifier.py` — birleşik alan (örtüşme, kırpma), oran ≤ 1, §11.2 tablosu + `low_text_page` + `vector_text_suspected`, eşiklerin config'ten gelmesi
- [x] `test_layout_analyzer.py` — iki sütun boşluğu, tek sütunda boşluk yok, **paragraf son satırları ve tablo hücreleri sahte sütun oluşturmaz**, bantlı okuma sırası, belirsizlik kuralı, belge geneli boşluk, girintili ilk satır birleştirme, stil değişiminde bölme, üst/alt bilgi (rakam normalizasyonu, kısa belge), caption ve liste kalıpları, başlık puanı tablosu (numaralı, italik alt başlık, roma, harf aralıklı, yayıncı etiketi, cümle, yazar baş harfi, sayı satırı), belge başlığı + ön bilgi + seviyeler + kaynakça, metadata başlığı ve dergi adı ayıklama, numarasız seviyeler, bölüm başlığının belge başlığı olamaması
- [x] `test_pdf_parser.py` — sentetik: başlık hiyerarşisi ve liste `EXPECTED` ile birebir, bölüm ağacı, iki sütun okuma sırası işaretleri, üst/alt bilgi, taranmış sayfa, caption/figure, şifreli/bozuk/PDF olmayan → `DocumentError(parse)` ve mesajda yol yok, sahip parolalı PDF, **PDF değişmez**, JSON round-trip, blok kimlik/sıra, tek sayfa hatası uyarı olur; gerçek (dosya yoksa atlanır): Elsevier başlığı ve 4 seviyeli alt başlıklar, dergi adı başlık değil, sütunlar arası bölüm sırası (Imran 4.2 < 4.3), tek sütunlu makale ve seviyeler (Berardi), IEEE roma rakamlı bölümler, vektör metin sayfaları (Shilaskar)
- [x] `test_cache_manager.py` — kayıt/yükleme ve girintisiz JSON, `force`, sürüm/ayar değişiminde geçersizlik, bozuk dosya, geçersiz sha/plan hash (path traversal), dizin düzeni
- [x] `test_cli_parse.py` — uçtan uca: `document.json` şemadan geçer (§38 kriter 23), açılamayanlar `failed(parse)`, aynı içerik tek önbellek; `--retry-failed`, `--force`; ayrıştırma ayarı değişince yeniden ayrıştırma; içeriği değişen PDF yeniden ayrıştırılır
- [x] Faz 02 CLI testleri, açılamayan fixture'lar nedeniyle çıkış kodu 1 bekleyecek şekilde güncellendi

## Tamamlanma Kriterleri

- [x] Tüm sentetik ve gerçek metin tabanlı PDF'ler için `document.json` üretilir ve şemadan geçer (§38 kriter 23)
- [x] Şifreli/bozuk PDF'ler `failed` + `error_stage: parse`, batch devam eder (§38 kriter 11)
- [x] Aynı içerikli iki PDF tek `_cache/<sha>` klasörünü paylaşır
- [x] Gerçek makalelerde elle inceleme: 9 makalenin 8'inde belge başlığı doğru (Shilaskar'da okunabilir metin yok), ana bölüm başlıkları doğru sıra ve seviyede, Elsevier alt başlıkları 4 seviyeye kadar, sütun sırası doğru
- [x] `pytest` yeşil (231 geçti, 1 atlandı — Tesseract kurulu değil)
