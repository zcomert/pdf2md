# Faz 14 — Kabul Testleri, Doğruluk/Performans Ölçümü ve Dokümantasyon

**İlgili bölümler:** §30 (son paragraf), §34.3, §38 (tümü), §39
**Önkoşul:** Faz 13
**Tahmini büyüklük:** Orta

## Amaç

§38'deki 28 kabul kriterinin ve §41.4'ün tamamının karşılandığını sistematik olarak göstermek, doğruluk ve performansı mod bazında ölçüp raporlamak, kurulum ve kullanım dokümantasyonunu tamamlamak. Bu faz sonunda ilk sürüm (`v1.0`) yayınlanabilir.

## Görevler

### 1. Kabul kriteri izleme matrisi — `tests/acceptance/MATRIX.md`

- [ ] §38'deki her kriter (1–28) ve §41.4 (G1–G5) için satır: kriter, doğrulama türü (otomatik / elle), test dosyası ve fonksiyonu, son sonuç, tarih
- [ ] Önceki fazlarda yazılmış testler bu matrise eşlenir; eksik kalanlar için test yazılır

### 2. Uçtan uca kabul test paketi — `tests/acceptance/`

- [ ] `test_functional.py` — kriter 1–10
- [ ] `test_robustness.py` — kriter 11–19 (kill/restart ve eşzamanlı kilit alt süreçle)
- [ ] `test_accuracy.py` — kriter 20–24
- [ ] `test_inventory_env.py` — kriter 25–28
- [ ] Ollama gerektirenler `@requires_ollama`; `pytest -m acceptance` ile ayrı çalıştırılabilir
- [ ] **Temiz ortam testi (kriter 27):** yeni bir klasöre `git clone` → §34.3 komutları → `python -c "import site; print(site.getsitepackages())"` ile global site-packages kullanılmadığının doğrulanması (`python -m venv` varsayılan olarak `include-system-site-packages = false`); Windows ve mümkünse Linux'ta

### 3. Doğruluk ölçümü — `tools/evaluate.py`

Kriter 22: referans veriyle mod bazında ölçüm.

- [ ] Her referans makale × her mod (`fast`, `balanced`, `full`) için çalıştırma (ayrı çıktı klasörleri, aynı prompt)
- [ ] Ölçütler:
  - **Künye:** alan bazında tam eşleşme oranı (başlık için normalize edilmiş eşleşme; yazarlar için küme örtüşmesi)
  - **Tablo hücreleri:** referans tablolardaki hücrelerin normalize eşleşme oranı
  - **Formüller:** LaTeX normalize eşleşme (boşluk ve `\,`/`\!` gibi aralık komutları kaldırılarak) + `latex_valid` oranı; isteğe bağlı olarak `pylatexenc` ile metne çevrilip karşılaştırma
  - **Sayısal sonuçlar:** geri çağırma (referanstaki sonuçların `verified` olarak bulunma oranı) ve **yanlış verified sayısı** (referansta olmayan `verified` değer — kriter 21 için 0 olmalı)
- [ ] Çıktı: `reports/accuracy_<tarih>.md` ve `.json`

### 4. Performans ölçümü — `tools/benchmark.py`

§30 son paragrafı:

- [ ] Test setinde mod başına: sayfa başına ortalama süre, belge başına görsel/metin çağrı sayısı, OCR sayfa sayısı
- [ ] Soğuk (önbelleksiz, `--force`) ve sıcak (prompt değişikliği sonrası) çalıştırma ayrı raporlanır
- [ ] Donanım bilgisi (GPU, VRAM, model digest'leri) rapora eklenir
- [ ] Çıktı: `reports/performance_<tarih>.md`

### 5. Gereksinim belgesinin güncellenmesi

- [ ] Kriter 22: ilk ölçüm sonrası **eşik değerleri** gereksinim belgesine eklenir
- [ ] Fazlar sırasında alınan kararlar (README'deki karar tablosu, `llm.max_retries` anahtarı, künye LLM çağrısı, tek PDF için varsayılan çıktı yolu, çıkış kodu kapsamı, koleksiyon atlama kuralı vb.) belgeye işlenir
- [ ] Belge sürüm notu

### 6. README.md

§34.3 ve §30:

- [ ] Proje amacı ve özellik özeti
- [ ] **Windows kurulumu** — Python 3.11+, venv, pip, Tesseract (UB Mannheim yükleyicisi, PATH, `tur` dil paketi), Ollama kurulumu ve `ollama pull minicpm-v4.5:8b`, `ollama pull gemma4:latest`
- [ ] **Linux/macOS kurulumu** — `apt install tesseract-ocr tesseract-ocr-tur` / `brew install tesseract tesseract-lang`
- [ ] Hızlı başlangıç: §24 örnekleri ve §40 nihai hedef komutu
- [ ] CLI seçenek tablosu, config örneği (`config.example.yaml`'a bağlantı)
- [ ] Çıktı yapısı (§6.2) ve `_cache`'in anlamı
- [ ] Modlar ve ne zaman hangisi
- [ ] Prompt yazma ipuçları ve §21.3 örnekleri; `--plan-only` ile deneme önerisi
- [ ] Güvenilirlik işaretlerinin anlamı: `not_found`, `[unclear]`, `[unverified]`, `[source_not_found]`, `[latex_unverified]`, `[unreadable_page]`
- [ ] Resume, `--retry-failed`, `--force`
- [ ] GUI kullanımı ve ekran görüntüleri
- [ ] **Doğruluk ve performans raporu** özet tabloları (Görev 3–4)
- [ ] Sorun giderme: Ollama erişilemiyor, model yok, Tesseract yok, kilit dosyası, Windows uzun yol sınırı (`LongPathsEnabled`)
- [ ] Gizlilik: tamamen yerel, loopback zorunluluğu

### 7. Sürüm hazırlığı

- [ ] `requirements.txt` sabit sürümleri güncel ve temiz ortamda doğrulanmış
- [ ] `src/__init__.py` → `__version__ = "1.0.0"`, `PARSER_VERSION` son hali
- [ ] `CHANGELOG.md`
- [ ] Etiket `v1.0.0`

### 8. Gelecek aşama notu (§39)

- [ ] `docs/future-rag.md`: `document.json` ve çıkarım dosyalarının embedding için nasıl kullanılacağı, `nomic-embed-text` ile blok bazlı parça stratejisi, `qdrant-client` vs `faiss-cpu` değerlendirme kriterleri. Kod yazılmaz; yalnızca Aşama 6'ya giriş belgesi

## Tamamlanma Kriterleri

- [ ] `MATRIX.md`'deki tüm satırlar ✓ (elle doğrulananlar tarih ve not ile)
- [ ] Doğruluk ve performans raporları üretilmiş, README'ye özetlenmiş, eşikler gereksinim belgesine eklenmiş
- [ ] Temiz makinede README adımlarıyla kurulum başarılı
- [ ] `v1.0.0` etiketi atılmış
