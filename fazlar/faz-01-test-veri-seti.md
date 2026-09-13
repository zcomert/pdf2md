# Faz 01 — Test Veri Seti ve Fixture Altyapısı

**İlgili bölümler:** §38.1
**Önkoşul:** Faz 00
**Tahmini büyüklük:** Küçük–Orta (referans veri hazırlığı elle yapılır, zaman alır)

## Amaç

Tüm sonraki fazların birim ve entegrasyon testlerinde kullanılacak PDF setini erkenden hazırlamak. Geç hazırlanan test verisi, ayrıştırıcının "sadece elimdeki PDF'te çalışır" hale gelmesine yol açar.

## Görevler

### 1. Sentetik PDF üreticisi — `tests/fixtures/generate_fixtures.py`

PyMuPDF ile programatik olarak üretilen, içeriği tam bilinen PDF'ler. Beklenen içerik (başlıklar, tablo hücreleri, formüller, okuma sırası işaretleri) `EXPECTED` sözlüğündedir; sonraki fazların testleri buradan okur.

Üretim: `.venv\Scripts\python.exe -m tests.fixtures.generate_fixtures [--out KLASÖR] [--overwrite-encrypted]`

- [x] `synthetic_single_column.pdf` — başlık, `Abstract`, numaralı bölümler (`1. Introduction`, `2.1 Dataset`), paragraflar, madde listesi
- [x] `synthetic_two_column.pdf` — iki sütunlu gövde, tam genişlik başlık ve tam genişlik tablo; okuma sırası için `LEFT-TOP`, `RIGHT-TOP`, `LEFT-BOTTOM`, `RIGHT-BOTTOM` işaretleri
- [x] `synthetic_table_equation.pdf` — çizgili tablo (hücre değerleri bilinen), `(1)`, `(2)` numaralı formül satırları, `Figure 1` başlıklı gömülü PNG
- [x] `synthetic_header_footer.pdf` — 4 sayfa, her sayfada tekrarlanan dergi adı ve `Page n of 4`
- [x] `synthetic_scanned.pdf` — metin içeren sayfanın 200 DPI render'ı, metin katmanı olmadan görsel olarak eklenmiş
- [x] `synthetic_encrypted.pdf` — kullanıcı parolalı (boş parola ile açılmayan; parola `EXPECTED` içinde)
- [x] `synthetic_encrypted_empty_pw.pdf` — yalnızca sahip parolalı (boş parola ile açılabilen) — §28
- [x] `corrupt.pdf` — geçerli PDF'in ilk 16 baytı (başlık) + sabit tohumlu rastgele bayt
- [x] `not_a_pdf.PDF` — büyük harf uzantılı, aslında metin dosyası
- [x] `subdir/synthetic_single_column.pdf` — kökteki ile **aynı ad, farklı içerik** (§6.2 çakışma)
- [x] `duplicate_copy.pdf` — kökteki `synthetic_single_column.pdf` ile **aynı içerik, farklı ad** (§8.2 önbellek paylaşımı)

Üretici deterministiktir (sabit metin, sabit metadata tarihi, `no_new_id=True`, sabit rastgele tohum). Üretilen dosyalar git'e eklenir.

**Uygulamada ortaya çıkan kararlar:**

- **Şifreli PDF'ler deterministik değil.** MuPDF tüm şifreleme yöntemlerinde (RC4-40/128, AES-128/256) rastgele değer kullanır. Bu iki dosya `NONDETERMINISTIC` kümesindedir: üretici mevcut dosyaya dokunmaz (`--overwrite-encrypted` ile yeniden üretilir), testler hash yerine davranışlarını doğrular.
- **`corrupt.pdf` yalnızca başlığı içerir.** İlk ~2 KB bırakıldığında MuPDF xref'i onararak dosyayı açıp metnin bir kısmını okuyabiliyor (1 sayfa, 539 karakter). "Bozuk PDF → `failed(parse)`" testinin anlamlı olması için dosya açılamayacak şekilde bozuldu. Faz 03'te ayrıca "açıldı ama `page_count == 0`" durumu da bozuk sayılmalıdır.
- **Başlık seviyeleri:** makale başlığı seviye 1, numaralı bölümler seviye 2, alt bölümler seviye 3 (Faz 03 test maddesi buna göre düzeltildi).
- Base14 fontlar Türkçe karakterleri (`ğ`, `ş`, `ı`) desteklemediği için sentetik PDF'ler İngilizcedir. Türkçe içerik gerçek makale setinden veya ileride gömülü fontlu ek bir fixture'dan gelmelidir.

### 2. Gerçek makaleler — `tests/fixtures/real/`

§38.1'in istediği gerçekçi set. Lisansı paylaşıma uygun (ör. arXiv CC-BY) makaleler seçilir. **Elle yapılacak.**

- [ ] 4 metin tabanlı tek sütunlu makale
- [ ] 3 çift sütunlu makale (en az biri tablo ve formül yoğun)
- [ ] 2 taranmış PDF (gerçek tarama veya yüksek kaliteli sentetik)
- [x] `tests/fixtures/real/SOURCES.md` şablonu (dosya adı, tür, kaynak URL, lisans, SHA-256, referans YAML)
- [ ] `SOURCES.md` tablosunun doldurulması

### 3. Referans veri — `tests/fixtures/reference/<ad>.yaml`

Şema: `tests/reference_schema.py` (`ReferenceData`). Alanlar: `source` (`tests/fixtures`'a göre yol), `sha256`, `kind` (`real` | `synthetic`), `bibliographic`, `tables`, `equations`, `results`.

- `kind: real` için §38.1 minimumları şemada zorunludur: en az 2 tablo, 3 formül, 5 sonuç
- Tablo satırlarının hücre sayısı başlıkla aynı olmalıdır
- Şablon: `reference/TEMPLATE.yaml.example`

- [x] Şema ve yükleyici (`load_reference`, `reference_files`)
- [x] `reference/synthetic_table_equation.yaml` — şema örneği ve Faz 14 ölçüm aracının hızlı testi için
- [x] `reference/TEMPLATE.yaml.example`
- [ ] 3 gerçek makale için referans YAML (**elle yapılacak**)

### 4. Test altyapısı

- [x] `conftest.py`: `fixtures_dir`, `synthetic_pdf(name)` fixture'ları
- [x] `tmp_input_copy` — fixture PDF'lerini (alt klasörler dahil, `.py`/`reference/` hariç) geçici bir giriş klasörüne kopyalar
- [x] `tmp_output` — giriş dışında, henüz oluşturulmamış çıktı klasörü yolu
- [x] `tests/helpers.py`: `input_snapshot(path) -> dict[relpath, sha256]`, `sha256_file` (§38 kriter 17). conftest'ten import edilmemesi için ayrı modülde
- [x] `requires_tesseract` (PATH, `TESSERACT_PATH` ortam değişkeni veya `C:\Program Files\Tesseract-OCR`) ve `requires_ollama` (`OLLAMA_ENDPOINT`, varsayılan `http://127.0.0.1:11434/api/tags`) işaretleri; ortamda yoksa `skip`
- [x] `pytest.ini`: `testpaths`, PyMuPDF SWIG uyarı filtreleri; conftest'te beklenen MuPDF hata mesajları gizlenir

## Testler — `tests/test_fixtures.py`

- [x] Tüm `EXPECTED` dosyaları mevcut
- [x] Üretici iki kez çalıştırıldığında deterministik dosyalar aynı SHA-256'yı üretir
- [x] Git'teki fixture'lar üreticinin çıktısıyla aynı (bayat fixture tespiti)
- [x] Üretici mevcut şifreli dosyaları korur
- [x] Sayfa sayıları; başlık ve liste metinleri; iki sütun işaretleri ve tablo; tablo hücreleri, formül numaraları, gömülü görsel; her sayfada üst/alt bilgi
- [x] Taranmış PDF'in metin katmanı boş
- [x] Şifreli PDF boş parolayla açılmaz, doğru parolayla açılır; sahip parolalı PDF açılır
- [x] `corrupt.pdf` ve `not_a_pdf.PDF` açılışta `FileDataError`
- [x] Aynı ad/farklı içerik ve farklı ad/aynı içerik
- [x] `tmp_input_copy` yalnızca PDF içerir; `tmp_output` giriş dışında
- [x] Tüm referans YAML'ları şemaya uyar ve kaynak PDF varsa SHA-256 eşleşir (yoksa atlanır)
- [x] `kind: real` minimumları zorunlu
- [x] İşaret testleri: Ollama erişilebilirken çalışır, Tesseract yokken atlanır

## Tamamlanma Kriterleri

- [x] Sentetik set üretilmiş ve beklenen özellikleri doğrulanmış (şifreli olan açılmıyor, bozuk olan hata veriyor, taranmışın metin katmanı boş)
- [ ] Gerçek makaleler ve 3 referans YAML hazır (**elle yapılacak**; Faz 03 başlamadan en azından PDF'lerin toplanması önerilir, referans YAML'ları Faz 14'ten önce tamamlanmalı)
- [x] `requires_tesseract` / `requires_ollama` işaretleri çalışıyor
- [x] `pytest` yeşil (58 geçti, 1 atlandı — Tesseract kurulu değil)
