# Faz 14 — Kabul Testleri, Doğruluk/Performans Ölçümü ve Dokümantasyon

**İlgili bölümler:** §30 (son paragraf), §34.3, §38 (tümü), §39
**Önkoşul:** Faz 13
**Tahmini büyüklük:** Orta

## Amaç

Bu fazın amaçları:

- §38'deki 28 kabul kriterinin ve §41.4'ün tamamının karşılandığını sistematik olarak göstermek
- Doğruluğu ve performansı mod bazında ölçüp raporlamak
- Kurulum ve kullanım dokümantasyonunu tamamlamak

Faz sonunda ilk sürüm (`v1.0`) yayınlanabilir.

## Görevler

### 1. Kabul kriteri izleme matrisi — `tests/acceptance/MATRIX.md`

- [x] §38'deki her kriter (1–28) ve §41.4 (G1–G5) için bir satır: kriter, doğrulama türü, testler, sonuç, not. Son çalıştırma tarihi başlıkta yer alır.
- [x] Önceki fazlarda yazılmış testler matrise eşlendi; eksik kalanlar için `test_acceptance_extra.py` yazıldı.
  - Makine okunur eşleme `tests/acceptance/criteria.py` dosyasındadır.
  - `test_matrix.py` her kriterin eşlendiğini ve eşlenen her testin var olduğunu (AST ile) denetler.

### 2. Uçtan uca kabul test paketi — `tests/acceptance/`

- [x] Kriter 1–28 → **karar:** önceki fazların uçtan uca testleri yeniden yazılmadı. Kriterler bu testlere eşlendi (kopya test bakım yükü getirir). `conftest.py`'deki `pytest_collection_modifyitems` kancası, eşlenen testleri `acceptance` işaretiyle işaretler.
- [x] Eksik testler `test_acceptance_extra.py` içinde yazıldı:
  - yanlış hücreden `verified` tespiti (21)
  - sentetik referansla puanlama (22)
  - tüm JSON çıktılarının şema doğrulaması (23)
  - konsol ve log özeti (26)
  - global site-packages kullanılmaması (27)
  - `.venv` ve önbelleğin çıktıya/git'e girmemesi (28)
- [x] Ollama gerektirenler `requires_ollama` ile işaretli; paket `pytest -m acceptance` ile ayrı çalıştırılabilir.
- [x] **Temiz ortam testi (kriter 27):**
  - Windows'ta yeni klasöre `git clone` yapıldı, §34.3 komutları çalıştırıldı ve `site.getsitepackages()` kontrol edildi.
  - İlk denemede 561/562 test geçti. `not_a_pdf.PDF` fixture'ı `core.autocrlf` ile değiştiği için SHA-256 tutmadı; `.gitattributes` eklendi (`tests/fixtures/** -text`, `*.pdf binary`) ve klonda yeniden doğrulandı.
  - Linux denenmedi.

### 3. Doğruluk ölçümü — `tools/evaluate.py`

- [x] Her referans makale × her mod için ayrı çıktı klasörü. Her modda aynı iki çalıştırma yapılır: varsayılan prompt (tam dönüşüm; `.md` ayrı klasöre kopyalanır) ve sabit sonuç promptu.
- [x] Ölçütler:
  - **Künye:** başlık için normalize tam eşleşme, yazarlar için referans yazar oranı; yıl, dergi ve DOI
  - **Tablo hücreleri:** yapılandırılmış tablodaki hücre eşleşmesi + hücre metninin çıktıda bulunması (yapısız tablolar dahil)
  - **Formüller:** normalize LaTeX tam eşleşme (aralık komutları, `\left`/`\right` kaldırılarak), benzerlik ≥ 0,9 oranı, `latex_valid` oranı
  - **Sayısal sonuçlar:**
    - geri çağırma: referans sonucun model + metrik + değer olarak `verified` bulunması
    - referans tablo hücresiyle doğrulanan sonuç sayısı
    - **referans tablo hücresiyle çelişen `verified` sayısı** (kriter 21). Satır model adına göre (tek en iyi kelime jaccard'ı) seçilir. Model adı birden çok satıra uyuyorsa değer bu satırların hiçbirinin sütununda bulunmuyorsa çelişki sayılır.
- [x] Çıktı: `reports/accuracy_20260914.md` ve `.json`

### 4. Performans ölçümü — `tools/benchmark.py`

- [x] Test setinde mod başına: sayfa başına ortalama süre, belge başına görsel/metin çağrı sayısı, OCR sayfa sayısı
- [x] Soğuk (`--force`, varsayılan prompt) ve sıcak (farklı prompt, ayrıştırma ve görsel sonuçlar önbellekten) çalıştırma ayrı raporlanır
- [x] Donanım bilgisi (CPU, GPU, VRAM, Ollama sürümü, model digest'leri)
- [x] Çıktı: `reports/performance_20260914.md`

### 5. Gereksinim belgesinin güncellenmesi

- [x] **Karar (Faz 11'deki kullanıcı kararı):** `gereksinim-analizi.md` değiştirilmedi. Faz boyunca alınan tüm kararlar ve sapmalar gereksinim bölümlerine göre `docs/gereksinim-guncellemeleri.md` dosyasında toplandı; belgenin bir sonraki sürümüne işlenmek üzere kullanıcı onayı bekliyor.
- [x] Kriter 22 eşik önerileri README'nin "Doğruluk" bölümünde ve `docs/gereksinim-guncellemeleri.md` §38'de
- [ ] Gereksinim belgesine işleme ve belge sürüm notu — kullanıcı onayından sonra

### 6. README.md

- [x] Proje amacı ve özellik özeti
- [x] Windows kurulumu: venv, pip, isteğe bağlı paketler, Tesseract (UB Mannheim, `tur`, `tesseract_path`), `ollama pull`
- [x] Linux/macOS kurulumu (apt/brew). Bu platformların test edilmediği belirtildi.
- [x] Hızlı başlangıç: tam dönüşüm, belge çıkarımı, §40 komutu, GUI
- [x] CLI seçenek tablosu, çıkış kodları, yapılandırma anahtarları (`config.example.yaml`)
- [x] Çıktı yapısı ve `_cache`'in anlamı
- [x] Modlar ve kullanım durumları
- [x] Prompt ipuçları ve `--plan-only`
- [x] Güvenilirlik işaretleri: `not_found`, `[unclear]`, `[unverified]`, `[source_not_found]`, `[latex_unverified]`, `[latex_unavailable]`, `[table_structure_unavailable]`, `[figure_unavailable]`, `[unreadable_page]`
- [x] Resume, `--retry-failed`, `--force`, `pending` politikası
- [x] GUI kullanımı. **Karar:** ekran görüntüleri depoya eklenmedi; Faz 13'te alınan görüntüler kullanıcının yerel yollarını gösteriyor. Adımlar metinle anlatıldı.
- [x] Doğruluk ve performans özet tabloları
- [x] Sorun giderme: Ollama, model, Tesseract, zaman aşımı, kilit, `LongPathsEnabled`, CSV kodlaması, tablo yapısı, sürekli `failed`
- [x] Gizlilik: loopback zorunluluğu, model içeriğinin loglanmaması

### 7. Sürüm hazırlığı

- [x] `requirements.txt` sabit sürümleri temiz klonda doğrulandı (kriter 27)
- [x] `src/__init__.py` → `__version__ = "1.0.0"`; `PARSER_VERSION` değişmedi
- [x] `CHANGELOG.md`
- [ ] Etiket `v1.0.0` — kullanıcı istediğinde

### 8. Gelecek aşama notu (§39)

- [x] `docs/future-rag.md` içeriği:
  - hazır girdiler
  - blok bazlı parça stratejisi
  - `nomic-embed-text` ve önbellek anahtarı
  - `qdrant-client` ve `faiss-cpu` karşılaştırması, değerlendirme ölçütleri
  - taşınacak güvenilirlik kuralları, açık sorular

## Doğrulayıcı Değişikliği: Tablo Sütun Kuralı (kriter 21)

İlk doğruluk ölçümünde BALANCED modunda bir çelişkili `verified` sonuç bulundu. Vekkot Tablo 9'da "MFCC+Stat-Bi-LSTM / Ambiguous F score = 92%" doğrulanmış sayılmıştı; oysa doğru değer 91, 92 ise aynı satırın Recall sütunundaki değerdi. Faz 09'dan beri bilinen "`verified` hücre düzeyinde değil" sınırlaması yalnızca belgelenmek yerine düzeltildi:

- **Sütun etiketleri:** `SourceIndex.table_cell_for` çok düzeyli başlıkları düzleştirir.
  - İlk başlık satırındaki boş hücre soldaki başlığı sürdürür (colspan).
  - İlk hücresi boş olan ve sayı içermeyen sonraki satırlar alt başlık olarak eklenir ("F score" + "Ambiguous").
- **Sütun eşleştirme:** metrik adı ile sütun etiketi arasında kelime jaccard'ı hesaplanır. Sonuç ≥ 0,5 ve tek en iyi sütun olmalıdır. "F1-Score", "F score" ve "F-measure" eşdeğer sayılır.
- **Satır seçimi:** önce model adıyla tam eşleşen satırlar alınır. Yoksa adı içeren satırların tümü alınır: ikinci ölçümde model "MFCC+Stat-Bi-LSTM" yerine "Bi-LSTM" yazdı ve ad üç satıra uydu. Değer, bu satırların belirlenen sütunundaki hücrelerden birinde bulunmalıdır.
- **Geri dönüş:** sütun belirlenemezse Faz 09 satır kuralı geçerlidir.
- `VERIFIER_VERSION = "3"`: eski çıkarım önbellekleri yeniden doğrulanmak üzere geçersiz sayılır.
- Aynı "birden çok satır" mantığı değerlendiricinin `table_cell_verdict` fonksiyonuna da eklendi. Önceki kural bu durumu "belirsiz" sayıp çelişkiyi raporlamıyordu.

## Gerçek Set Sonuçları

### Doğruluk (`reports/accuracy_20260914.md`, 3 referans makale)

| Ölçüt | FAST | BALANCED | FULL |
|---|---:|---:|---:|
| Künye (5 alan) | 1.0 | 1.0 | 1.0 |
| Tablo hücreleri (yapılandırılmış) | 0 | 0,661 | 0,661 |
| Tablo hücre metni çıktıda | 0,852 | 0,847 | 0,847 |
| Formül tam eşleşme / benzerlik ≥ 0,9 | 0 / 0 | 0,231 / 0,769 | 0,231 / 0,769 |
| LaTeX geçerli | — | 1.0 | 1.0 |
| Sonuç geri çağırma (`verified`) | 0,15 | 0,167 | 0,042 |
| Çelişen `verified` | 0 | 0 | 0 |

- Sütun kuralından önceki ölçümde BALANCED çelişen `verified` = 1 idi. Kuraldan sonra aynı değer (`Bi-LSTM / F1-Score (Ambiguous) = 92%`) `unverified` olarak işaretlendi.
- **Geri çağırma düşük ve değişken:** aynı prompt ve modelle çalıştırmalar arasında FULL için 0,25 → 0,04 aralığında değişti. Gemma "tüm sonuçları" istense de az sayıda sonuç çıkarıyor, model adını kısaltıyor ve zaman zaman belgede olmayan blok kimliği veriyor (`source_not_found`). Eşik önerilmedi.
- Referans tablo hücresiyle doğrulanan sonuç sayısı her modda 0. Model adları referans satırlarına tek anlamlı eşleşmedi ("Bi-LSTM", "bi-LSTM"). Değerlendirici bu durumda "belirsiz" der; bu sayı çıkarım kalitesinin bir göstergesidir, puanlayıcı hatası değildir (hata ayıklama betiğiyle doğrulandı).

### Performans (`reports/performance_20260914.md`, 9 gerçek makale)

| Ölçüt | FAST soğuk | FAST sıcak | BALANCED soğuk | BALANCED sıcak | FULL soğuk | FULL sıcak |
|---|---:|---:|---:|---:|---:|---:|
| Toplam süre (9 makale, 132 sayfa) | 111 sn | 514 sn | 626 sn | 574 sn | 890 sn | 568 sn |
| Sayfa başına süre | 0,83 sn | 3,82 sn | 4,73 sn | 4,29 sn | 6,74 sn | 4,24 sn |
| Belge başına görsel çağrı | 0 | 0 | 7,1 | 1,1 | 14,3 | 1,6 |
| Belge başına metin çağrısı | 1,0 | 2,1 | 1,0 | 2,1 | 1,0 | 2,1 |
| OCR sayfası (toplam) | 6 | 6 | 6 | 6 | 6 | 6 |

- Tüm çalıştırmalarda 9/9 belge tamamlandı, başarısız belge yok. Sıcak çalıştırmalarda 4–6 belge `completed_with_warnings` (prompt cevabında `not_found` / `[unverified]`).
- Soğukta tek metin çağrısı künye LLM adımıdır (Faz 11). Sıcakta çağrılar planlayıcı (1), belge başına çıkarım ve gerektiğinde parça bölme.
- Sıcak BALANCED/FULL'da 10/14 görsel çağrı: çıkarım planının istediği içerik, tam dönüşümün tetikleyicilerinden farklı olduğu için görsel modele gitti.
- FAST soğuk en hızlısı (0,83 sn/sayfa); FULL soğuk BALANCED'dan yaklaşık %42 daha yavaş.
- Ölçüm sırasında GPU'da yaklaşık 16 GB model belleği kullanılıyordu (8 GB boş).

## Sınırlamalar

- **Referans veri taslak:** `tests/fixtures/reference/{polle_meta,pokorny_vocdoc,vekkot_continuous}.yaml` pipeline çıktısı kullanılmadan, PDF metni ve sayfa görüntülerinden Claude tarafından hazırlandı. Kullanıcı onayı bekliyor. Çok düzeyli tablo başlıkları "Ölçüt Sınıf" biçiminde düzleştirildi.
- **§38.1 test seti eksikleri:** 4 yerine 1 tek sütunlu gerçek makale; 0 gerçek taranmış PDF (sentetik taranmış PDF ve metni vektör çizilmiş Shilaskar makalesi kullanıldı).
- Kriter 22 eşikleri öneri durumunda.
- **Elle doğrulama bekleyenler:**
  - CSV'nin Excel'de açılması (kriter 25)
  - GUI dosya seçme diyaloğu (G1)
  - `os.startfile` (G3)
- Linux/macOS kurulumu denenmedi.
- Sütun kuralı yalnızca metrik adı başlıkla tek anlamlı eşleşiyorsa uygulanır. Başlığı olmayan veya metriği satırda veren (transpoze) tablolarda doğrulama satır düzeyinde kalır.
- Doğruluk ölçümü yalnızca 3 makale ve tek çalıştırmadır; model çıktısının değişkenliği nedeniyle sonuç ölçütleri güvenilir bir ortalama değildir.

## Testler

- `tests/test_extraction.py::test_table_value_must_be_in_metric_column_with_multilevel_header` — Vekkot benzeri iki düzeyli başlık:
  - yanlış sütundaki 92 → `unverified`, 91 → `verified`
  - belirsiz sütun → satır kuralı
  - "Bi-LSTM" iki satıra uyar: 92 → `unverified`, 91 → `verified`
- `tests/acceptance/test_acceptance_extra.py` — 6 test (yukarıda). Değerlendirici testine belirsiz satır durumları eklendi.
- `tests/acceptance/test_matrix.py` — eşleme bütünlüğü
- `tests/test_fixtures.py` — gerçek referans dosyaları eklenince sentetik referans testi dosya adıyla seçilecek şekilde düzeltildi
- Çalıştırmalar:
  - `pytest -m "not requires_ollama"`: 575 geçti
  - `pytest -m requires_ollama`: 10 geçti (gerçek Gemma/MiniCPM-V, 105 sn)
  - `pytest -m acceptance`: 68 geçti

## Tamamlanma Kriterleri

- [x] `MATRIX.md`'deki tüm satırlar karşılandı. ⚠ satırlar (25, G1) belirtilen elle doğrulamayı bekliyor.
- [x] Doğruluk ve performans raporları üretildi ve README'de özetlendi. Eşikler kullanıcı onayı bekliyor.
- [x] Temiz klonla README/§34.3 adımlarıyla kurulum Windows'ta başarılı
- [ ] `v1.0.0` etiketi — kullanıcı istediğinde
