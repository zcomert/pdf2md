# Faz 11 — Envanter Tablosu, Künye Çıkarımı ve Analitik Sütunlar

**İlgili bölümler:** §3.3, §22, §38.5 (kriter 25, 26)
**Önkoşul:** Faz 10
**Tahmini büyüklük:** Orta

## Amaç

Prompttan bağımsız, sabit sütunlu `papers_summary.csv` envanterini üretmek; her belge için künye bilgisini düşük maliyetle çıkarmak ve isteğe bağlı analitik sütunları desteklemek.

## Modüller

`src/bibliographic.py`, `src/summary_writer.py` (yeni); `src/config.py` (`summary.bibliographic_llm`, `extra_fields` doğrulaması), `src/field_catalog.py` (türetilmiş `results.best_<metrik>`), `src/schemas.py` (`Bibliographic`, `DocumentState` envanter alanları), `src/prompt_planner.py` (`summary_signature`), `src/batch_processor.py` (envanter adımı), `src/cli.py`, `src/preflight.py` (`check_xlsx`)

## Karar Noktası — verildi

§16.3 ve §38 kriter 4 "varsayılan promptta metin LLM'i çağrılmaz" derken §22.3 "künye için eksik alanlarda kısa LLM çağrısı" der. **Kullanıcı kararı: ayrı adım, varsayılan açık.**

- Künye çıkarımı tam dönüşüm içeriğinin parçası değildir; ayrı bir envanter adımıdır. Çağrılar belgenin `text_llm_calls` sayısına eklenir; `A.md` front matter'ındaki `models` boş kalır
- Kriter 4, "`A.md` içeriği üretilirken metin LLM'i çağrılmaz" olarak okunur
- Künye sonucu `_cache/<sha>/bibliographic_v<sürüm>_<text_model_digest8>.json` (LLM kapalıysa `_nollm`) altında önbelleklenir; atlanan belgelerde çağrı yapılmaz (kriter 12 korunur)
- Yeni config anahtarı `summary.bibliographic_llm: true` (varsayılan)
- **Gereksinim belgesi güncellenmedi** (kullanıcı kararı: kararlar faz dosyalarında kalır). İşlenmesi gerekenler: §22.3 ve §38 kriter 4 yorumu, §25'e `summary.bibliographic_llm`

## Görevler

### 1. Künye çıkarımı — `src/bibliographic.py`

§22.3 sırası:

- [x] **1. PDF metadata:** `title` (anlamsız değer filtreleri: `untitled`, `Microsoft Word - …`, dosya uzantısı, dosya adıyla aynı, 5 karakterden kısa); `author` yalnızca **birden fazla yazar** içeriyorsa (Elsevier metadata'sında tek isim ilk yazardır, yazar listesi değildir); yayıncı `subject` kalıpları → dergi, yıl, DOI (Elsevier "Journal of Safety Research, 90 (2024) 100-114. doi:…", IEEE "IEEE Access;2025;13; ;10.1109/…")
  - Karar: `creationDate` yıl kaynağı olarak **kullanılmadı** (oluşturma tarihi yayın yılı değildir; Pokorny 2023'te oluşturulmuş, 2024 yayını)
- [x] **2. DOI regex:** ilk 2 sayfa, `10.\d{4,9}/…` (harf duyarsız), sondaki noktalama ve eşleşmeyen `)` temizlenir
- [x] **Ek (LLM'siz):** ayrıştırıcının başlık tespiti (§16.2); satır sonu tirelemesi kalıntısı temizlenir ("pre- trained" → "pre-trained")
- [x] **Ek:** plan çıkarımı zaten `bibliographic.*` istediyse doğrulanmış değerler kullanılır (çift çağrı yok)
- [x] **3. LLM (yalnızca eksik alan varsa):** ilk 2 sayfa (Faz 09 bağlam biçimi, blok kimlikleri) + yalnızca eksik alanlar → Faz 09 çıkarım hattı (şemalı yanıt, doğrulama, yeniden deneme)
- [x] Tahmin yasağı: yıl (4 hane) ve DOI ilk sayfaların metninde birebir geçmeli; yazar adları tek tek kaynakta geçmeli (geçmeyenler atılır); başlık/dergi kanıt bloğunda geçmeli; aksi halde boş
- [x] Ollama erişilemiyor / zaman aşımı / geçersiz yanıt → uyarı loglanır, belge başarısız sayılmaz; bu durumda önbelleğe yazılmaz (sonra yeniden denenir)
- [x] Bulunamayan değer boş

### 2. Analitik sütunlar — `summary.extra_fields`

- [x] Config doğrulaması: katalog alanı veya `results.best_<metrik>` (`accuracy`, `f1`, `precision`, `recall`, `auc` eş adlarıyla); bilinmeyen anahtar → çıkış 2
- [x] Liste boş değilse belge başına **özet planı** (`requested_fields` = katalog alanları; türetilmiş metrikler için `results.best`) → Faz 09 çıkarım hattı → `extractions/<özet_plan_hash[:32]>.json`
- [x] `results.best_<metrik>`: metrik adı eşleşen `verified` sonuçlar arasında en yüksek değer (yüzdeler oran olarak karşılaştırılır), `value_text` yazılır; `results.best_model`: alan değeri güvenilir değilse en yüksek doğrulanmış sonucun modeli
- [x] CSV'ye **yalnızca doğrulanmış** değerler (§22.4). Karar: sayısal olmayan alanlarda (ör. `dataset.name`) doğrulama etiketi yoktur; değer metninin kanıtta geçmesi (`in_evidence`) ve güvenin `low` olmaması şartı aranır
- [x] Sütun adları alan anahtarıyla aynı
- [x] Atlama kuralı: envanter imzası (künye sürümü, `bibliographic_llm`, `extra_fields`, bunlar LLM kullanıyorsa metin modeli digest'i) plan hash'ine girer; değişince belgeler önbellekten yeniden işlenir. Prompt çıkarımının önbellek anahtarı imzasız **içerik hash'idir**, bu yüzden envanter ayarı değişince prompt çıkarımı tekrarlanmaz

**Karar (Faz 08 kararının güncellenmesi):** Faz 08'de varsayılan planın hash'ine metin modeli girmiyordu. Künye LLM'i açıkken envanter çıktısı metin modeline bağlı olduğu için artık girer (envanter imzası üzerinden). Gemma güncellenince tam dönüşümler önbellekten yeniden yazılır, künye yeniden çıkarılır.

**Geçiş notu:** Faz 10 ve öncesi state kayıtlarında plan hash'i envanter imzası içermez; bu belgeler bir kez (önbellekten, künye çağrısıyla) yeniden işlenir.

### 3. CSV yazıcı — `src/summary_writer.py`

- [x] §22.2 sütunları **tam bu sırayla**, ardından `extra_fields`
- [x] Kaynak: `processing_state.json` (tüm belgeler; bu çalıştırmada görülmeyenler ve hiç işlenmemişler dahil)
  - Karar: sayfa sayıları, çağrı sayıları ve künye `_cache` yerine **state'e** (`DocumentState.pages/scanned_pages/ocr_pages/vision_calls/text_llm_calls/bibliographic/summary_values`) yazılır; önbellek silinse de CSV eksiksiz kalır (faz planında önbellek silinirse sütunların boş kalması kabul ediliyordu)
  - `vision_calls` / `text_llm_calls`: belgenin son işlenişindeki çağrılar (önbellekten gelen sonuçlar 0)
- [x] `authors` `; ` ile; `error_message` tek satır, ≤ 200 karakter
- [x] UTF-8 **BOM'lu**, `csv.QUOTE_MINIMAL`, `\r\n`; atomik yazım
- [x] Yazım zamanı: her belge sonunda (başarılı veya başarısız) ve çalıştırma sonunda (§22.1); yalnızca ana süreçte. Yazılamazsa (ör. Excel'de açık, kilitli) uyarı, belge başarısız sayılmaz
- [x] `output.save_xlsx: true` → `pandas` + `openpyxl`, geçici dosya + `os.replace`; `openpyxl` yoksa başlangıçta uyarı (`check_xlsx`) ve yalnızca CSV

### 4. Çalıştırma özetleri (§22.5)

- [x] Sayılar CSV'ye satır olarak eklenmez (test: satır sayısı = belge sayısı)
- [x] Konsol + log sonu + `runs[run_id]` (Faz 10)

## Gerçek Set (9 makale, FAST, `gemma4:latest`)

Ayrıştırma önbellekten; 9 künye çağrısı, çağrı başına 8,5–17,7 sn (toplam 108,6 sn). `SOURCES.md`'deki künye bilgileriyle karşılaştırma:

| Alan | Doğru | Kaynak dağılımı | Not |
|---|:---:|---|---|
| Başlık | 9/9 | metadata 5, ayrıştırıcı 4 | Rahman "pre- trained" kalıntısı düzeltildi |
| Yazarlar | 9/9 | LLM 9 | Pokorny 12 yazar eksiksiz; Vekkot büyük harfle (PDF'deki gibi) |
| Yıl | 8/9 | metadata 5, LLM 3 | Berardi boş (model yılı doğrulanabilir biçimde vermedi; tahmin edilmedi) |
| Dergi/konferans | 9/9 | metadata 5, LLM 4 | |
| DOI | 9/9 | metadata 6, regex 3 | |

## Bilinen Sınırlamalar

- Yazar adları PDF'deki yazımla (büyük harf, üst simge ayrılmış) gelir; normalize edilmez
- Yıl yalnızca metadata'dan veya ilk sayfalarda geçen 4 haneden; ilk sayfalarda yazmayan yayınlarda boş kalır
- Analitik sütunlarda metrik eşleştirmesi ada dayalıdır (`Accuracy`, `acc`, `F1-score`…); farklı adlandırılmış metrikler kaçabilir
- Sonuç `verified` kuralı Faz 09'daki satır düzeyi sınırlamayı taşır (doğru sütun garanti değildir)
- CSV Excel'de elle açılıp kontrol edilmedi (aşağıda)

## Testler

- [x] `test_inventory.py` (24): DOI regex (sondaki nokta, `doi:` öneki, parantez, SICI biçimi); başlık filtreleri; Elsevier/IEEE `subject` kalıpları ve tek yazar kuralı; **kaynakta geçmeyen yıl ve yazar → boş/atılır**, LLM'e yalnızca eksik alanlar gider; künye önbelleği ve LLM anahtarı; servis kapalı → yalnızca uyarı; plan çıkarımındaki değerlerin yeniden kullanımı; CSV sütun sırası, BOM, `\r\n`, **Türkçe başlık bayt düzeyinde**, virgüllü alan, hata mesajı kısaltma, hiç işlenmemiş belge, özet satırı yok; XLSX; `extra_fields` doğrulaması; analitik sütunlarda **yalnızca `verified`** (unverified daha yüksek değer yok sayılır, uydurma veri seti adı yazılmaz); uçtan uca: künye ve analitik sütunlar CSV'de, çıktı silinip yeniden işlenince **metin çağrısı 0** (önbellek), envanter ayarı değişince yeniden işleme; çalıştırma sonunda keşif hataları dahil tüm state belgeleri ve filtre dışı belgeler CSV'de; XLSX başlangıç uyarısı; başlık tireleme temizliği
- [x] Önceki testler güncellendi: görsel çağrı sayan testler yalnızca görsel görevleri sayar; varsayılan çalıştırmada `text_llm_calls` = 1 (künye)

## Tamamlanma Kriterleri

- [ ] `papers_summary.csv` Excel'de açıldığında Türkçe karakterler bozulmuyor (**elle kontrol, yapılmadı**): BOM, UTF-8 baytları ve `\r\n` otomatik testte doğrulanıyor; Excel'de açma kullanıcı tarafından yapılmalı (§38 kriter 25)
- [x] Künye alanları gerçek 9 makalede `SOURCES.md` ile elle karşılaştırıldı (referans YAML'ları hâlâ yok — Faz 01 açığı)
- [ ] Karar noktası gereksinim belgesine işlenmiş — **kullanıcı kararıyla faz belgesinde bırakıldı**
- [x] `pytest` yeşil — 528 sahte arka uçla + 9 `requires_ollama`
