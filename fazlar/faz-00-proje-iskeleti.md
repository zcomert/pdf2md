# Faz 00 — Proje İskeleti ve Ortam

**İlgili bölümler:** §24, §25, §29, §33, §34, §35
**Önkoşul:** Python 3.11+ kurulu, git deposu mevcut
**Tahmini büyüklük:** Küçük

## Amaç

Sonraki tüm fazların üzerine inşa edileceği proje yapısını, sanal ortamı, yapılandırma şemasını, loglama altyapısını ve CLI iskeletini kurmak. Bu fazın sonunda uygulama çalışır, argümanları ve config'i doğrular ama PDF işlemez.

## Görevler

### 1. Ortam ve depo

- [ ] `python -m venv .venv` ile sanal ortam oluştur
- [ ] `.gitignore`: `.venv/`, `__pycache__/`, `.pytest_cache/`, `*.pyc`, `tests/output/`, `tests/_tmp/`, `*_output/`
- [ ] `requirements.txt`: `pymupdf`, `ollama`, `pydantic`, `pyyaml`, `pandas`, `tqdm`, `pillow`, `pylatexenc`
- [ ] `requirements-optional.txt` (veya README'de not): `openpyxl`, `rich`
- [ ] `requirements-dev.txt`: `-r requirements.txt` + `pytest`
- [ ] Paketleri kurduktan sonra `pip freeze` çıktısından **sabit sürümleri** (`==`) `requirements.txt`'e yaz (§34.2)

### 2. Klasör yapısı

```text
pdf2md/
├── process_papers.py          # giriş noktası: from src.cli import main; sys.exit(main())
├── config.example.yaml        # §25'teki örnek, yorumlu
├── requirements.txt
├── requirements-dev.txt
├── src/
│   ├── __init__.py            # __version__, PARSER_VERSION sabitleri
│   ├── cli.py
│   ├── config.py
│   ├── logger.py
│   └── errors.py              # ortak istisna sınıfları (aşağıda)
└── tests/
    ├── conftest.py
    └── test_config.py
```

§33'teki diğer modüller ilgili fazlarda eklenir. Boş dosya olarak şimdiden açmaya gerek yoktur.

### 3. `src/errors.py`

Hata aşamaları (§22.2 `error_stage`) ve sistem geneli/belge özgü ayrımı (§28) için baştan ortak tipler:

- `ErrorStage` enum: `discovery`, `parse`, `ocr`, `vision`, `llm`, `validation`, `write`
- `DocumentError(stage, message)` — yalnızca o belgeyi başarısız yapar
- `FatalBatchError(stage, message)` — batch'i durdurur (Ollama kapalı, disk dolu)
- `PreflightError(message, hint)` — çıkış kodu 2

### 4. `src/config.py`

- §25'teki tüm anahtarlar için iç içe Pydantic modelleri (`OllamaConfig`, `ModelsConfig`, `PdfConfig`, `OcrConfig`, `ProcessingConfig`, `OutputConfig`, `SummaryConfig`, `LoggingConfig`, `AppConfig`)
- Tüm modellerde `model_config = ConfigDict(extra="forbid")` → bilinmeyen anahtar hata verir
- Değer doğrulamaları: `mode ∈ {fast, balanced, full}`, `render_dpi ∈ [150, 400]`, oranlar `[0, 1]`, worker sayıları ≥ 1, `scope ∈ {auto, document, collection}`
- `load_config(path | None) -> AppConfig`: YAML oku, doğrula
- `merge_cli(config, args) -> AppConfig`: öncelik **CLI > config.yaml > varsayılan** (§24)
- `--config` verilmemişse `./config.yaml` varsa kullanılır, yoksa varsayılanlar

### 5. `src/cli.py`

- `argparse` ile §24 tablosundaki tüm seçenekler (henüz kullanılmayanlar dahil) tanımlanır
- Giriş hem konumsal hem `--input` olarak kabul edilir; ikisi birden verilirse hata
- `--prompt` ve `--prompt-file` birlikte verilebilir ama öncelik §10.1'e göre; ikisi birden verilirse uyarı loglanır
- `--include` tekrarlanabilir (`action="append"`)
- `main()` şimdilik: argümanları ayrıştır → config yükle/birleştir → logger kur → etkin config'i DEBUG seviyesinde logla → çık
- Çıkış kodları sabitleri: `EXIT_OK=0`, `EXIT_DOC_FAILED=1`, `EXIT_PREFLIGHT=2`

### 6. `src/logger.py`

- `setup_logging(output_dir, level, run_id) -> Logger`
- `run_id` biçimi: `YYYYMMDD-HHMMSS` (§9.2 `last_run_id`)
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
  - Varsayılan config geçerli
  - Bilinmeyen anahtar → `ValidationError`
  - `render_dpi: 500` → hata
  - CLI değeri config değerini ezer (`--mode fast` vs `mode: full`)
- `test_cli.py`
  - Konumsal ve `--input` birlikte → hata
  - `--include` birden fazla kez verilebilir

## Tamamlanma Kriterleri

- [ ] `.venv\Scripts\python.exe -m pip install -r requirements-dev.txt` temiz ortamda çalışır
- [ ] `.venv\Scripts\python.exe process_papers.py --help` tüm §24 seçeneklerini gösterir
- [ ] Geçersiz `config.yaml` anlaşılır hata mesajıyla sonlanır
- [ ] `pytest` yeşil
- [ ] `.venv` ve cache dosyaları `git status`'ta görünmez (§38 kriter 28)
