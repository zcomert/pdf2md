# Faz 11 — Envanter Tablosu, Künye Çıkarımı ve Analitik Sütunlar

**İlgili bölümler:** §3.3, §22, §38.5 (kriter 25, 26)
**Önkoşul:** Faz 10
**Tahmini büyüklük:** Orta

## Amaç

Prompttan bağımsız, sabit sütunlu `papers_summary.csv` envanterini üretmek; her belge için künye bilgisini düşük maliyetle çıkarmak ve isteğe bağlı analitik sütunları desteklemek.

## Modüller

`src/bibliographic.py`, `src/summary_writer.py`

## Karar Noktası (uygulamadan önce)

§16.3 ve §38 kriter 4 "varsayılan promptta metin LLM'i çağrılmaz" derken §22.3 "künye için her belgede eksik alanlar için kısa LLM çağrısı" der. Önerilen çözüm:

- Künye çıkarımı **tam dönüşüm içeriğinin** parçası değildir; ayrı bir envanter adımıdır ve `text_llm_calls` sayacına ayrı etiketle (`bibliographic`) yazılır.
- Kriter 4, "`A.md` içeriği üretilirken metin LLM'i çağrılmaz" olarak okunur.
- Künye sonucu `_cache/<sha>/bibliographic_<text_model_digest8>.json` altında önbelleklenir; skip edilen belgelerde çağrı yapılmaz (kriter 12 korunur).
- İstenirse `summary.bibliographic_llm: true|false` anahtarı eklenebilir (varsayılan `true`). Bu yeni bir config anahtarıdır; eklenirse gereksinim belgesi §25 güncellenmelidir.

Karar verildikten sonra gereksinim belgesine not düşülür.

## Görevler

### 1. Künye çıkarımı — `src/bibliographic.py`

§22.3 sırası:

- [ ] **1. PDF metadata:** `title`, `author` (`;` veya `,` ile bölünmüş), `creationDate` → yıl adayı (düşük öncelik: oluşturma tarihi yayın yılı olmayabilir; yalnızca başka kaynak yoksa ve uyarıyla). Anlamsız metadata filtreleri: `untitled`, `Microsoft Word - ...`, dosya adıyla aynı başlık, 5 karakterden kısa
- [ ] **2. DOI regex:** ilk sayfa (yoksa ilk 2 sayfa) metninde `\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b` (harf duyarsız), sondaki noktalama temizlenir; `doi.org/` önekleri
- [ ] **3. LLM (yalnızca eksik alan varsa):** ilk 1–2 sayfanın metni (Faz 09 bağlam biçimiyle, blok kimlikleri dahil) + eksik alan listesi → şemalı yanıt `{title, authors, year, venue, doi}` her biri `FieldValue` + kanıt
- [ ] Doğrulama: LLM'in verdiği `year` ve `doi` kaynak metinde geçmeli; geçmiyorsa boş bırakılır (tahmin yasağı). `title` için normalize edilmiş metnin ilk sayfada geçmesi kontrolü
- [ ] Ollama yoksa/erişilemiyorsa LLM adımı atlanır, uyarı; belge başarısız sayılmaz
- [ ] Bulunamayan değer boş (§22.3)
- [ ] Sonuç önbelleğe; ayrıca çıkarım sırasında plan zaten `bibliographic.*` istediyse o değerler tekrar kullanılır (çift çağrı yok)

### 2. Analitik sütunlar — `summary.extra_fields`

- [ ] Config doğrulaması: her anahtar alan kataloğunda olmalı (Faz 08 `field_catalog`)
- [ ] Liste boş değilse, her belge için ayrı bir "özet planı" oluşturulur (`requested_fields = extra_fields`, `output_outline` yok) → Faz 09 çıkarım hattı → `extractions/<summary_plan_hash>.json`
- [ ] `results.best_model`, `results.best_accuracy`, `results.best_f1` gibi türetilmiş alanlar: `results[]` listesinden deterministik seçim (metrik adına göre en yüksek `verified` değer)
- [ ] CSV'ye **yalnızca `verified`** değerler yazılır; diğerleri boş hücre (§22.4, §19.1)
- [ ] Sütun adları alan anahtarıyla aynı (`dataset.name`)
- [ ] Bu çıkarım prompttan bağımsızdır ve state atlama kuralında ayrı değerlendirilir (özet plan hash'i değişmedikçe yeniden yapılmaz)

### 3. CSV yazıcı — `src/summary_writer.py`

- [ ] §22.2'deki sütunlar **tam bu sırayla**, ardından `extra_fields` sütunları
- [ ] Kaynak: `processing_state.json` (tüm belgeler, bu çalıştırmada görülmeyenler dahil) + `_cache` verileri (`document.json` → `pages`, `scanned_pages`, `ocr_pages`; stats → çağrı sayıları; künye önbelleği)
- [ ] Önbellek silinmişse ilgili sütunlar boş kalır, hata yok (§6.2 "`_cache` silinirse sistem çalışmaya devam eder")
- [ ] `authors` `;` ile birleştirilir
- [ ] `error_message` kısa: tek satır, ≤ 200 karakter
- [ ] UTF-8 **BOM'lu** (`utf-8-sig`), `csv.QUOTE_MINIMAL`, satır sonu `\r\n` (Excel uyumu)
- [ ] Atomik yazım
- [ ] Yazım zamanı: her belge bitiminde ve çalıştırma sonunda (§22.1). Paralel akışta ana süreçte, state kilidi altında
- [ ] `output.save_xlsx: true` → `pandas.DataFrame.to_excel(engine="openpyxl")` atomik (geçici dosya + `os.replace`); `openpyxl` yoksa preflight uyarısı ve XLSX atlanır

### 4. Çalıştırma özetleri (§22.5)

- [ ] Sayılar CSV'ye satır olarak **eklenmez**
- [ ] Konsol + log sonu + `runs[run_id]` (Faz 10'da yapıldı — CSV'de özet satırı olmadığını test et)

## Testler

- DOI regex: `https://doi.org/10.1016/j.eswa.2023.119001.` → sondaki nokta temizlenmiş
- Metadata filtreleri: `Microsoft Word - paper.docx` başlık olarak kullanılmaz
- `FakeTextClient` künye: kaynakta geçmeyen yıl → boş
- CSV: sütun sırası §22.2 ile birebir; BOM mevcut; Türkçe karakterli başlık (`Yorgunluk Tespiti İçin Derin Öğrenme`) bayt düzeyinde doğru
- State'te olup bu çalıştırmada filtre dışı kalan belge CSV'de son durumuyla yer alır
- `extra_fields: ["results.best_accuracy"]` → yalnızca `verified` değer yazılır; `unverified` için boş
- Varsayılan prompt + künye önbelleği dolu → ikinci çalıştırmada model çağrısı 0

## Tamamlanma Kriterleri

- [ ] `papers_summary.csv` Excel'de açıldığında Türkçe karakterler bozulmuyor (elle kontrol, §38 kriter 25)
- [ ] Referans verili 3 makalede künye alanları elle karşılaştırılmış
- [ ] Karar noktası gereksinim belgesine işlenmiş
- [ ] `pytest` yeşil
