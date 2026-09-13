# Faz 05 — Görsel Aday Tespiti, Metin Tabanlı Tablo ve Şekil Çıkarımı

**İlgili bölümler:** §12.2, §12.4 (kırpma kısmı), §13 (1, 2, 4, 5. adımlar), §14 (metin tabanlı), §15, §6.2 (`assets/`)
**Önkoşul:** Faz 04
**Tahmini büyüklük:** Büyük

## Amaç

Model kullanmadan elde edilebilecek her şeyi çıkarmak: tablo/formül/şekil adaylarını bulmak, metin katmanından tabloları okumak, şekil görsellerini çıkarmak ve tam dönüşüm Markdown'ında bunları doğru biçimde göstermek. Görsel modele gönderilecek adaylar bu fazda **işaretlenir** ama gönderilmez (Faz 07).

## Modüller

`src/visual_detector.py`, `src/table_extractor.py`, `src/figure_extractor.py`, `src/render.py`, `src/assets.py`; `src/pdf_parser.py`, `src/layout_analyzer.py`, `src/markdown_builder.py`, `src/batch_processor.py`, `src/document_model.py` güncellendi

## Ölçümle Alınan Tasarım Kararları

Uygulamadan önce gerçek setteki 9 makalede ölçüm yapıldı:

- **`find_tables()` akademik tabloların çoğunu bulamıyor:** 61 tablo başlığına karşılık yalnızca 8 tablo (Berardi 7, Pokorny 1). Tabloların çoğu dikey çizgisiz (booktabs), çizgisiz veya vektör çizim/görsel olarak gömülü (Vekkot)
- **Metin hizalamalı `find_tables(strategy="text")` güvenilir değil:** hücreleri böler ("Sampling N" | "umber of"), boş satırlar üretir. Bu çıktı "yapılandırılmış tablo" olarak sunulmadı
- **Sonuç:** Hücreler yalnızca çizgili tablolarda ve tutarlılık kontrolünden geçerse metin katmanından alınır. Diğer tablolar başlıktan bulunan bölge olarak işaretlenir (`needs_vision`), bölge görüntüsü `assets/tables/` altına konur ve satır yapısı korunmuş ham metin eklenir. §12.3 BALANCED modu bu tabloları Faz 07'de görsel modele gönderecek; o zamana kadar okuyucu tabloyu görüntüden görür

## Görevler

### 1. Şema (`DOCUMENT_SCHEMA_VERSION` 1.1, `PARSER_VERSION` 0.2.0 — eski önbellek geçersiz)

- [x] `Candidate`: `id`, `kind` (`table|equation|figure|algorithm`), `page`, `bbox`, `reasons`, `number`, `caption_block_id`, `ref_id`, `needs_vision`, `vision_trigger`; `DocumentModel.candidates`
- [x] `Table`: + `caption_block_id`, `raw_text`, `cache_path`
- [x] `Figure`: + `caption_block_id`, `image_xref`
- [x] `RawLine.math_chars` (matematik fontlu karakter sayısı), `RawBlock.ref_id`

### 2. Ayrıştırma akışı (`src/pdf_parser.py`)

Yeni sıra: ham çıkarım → üst/alt bilgi → **sayfa sınıfı** → **görsel tespit** (taranmış sayfalar hariç) → sütun boşluğu ve okuma sırası → blok türleri → bloklar → bölümler → tablo/formül/şekil modelleri

- [x] Görsel tespit okuma sırasından **önce** çalışır: bölgeye düşen metin blokları tek bir `table`/`equation`/`figure` bloğunda toplanır; okuma sırasında bu blok bütün olarak yer alır ve Markdown'da metin iki kez yazılmaz
- [x] Bu bloklar sütun tespitine, paragraf birleştirmeye, başlık puanlamasına ve belge başlığı seçimine katılmaz (`is_flow_text`)
- [x] Sayfa sınıfı artık okuma sırasından önce hesaplanır; taranmış/vektör metin sayfalarında görsel tespit yapılmaz (Faz 06–07)
- [x] Görsel tespit hatası sayfanın metnini kaybettirmez: `visual_detection_error` uyarısı

### 3. Tablolar (`src/visual_detector.py`, `src/table_extractor.py`)

- [x] **Çizgili tablolar:** `ruled_table_clip` — bir yatay çizgiyi kesen en az 3 ayrı dikey çizgi (≥2 sütun) varsa `find_tables()` yalnızca bu ızgara bölgesinde çağrılır. Hücre hücre ayrı çizilmiş satır çizgileri önce birleştirilir (Berardi)
- [x] Başlıksız çizgili tablo yalnızca ≥3 satır ve ≥2 sütunsa kabul edilir (özet kutusu gibi çerçeveler elenir)
- [x] **Tutarlılık** (`assess_cells`, §12.3): en az 2×2, birleştirilmemiş hücrelerin ≥%50'si dolu, tamamen boş satır/sütun yok
- [x] Tutarlı tablo → Markdown (ilk satır başlık, sayısal sütunlar sağa hizalı, `|` kaçışı); birleşik hücre varsa (`merged_cells_from_bboxes`) HTML (`rowspan`/`colspan`, HTML kaçışı)
- [x] **Başlık tabanlı bölge** (`_table_region_below`), sırasıyla:
  1. Yatay çizgiler: başlıktan ≤30 pt aşağıda başlayan ≥2 çizgi; aralarında düzyazı olmayan son çizgiye kadar (satırları uzun cümle olan tablolar da bulunur, tablo notları dışarıda kalır)
  2. Metin akışı: aynı sütunda düzyazı veya >30 pt boşluk gelene kadar
  3. Görsel/çizim kümesi: başlığın altında metin yoksa (vektör çizim veya görsel olarak gömülü tablo)
  - Bir sonraki tablo/şekil başlığı veya bölüm başlığı hiçbir durumda aşılmaz
  - Başlığın hemen altındaki içerik sütun boşluğunu kesiyorsa tablo tam genişlik sayılır (sola dayalı başlıklı tam genişlik tablolar, Elsevier)
- [x] Kalın "Table 1" etiketi ile başlık metni ayrı bloklara bölünmüşse birleştirilir (`merge_caption_labels`)
- [x] Hücreleri çıkarılamayan tablo: `consistent=False`, `needs_vision`, `vision_trigger=table_inconsistent`, `raw_text` (kelimeler satırlara gruplanır, geniş boşluklar iki boşlukla), `cache_path=tables/table_NN.png`

### 4. Formüller

- [x] **Tek başına numara satırı** `(n)` (≤45 pt genişlik): aynı yükseklikte, solunda ve **aynı sütunda** kalan satırlar gövdedir; gövdede matematik (matematik fontu ≥%20 veya `=∑∫…` sembolleri) şarttır; başka bir numara satırı gövdeye girmez; çok satırlı formüller ≤4 pt yakınlıktaki matematiksel satırlarla büyür
- [x] **Satır sonu numarası:** `... (n)` ile biten, matematik içeren ve düzyazı olmayan satır
- [x] Formül satırları bloklarından çıkarılır; kalan satırlar ayrı bloklar olarak korunur
- [x] `Equation`: `number`, `raw_text`, `section` (formülü içeren en derin bölüm), `bbox`; `latex=None`; aday `needs_vision=True`, `vision_trigger=equation_requested`
- [x] Matematik fontları: TeX (`CMMI`, `CMSY`, `CMEX`, `MSBM`…), Cambria Math, STIX, MathType, Symbol

### 5. Şekiller

- [x] Aday görseller: `get_image_info(xrefs=True)` (sayfanın ≥%0,2'si) ve `cluster_drawings()` kümeleri (≥%1, tablo bölgeleriyle örtüşmeyen)
- [x] Başlık (`Figure|Fig.|FIGURE|Şekil`) → aynı sütunda başlığın hemen üstündeki (≤60 pt), yoksa altındaki (≤40 pt) görsel; aradaki başka başlığı aşmadan 30 pt toleransla komşu görsellerle büyütülür (2×2 panelli şekiller)
- [x] Tek parçalı ve eksen hizalı gömülü görsel → `image_xref` (orijinal görsel çıkarılır); aksi halde bölge render edilir
- [x] Başlıksız şekil yalnızca sayfanın ≥%5'i büyüklüğündeki gömülü görseller için (logo ve yazar fotoğrafları elenir)
- [x] Şekil içindeki etiket blokları (alanının ≥%80'i içeride, <3 satır) akıştan çıkarılır
- [x] `referenced_by`: `Fig. 3`, `Figs. 2 and 3`, `Figures 2–4`, `Şekil 3` atıflarını içeren paragraf/liste blokları
- [x] Dosya adları: `figure_NN.png`, numarasızsa `figure_p<sayfa>_<sıra>.png`; çakışmada `_2` eki

### 6. Görsellerin üretimi — `src/figure_extractor.py`, `src/render.py`

- [x] `parse_pdf` saf kalır; görseller ayrı adımda (`materialize_assets`) PDF yeniden salt okunur açılarak `_cache/<sha>/figures|tables/` altına yazılır
- [x] Gömülü görsel: `Pixmap(xref)`, saydamlık maskesi uygulanır, CMYK → RGB; çevrilemezse bölge render edilir
- [x] Render: `pdf.render_dpi`, kenar payı `pdf.crop_padding_pt` (tablolarda en fazla 2 pt — sıkı bölgelerde başlık satırı görüntüye girmesin)
- [x] Mevcut görsel yeniden üretilmez; `--force` ile üretilir
- [x] Hata → `asset_extraction_failed: page n` uyarısı, belge devam eder

### 7. `assets/` — `src/assets.py`

- [x] `render_full_conversion` Markdown ile birlikte referans verilen önbellek yollarını döndürür; yalnızca bunlar `assets/figures|tables/` altına kopyalanır (§15)
- [x] Artık referans verilmeyen dosyalar silinir; hiç referans yoksa `assets/` oluşmaz/kaldırılır (§6.2)
- [x] Görseller Markdown'dan **önce** yazılır: Markdown hiçbir zaman olmayan bir görsele referans vermez
- [x] Aynı içerikli dosya yeniden kopyalanmaz

### 8. Markdown gösterimi

| Öğe | Gösterim |
|---|---|
| Tutarlı tablo | Markdown tablo veya birleşik hücreli HTML |
| Hücreleri çıkarılamayan tablo | `![başlık](assets/tables/table_NN.png)` + ham metin kod bloğu + `[table_structure_unavailable]` |
| Formül (LaTeX yok) | ham metin kod bloğu + `[latex_unavailable]` |
| Formül (LaTeX var, Faz 07) | `$$…$$`, geçersizse `[latex_unverified]` |
| Şekil | `![başlık](assets/figures/figure_NN.png)`; görsel yoksa `[figure_unavailable]` |

- [x] Kod bloğu çiti içerikteki en uzun ters tırnak dizisinden uzun seçilir
- [x] Başlık (caption) blokları ayrıca paragraf olarak kalır

**Karar — uyarı üretilmez:** `[table_structure_unavailable]` ve `[latex_unavailable]` belgeyi `completed_with_warnings` yapmaz. Bunlar Faz 07'de görsel modelle doldurulacak ara durumlardır; neredeyse her makalede bulunduğu için uyarı sayılsaydı durum bilgisi anlamını yitirirdi. Görsel model yok veya başarısızsa uyarı Faz 07'de verilecek. Görsel çıkarım hatası ise uyarıdır.

### 9. Performans

- `find_tables()` her sayfada çağrıldığında 20 PDF'lik fixture seti 3,8 sn'den 33 sn'ye çıkıyordu (süre ayrıştırmanın ~%90'ı). Izgara ön kontrolü ve kırpma ile **11 sn**. Kalan artışın ~4 sn'si 86 görselin 250 DPI üretimi (Faz 07'de görsel model de bu görüntüleri kullanacak)

## Gerçek Setteki Sonuçlar

| Makale | Tablo (bulunan/toplam) | Formül | Şekil |
|---|---|---|---|
| Imran | 8/8 (booktabs, bölge) | 0 | 6 |
| Lambay | 7/7 (tam genişlik, bölge) | 0 (kaynakçadaki "(4)" elendi) | 6 |
| Pokorny | 3/3 | 5 | 10 |
| Berardi | 6/6 (çizgili, **hücreler yapılandırılmış**) | 0 | 4 |
| Goodman | 5/6 (Tablo 2 döndürülmüş) | 0 | 2 |
| Polle | 2/3 | 4 | 3 |
| Rahman | 5/7 | 2 | 6 |
| Vekkot | 8/9 (vektör çizim tablolar dahil) | 5 | 10 (panelli şekiller birleşik) |
| Shilaskar | – (vektör metin, tespit yapılmaz) | – | – |

Görüntüler elle kontrol edildi: Imran Tablo 6 (booktabs bölgesi), Vekkot Tablo 4 (vektör çizim tablo), Vekkot Şekil 7 (3 panel).

## Bilinen Sınırlamalar

- **Döndürülmüş (yatay sayfa) tablolar** bulunmaz: başlıkları dikey metin (Goodman Tablo 2 ve devamları, Rahman Tablo 6–7)
- Polle Tablo 2 ve Vekkot Tablo 1 bölgesi bulunamadı
- **Numarasız formüller** tespit edilmez (FULL mod adayları, Faz 07)
- Satır içi matematik çok parçalı satırlarda formül ham metni dağınıktır (Pokorny, Polle); bölge ve görüntü doğrudur, LaTeX Faz 07'de
- Formül gövdesine aynı satırdaki kısa metin girebilir ("gave us")
- **Algoritma** blokları tespit edilmez (gerçek sette örnek yok); `Algorithm N` başlığı `caption` olarak kalır
- Tablo başlığının altında değil üstünde kalan tablolar (başlık altta) bulunmaz

## Testler

- [x] `test_table_extractor.py` — tutarlılık tablosu, birleşik hücre (colspan/rowspan), Markdown hizalama ve kaçış, HTML, kelimelerden satır metni
- [x] `test_visual_detector.py` — başlık etiketi birleştirme, düzyazı tespiti, ızgara ön kontrolü (ızgara/çerçeve/booktabs), hücre başına çizilmiş satır çizgileri, tek başına ve satır sonu formül numarası, matematiksiz kaynakça numarası, sütun sınırı, şekil panellerinin gruplanması ve etiketlerin akıştan çıkarılması, gömülü görsel xref'i ve küçük görsellerin elenmesi, iki başlık arasında gruplama sınırı, atıf numaralarının açılması ve şekil atıfları
- [x] `test_assets.py` — gömülü şekil PNG'si, mevcut görselin yeniden üretilmemesi ve `overwrite`, tablo bölgesi render'ı, hata raporu, `assets/` senkronizasyonu (kopyalama, eski dosya silme, boş klasör kaldırma)
- [x] `test_markdown_builder.py` — Markdown/HTML tablo, görüntü + ham metin + işaret, görsel yoksa işaretsiz görüntü, formül (ham/LaTeX/doğrulanmamış), şekil ve `[figure_unavailable]`, kod bloğu çiti
- [x] `test_pdf_parser.py` — sentetik: tablo hücreleri `EXPECTED` ile, formüller, şekil xref'i, blok bağlantıları, tablo hücrelerinin paragraf olarak tekrarlanmaması, adaylar; iki sütunda tablo bloğunun sırası; gerçek: Berardi 6 yapılandırılmış tablo, Imran 8 booktabs tablo ve ham metni, Vekkot vektör çizim tabloları ve birleşik panel şekli, Lambay'de kaynakça numarası formül değil, Pokorny'de formül numarası sütun aşmıyor
- [x] `test_cli_batch.py` — uçtan uca tablo/formül/şekil Markdown'ı, `assets/figures/figure_01.png`, görsel referansı olmayan belgede `assets/` yok, belge klasöründe yalnızca `.md` ve referans verilen `assets/` (§38 kriter 2)

## Tamamlanma Kriterleri

- [x] Metin tabanlı gerçek makalelerde çizgili tablolar metin katmanından doğru çıkıyor (Berardi 6/6); diğerleri `needs_vision` işaretli ve bölge görüntüsüyle
- [x] Şekiller `assets/figures/` altında ve Markdown'dan açılabiliyor
- [x] Metin LLM'i veya görsel model hâlâ çağrılmıyor
- [x] `pytest` yeşil (335 geçti, 1 atlandı — Tesseract kurulu değil)
