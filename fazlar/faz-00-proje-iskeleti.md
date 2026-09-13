# Faz 00 — Proje İskeleti ve Ortam

**İlgili bölümler:** §24, §25, §29, §33, §34, §35
**Önkoşul:** Python 3.11+ kurulu, git deposu mevcut
**Tahmini büyüklük:** Küçük

## Amaç

Sonraki tüm fazların üzerine inşa edileceği proje yapısını, sanal ortamı, yapılandırma şemasını, loglama altyapısını ve CLI iskeletini kurmak. Bu fazın sonunda uygulama çalışır, argümanları ve config'i doğrular ama PDF işlemez.

## Görevler

### 1. Ortam ve depo

- [x] `python -m venv .venv` ile sanal ortam oluştur
- [x] `.gitignore`: `.venv/`, `__pycache__/`, `.pytest_cache/`, `*.pyc`, `tests/output/`, `tests/_tmp/`, `*_output/`
- [x] `requirements.txt`: `pymupdf`, `ollama`, `pydantic`, `pyyaml`, `pandas`, `tqdm`, `pillow`, `pylatexenc`
- [x] `requirements-optional.txt` (veya README'de not): `openpyxl`, `rich`
- [x] `requirements-dev.txt`: `-r requirements.txt` + `pytest`
- [x] Paketleri kurduktan sonra sabit sürümleri (`==`) `requirements.txt`'e yaz (§34.2)

### 2. Klasör yapısı

```text
pdf2md/
├── process_papers.py          # giriş noktası: from src.cli import main; sys.exit(main())
├── config.example.yaml        # §25'teki örnek, yorumlu
├── requirements.txt
├── requirements-dev.txt
├── requirements-optional.txt
├── src/
│   ├── __init__.py            # __version__, PARSER_VERSION sabitleri
│   ├── cli.py
│   ├── config.py
│   ├── logger.py
│   └── errors.py              # ortak istisna sınıfları (aşağıda)
└── tests/
    ├── conftest.py
    ├── test_cli.py
    ├── test_config.py
    ├── test_errors.py
    └── test_logger.py
```

§33'teki diğer modüller ilgili fazlarda eklenir. Boş dosya olarak şimdiden açmaya gerek yoktur.

### 3. `src/errors.py`

Hata aşamaları (§22.2 `error_stage`) ve sistem geneli/belge özgü ayrımı (§28) için baştan ortak tipler:

- `ErrorStage` enum: `discovery`, `parse`, `ocr`, `vision`, `llm`, `validation`, `write`
- `PipelineError(stage, message)` — ortak taban; `stage` enum veya string olarak verilebilir
- `DocumentError(stage, message)` — yalnızca o belgeyi başarısız yapar
- `FatalBatchError(stage, message)` — batch'i durdurur (Ollama kapalı, disk dolu). **`DocumentError`'dan türemez**, aksi halde `except DocumentError` onu yutar ve batch durmaz
- `PreflightError(message, hint)` — çıkış kodu 2

### 4. `src/config.py`

- §25'teki tüm anahtarlar için iç içe Pydantic modelleri (`OllamaConfig`, `ModelsConfig`, `PdfConfig`, `OcrConfig`, `ProcessingConfig`, `OutputConfig`, `SummaryConfig`, `LoggingConfig`, `AppConfig`)
- Tüm modellerde `model_config = ConfigDict(extra="forbid")` → bilinmeyen anahtar hata verir
- Değer doğrulamaları: `mode ∈ {fast, balanced, full}`, `render_dpi ∈ [150, 400]`, oranlar `[0, 1]`, worker sayıları ≥ 1, `scope ∈ {auto, document, collection}`
- `load_config(path | None) -> AppConfig`: YAML oku, doğrula
- `merge_cli(config, args) -> AppConfig`: öncelik **CLI > config.yaml > varsayılan** (§24). İç içe alanlar dahil (`--dpi`→`pdf.render_dpi`, `--model-text`→`models.text`, `--model-vision`→`models.vision`, `--cpu-workers`→`processing.cpu_workers`, `--retry-failed`→`processing.retry_failed`, `--log-level`→`logging.level`); sonuç `model_validate` ile **yeniden doğrulanır** (`model_copy(update=...)` doğrulama yapmaz)
- `--config` verilmemişse `./config.yaml` varsa kullanılır, yoksa varsayılanlar. `--config` açıkça verilmiş ama dosya yoksa hata
- `--force`, `--plan-only`, `--collection-name`, `--collection-output` §25'te config anahtarı olmadığı için çalışma seçeneği olarak `args` üzerinde kalır
- Config hataları `PreflightError`'a çevrilir, alan yolu ile okunabilir mesaj verilir

### 5. `src/cli.py`

- `argparse` ile §24 tablosundaki tüm seçenekler (henüz kullanılmayanlar dahil) tanımlanır
- Giriş hem konumsal hem `--input` olarak kabul edilir; ikisi birden verilirse hata
- `--prompt` ve `--prompt-file` birlikte verilebilir ama öncelik §10.1'e göre (`--prompt` önceliklidir); ikisi birden verilirse uyarı loglanır
- `--include` tekrarlanabilir (`action="append"`)
- Giriş zorunlu: CLI'dan veya config `input_dir`'den gelmezse çıkış kodu 2
- `main()` şimdilik: argümanları ayrıştır → config yükle/birleştir → konsol logger'ı kur → etkin config'i DEBUG seviyesinde logla → çık
- Yalnızca `PreflightError` çıkış kodu 2'ye çevrilir; beklenmeyen istisnalar gizlenmez
- Konsol akışları UTF-8'e ayarlanır (Türkçe karakterler)
- Çıkış kodları sabitleri: `EXIT_OK=0`, `EXIT_DOC_FAILED=1`, `EXIT_PREFLIGHT=2`

### 6. `src/logger.py`

- `setup_logging(output_dir=None, level, run_id) -> Logger` — varsayılan olarak yalnızca konsol; tekrar çağrılınca handler çoğalmaz, `propagate = False`
- `add_file_handler(output_dir, run_id, level)` — kilit alındıktan sonra çağrılır
- `run_id` biçimi: `YYYYMMDD-HHMMSS` (§9.2 `last_run_id`); log dosya adı aynı `run_id`'den türetilir
- Dosya: `<output>/logs/process_<YYYY-MM-DD_HHMMSS>.log`, UTF-8
- Konsol handler'ı WARNING ve üstü; dosya handler'ı yapılandırılan seviye
- `tqdm` ile uyumlu konsol çıktısı için `tqdm.write` tabanlı handler
- Çıktı klasörü henüz bilinmiyorsa (preflight öncesi) yalnızca konsol; dosya handler'ı sonra eklenebilmeli

> Not: Çıktı klasörü kilit alınmadan önce oluşturulmamalı. Log dosyası kilit alındıktan sonra açılır (Faz 02).

## İleriye Dönük Tasarım

- `PARSER_VERSION` sabiti plan hash'ine ve `document.json` geçerliliğine girecek (Faz 03, 08). Ayrıştırma mantığı değiştikçe artırılacak.
- Config nesnesi uygulama boyunca değişmez (immutable/`frozen`) tutulursa worker süreçlerine güvenle aktarılabilir (Faz 10).

## Testler

- `test_config.py`
  - Varsayılan config geçerli; `config.example.yaml` geçerli
  - Bilinmeyen anahtar → `ValidationError`
  - `render_dpi: 500` → hata
  - CLI değeri config değerini ezer (`--mode fast` vs `mode: full`), iç içe alanlar dahil
  - Verilmeyen CLI bayrakları config değerini ezmez
  - Geçersiz CLI değeri (`--dpi 999`) doğrulanır
  - Açıkça verilen olmayan config → hata; varsayılan `./config.yaml` isteğe bağlı
  - Liste YAML, bozuk YAML, bilinmeyen iç anahtar → hata
- `test_cli.py`
  - Konumsal ve `--input` birlikte → hata
  - `--include` birden fazla kez verilebilir
  - `--help` tüm §24 seçeneklerini içerir
  - Giriş yok → çıkış 2; giriş config'ten gelebilir
  - Geçersiz config → çıkış 2
  - Geçerli çalıştırma çıktı klasörü oluşturmaz
  - `--prompt` + `--prompt-file` uyarısı `--prompt` önceliğini belirtir
- `test_errors.py` — `FatalBatchError` `except DocumentError` ile yakalanmaz; string aşama kabul edilir
- `test_logger.py` — `run_id`/dosya adı biçimi, yalnızca konsol kurulumu dosya yazmaz, handler çoğalmaz, UTF-8 dosya log'u

## Tamamlanma Kriterleri

- [x] `.venv\Scripts\python.exe -m pip install -r requirements-dev.txt` temiz ortamda çalışır
- [x] `.venv\Scripts\python.exe process_papers.py --help` tüm §24 seçeneklerini gösterir
- [x] Geçersiz `config.yaml` anlaşılır hata mesajıyla sonlanır
- [x] `pytest` yeşil (32 test geçti)
- [x] `.venv` ve cache dosyaları `git status`'ta görünmez (§38 kriter 28)
