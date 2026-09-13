# Faz 05 — Görsel Aday Tespiti, Metin Tabanlı Tablo ve Şekil Çıkarımı

**İlgili bölümler:** §12.2, §12.4 (kırpma kısmı), §13 (1, 2, 4, 5. adımlar), §14 (metin tabanlı), §15, §6.2 (`assets/`)
**Önkoşul:** Faz 04
**Tahmini büyüklük:** Büyük

## Amaç

Model kullanmadan elde edilebilecek her şeyi çıkarmak: tablo/formül/şekil/algoritma adaylarını bulmak, metin katmanından tabloları okumak, gömülü şekil görsellerini çıkarmak ve tam dönüşüm Markdown'ında bunları doğru biçimde göstermek. Görsel modele gönderilecek adaylar bu fazda **işaretlenir** ama gönderilmez (Faz 07).

## Modüller

`src/visual_detector.py`, `src/table_extractor.py`, `src/equation_extractor.py` (metin kısmı), `src/figure_extractor.py`, `src/render.py` (kırpma), `src/assets.py`

## Görevler

### 1. Aday modeli

- [ ] `Candidate`: `id`, `kind` (`table|equation|figure|algorithm`), `page`, `bbox`, `reasons: list[str]` (örn. `["caption:Table 3", "find_tables", "line_grid"]`), `number`, `caption_block_id`, `needs_vision: bool`, `vision_trigger: str | None`
- [ ] Adaylar `DocumentModel` içinde `candidates[]` olarak saklanır (şema sürümüne ekleme; Faz 03'te eklenmediyse şimdi `schema_version` artırılır)

### 2. Aday tespiti — `src/visual_detector.py`

Metin ve geometrik göstergeler birleştirilir; **tek başına metin göstergesi aday oluşturmaz** (§12.2).

- [ ] Başlık (caption) regex'leri: `^(Table|TABLE|Tablo)\s+([IVX\d]+)`, `^(Figure|Fig\.|FIGURE|Şekil)\s*(\d+)`, `^(Algorithm|Algoritma)\s+(\d+)`
- [ ] Formül numarası: satır sonunda `\((\d+[a-z]?)\)$`; metinde `Eq.`, `Equation`, `Eqn.` referansları
- [ ] Geometri:
  - `page.find_tables()` sonuçları
  - `page.get_drawings()` → yatay/dikey çizgi segmentleri; ızgara oluşturan kümeler → tablo bölgesi
  - Yoğun vektör çizim kümesi (çizgi/eğri sayısı eşiği) → şekil bölgesi
  - Görsel bloklar → şekil bölgesi
  - Matematik fontları (`CMMI`, `CMSY`, `CMEX`, `MSBM`, `Cambria Math`, `STIX`, `Symbol`) veya sembol karakter oranı yüksek (`∑∫∂≤≥±×αβγ...`) satırlar → formül
  - Ortalanmış, kısa, gövdeden ayrışan satırlar → formül/algoritma desteği
- [ ] Eşleştirme: caption bloğu ile en yakın geometrik bölge (tablo için genellikle caption **üstte**, şekil için **altta**; ikisini de dene, mesafe eşiği)
- [ ] Çakışan adayların birleştirilmesi (IoU tabanlı)
- [ ] Adaya dahil olan gövde blokları `table`/`equation`/`figure`/`algorithm` tipine çevrilir ve `ref_id` bağlanır (Markdown'da metin iki kez yazılmasın)

### 3. Tablo çıkarımı (metin katmanı) — `src/table_extractor.py`

- [ ] `find_tables()` sonucu → `cells: list[list[str | None]]`
- [ ] **Tutarlılık** (§12.3 tanımı): tablo bulunamadı veya satırların hücre sayıları tutarsız → `consistent = False`, `needs_vision = True`, `vision_trigger = "table_inconsistent"`
- [ ] Tutarlıysa `source_method = "text"`
- [ ] `None`/boş hücre: gerçekten boş mu yoksa okunamıyor mu ayrımı yapılamıyorsa boş bırak; okunamayan hücre `[unclear]` yalnızca görsel modelde (Faz 07) belirlenir
- [ ] Birleşik hücre tespiti (PyMuPDF `header` / hücre bbox genişlikleri) → `has_merged_cells` → HTML tablo (`rowspan`/`colspan`)
- [ ] Markdown tablo üretimi: `|` kaçışı, sayısal sütunlar sağa hizalı (`---:`), ilk satır başlık
- [ ] Caption ve numara saklanır

### 4. Formül (metin katmanı) — `src/equation_extractor.py`

- [ ] Formül adayının metin katmanındaki ham metni `raw_text` olarak saklanır
- [ ] Bu fazda LaTeX **üretilmez** (metin katmanından güvenilir LaTeX çıkarılamaz). `latex = None`, `needs_vision = True` (plan formül istiyorsa — Faz 07/08'de karar), `description` yakın metinden alınmaz (Faz 09'da değil, §14'e göre yalnızca PDF'de açıkça geçen açıklama; basit kural: formülden hemen sonra `where`/`burada` ile başlayan cümle)
- [ ] Tam dönüşümde LaTeX yoksa ham metin kod bloğu olarak ve `[latex_unavailable]` notuyla yazılır

### 5. Şekil çıkarımı — `src/figure_extractor.py`

- [ ] Şekil bölgesi tek bir gömülü görselle örtüşüyorsa: `doc.extract_image(xref)` → orijinal bayt; PNG değilse Pillow ile PNG'ye çevir
- [ ] Vektör çizim veya çoklu görsel ise: bölge render + kırpma (aşağıda)
- [ ] Dosya adı: `figure_<NN>.png`, numarasızsa `figure_p<sayfa>_<sıra>.png` (§15)
- [ ] `_cache/<sha>/figures/` altına yaz
- [ ] Metin içindeki `Fig. 3` / `Figure 3` / `Şekil 3` referanslarını içeren paragraf `block_id`'leri → `referenced_by`

### 6. Render ve kırpma — `src/render.py`

- [ ] `render_region(page, bbox, dpi, padding_pt) -> Path` — `page.get_pixmap(dpi=dpi, clip=padded_bbox)`; bbox sayfa sınırına kırpılır
- [ ] Önbellek anahtarı: `p{page}_{bbox yuvarlanmış}_{dpi}.png` → varsa tekrar kullanılır (§12.4)
- [ ] `render_page(page, dpi)` — tam sayfa (Faz 06–07 için)

### 7. `assets/` yönetimi — `src/assets.py`

- [ ] Markdown üretimi sırasında referans verilen görseller toplanır
- [ ] Yazım sonrası yalnızca bu görseller `assets/figures|tables|equations/` altına kopyalanır (§15); hiç referans yoksa `assets/` oluşturulmaz (§6.2)
- [ ] Önceki çalıştırmadan kalan, artık referanslanmayan asset'ler temizlenir (yeniden üretimde yetim dosya kalmasın)
- [ ] Markdown'daki yol göreli: `assets/figures/figure_03.png`

### 8. Markdown builder güncellemesi

- [ ] `table` → Markdown/HTML tablo + caption
- [ ] `figure` → `![Figure 3. Caption](assets/figures/figure_03.png)`
- [ ] `equation` → LaTeX varsa `$$...$$`, yoksa ham metin + işaret
- [ ] `algorithm` → kod bloğu

## Testler

- `synthetic_table_equation.pdf`: tablo hücreleri beklenen değerlerle birebir, formül adayları `(1)` ve `(2)` bulunur, `Figure 1` görseli çıkarılır ve PNG olarak kaydedilir
- Yalnızca metinde `Table 5` geçen (geometrisi olmayan) paragraf aday oluşturmaz
- Tutarsız hücre sayılı tablo → `needs_vision=True`, trigger `table_inconsistent`
- Birleşik hücreli tablo → HTML çıktı
- `assets/` yalnızca şekil referansı varsa oluşur
- Gerçek makale referans verisindeki tablolar için hücre eşleşme oranı loglanır (eşik yok, ölçüm Faz 14'te)

## Tamamlanma Kriterleri

- [ ] Metin tabanlı gerçek makalelerde referans tabloların çoğu metin katmanından doğru çıkıyor; çıkmayanlar `needs_vision` işaretli
- [ ] Şekiller `assets/figures/` altında ve Markdown'dan açılabiliyor
- [ ] Metin LLM'i veya görsel model hâlâ çağrılmıyor
- [ ] `pytest` yeşil
