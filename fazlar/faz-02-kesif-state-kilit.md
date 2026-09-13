# Faz 02 — Keşif, Kimlik, State, Kilit ve Başlangıç Kontrolleri

**İlgili bölümler:** §6.2, §8, §9, §20.1, §26 (Ollama hariç), §32
**Önkoşul:** Faz 00, 01
**Tahmini büyüklük:** Orta

## Amaç

PDF'leri deterministik biçimde bulan, içerik kimliğini hesaplayan, işlem durumunu güvenle saklayan ve aynı çıktı klasöründe eşzamanlı çalışmayı engelleyen altyapıyı kurmak. Bu faz, ileride "yarım dosya kalmaz", "giriş klasörü değişmez" gibi sağlamlık kriterlerinin temelidir.

## Modüller

`src/paths.py`, `src/atomic_io.py`, `src/pdf_discovery.py`, `src/state_manager.py`, `src/preflight.py`, `src/schemas.py` (state kısmı)

## Görevler

### 1. Yol yardımcıları — `src/paths.py`

- [ ] `normalize(path) -> Path` — mutlak, `resolve()` edilmiş
- [ ] `default_output_dir(input)` — klasörse `<ebeveyn>/<ad>_output`; tek PDF ise `<pdf_klasörü>/<pdf_klasör_adı>_output` (§6.2; tek PDF için davranış belgede açık değil, bu öneri kullanılır ve README'ye yazılır)
- [ ] `is_within(child, parent) -> bool`
- [ ] `ensure_under_output(path, output_dir)` — değilse `ValueError` (path traversal, §32.3)
- [ ] `safe_filename(name) -> str` — §20.1 kuralları: `< > : " / \ | ? *` ve kontrol karakterleri → `_`, sondaki nokta/boşluk silinir, ayrılmış adlara (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`, büyük/küçük harf duyarsız, uzantılı hali dahil) `_` öneki
- [ ] `resolve_output_paths(docs)` — normalizasyon sonrası aynı klasörde çakışma varsa `_<sha8>` eki (§20.1)
- [ ] Belge çıktı yolu: `<output>/<göreli_klasör>/<güvenli_ad>/<güvenli_ad>.md` (§6.2)

### 2. Atomik yazım — `src/atomic_io.py`

- [ ] `atomic_write_text(path, text, encoding="utf-8", bom=False)`
- [ ] `atomic_write_bytes(path, data)`
- [ ] `atomic_write_json(path, obj)` — Pydantic modeli veya dict
- [ ] Uygulama: aynı klasörde `tempfile.NamedTemporaryFile(delete=False)` → yaz → `flush` + `os.fsync` → `os.replace`
- [ ] Windows'ta hedef dosya başka süreç tarafından açıksa `os.replace` `PermissionError` verebilir → kısa bekleme ile birkaç kez dene
- [ ] Hata durumunda geçici dosya silinir
- [ ] Başlangıçta çıktı klasöründe kalmış `*.tmp` artıkları temizlenir (§38 kriter 15)

### 3. Keşif — `src/pdf_discovery.py`

- [ ] `discover(input, recursive, include) -> list[DiscoveredPdf]`
  - Tek dosya: uzantı `.pdf` (harf duyarsız) değilse hata
  - Klasör: `recursive` ise `rglob`, değilse `glob`; uzantı eşleşmesi harf duyarsız
  - `include` glob'ları **göreli yol** üzerinde, `/` ayırıcıyla eşleştirilir (`fatigue/*.pdf`). Windows yolları `as_posix()` ile normalize edilir
  - Sıralama: göreli yola göre alfabetik (§8.1)
- [ ] `DiscoveredPdf`: `relative_path` (posix str), `absolute_path`, `size_bytes`, `mtime`
- [ ] `compute_sha256(path)` — 1 MiB parçalarla, dosya `rb` modunda
- [ ] `resolve_identity(pdf, state_record) -> (sha256, rehashed: bool)` — §8.2 hızlı ön kontrol mantığı:
  - boyut + mtime aynı → kayıtlı hash
  - farklı → yeniden hash; hash aynıysa yalnızca boyut/mtime güncellenir

### 4. State şeması ve yöneticisi — `src/schemas.py`, `src/state_manager.py`

- [ ] Pydantic: `DocumentStatus` enum (§9.1), `ModelRef`, `DocumentState`, `CollectionState` (şimdilik minimal), `RunSummary`, `ProcessingState` (§9.2 örneğinin tüm alanları + `history: list[...]` + `runs: dict[run_id, RunSummary]`)
- [ ] `StateManager(output_dir)`
  - `load()` — dosya yoksa boş state; şema sürümü uyuşmazsa anlaşılır hata
  - `save()` — atomik
  - `get(rel_path)`, `update(rel_path, **fields)` — her güncellemede hemen `save()` (kaba ama güvenli; performans sorun olursa Faz 10'da toplu yazım)
  - `recover_interrupted()` — `processing` → `pending`, `attempts` korunur (§9.4)
- [ ] Thread-safe olmalı (tek `threading.Lock`); state yazımı yalnızca ana süreçten yapılır (worker süreçleri sonucu ana sürece döndürür)

### 5. Kilit — `src/state_manager.py` içinde `OutputLock`

- [ ] `<output>/.lock` dosyası `os.open(..., O_CREAT | O_EXCL)` ile oluşturulur; içerik: `pid`, `hostname`, `started_at`, `run_id` (JSON)
- [ ] Dosya varsa: PID yaşıyor mu kontrol et (Windows: `OpenProcess` / `psutil` kullanmadan `ctypes` ile veya `tasklist`; tercihen küçük bir `pid_alive(pid)` yardımcısı). Yaşamıyorsa uyarıyla sil ve yeniden al (§9.5)
- [ ] Yaşıyorsa `PreflightError` → çıkış kodu 2 (§38 kriter 16)
- [ ] Context manager; `atexit` ve sinyal (`SIGINT`, `SIGBREAK`) ile serbest bırakılır

### 6. Başlangıç kontrolleri — `src/preflight.py`

§26 tablosunun Ollama, model, Tesseract, GPU **dışındaki** satırları. Her kontrol `CheckResult(name, ok, severity: error|warning|info, message, hint)` döndürür; sonuçlar hem loga hem (ileride) GUI'ye verilebilir.

- [ ] Python ≥ 3.11
- [ ] Sanal ortam kontrolü: `sys.prefix != sys.base_prefix`; değilse uyarı ve `.venv\Scripts\python.exe process_papers.py ...` önerisi
- [ ] Zorunlu paket import kontrolü (`importlib.util.find_spec`); eksik paket için `pip install -r requirements.txt` önerisi (§38 kriter 19)
- [ ] Config geçerliliği (Faz 00'da yapılıyor, burada sonuç olarak raporlanır)
- [ ] Giriş yolu var ve okunabilir
- [ ] Çıktı ≠ giriş ve çıktı giriş içinde değil (§32.3)
- [ ] Kilit
- [ ] Boş disk ≥ `min_free_disk_mb` (`shutil.disk_usage`)

Sıralama önemli: kilit alınmadan çıktı klasörüne hiçbir şey yazılmaz. Çıktı klasörü yoksa kilitten hemen önce oluşturulur.

### 7. CLI entegrasyonu

- [ ] `main()`: argüman → config → preflight → kilit → log dosyası → keşif → state yükle, `recover_interrupted` → keşfedilen belgeleri state'e `pending` olarak ekle, hash'le → keşif sonucunu logla → kilidi bırak
- [ ] Keşfedilen ama `include` dışında kalan, state'te zaten kayıtlı belgeler `skipped` yapılmaz; mevcut durumları korunur (filtre dışı = bu çalıştırmada dokunulmaz). Filtre dışı atlama sayısı run özetine yazılır

## Testler

- `safe_filename`: `CON.pdf`→`_CON`, `a:b?.pdf`→`a_b_`, `"x. "`→`x`
- Çakışma: `A?.pdf` ve `A_.pdf` aynı klasörde → ikincisine `_sha8`
- Keşif: `recursive` açık/kapalı, `include` filtresi, `.PDF` uzantısı, deterministik sıra
- Hash ön kontrolü: sadece mtime değişince (içerik aynı) `rehashed=True` ama hash aynı → yeniden işleme işareti yok
- Atomik yazım: yazım ortasında istisna fırlatılınca hedef dosya eski halinde kalır, `.tmp` silinir
- Kilit: ikinci `OutputLock` alınamaz; ölü PID'li kilit uyarıyla kaldırılır
- Preflight: çıktı = giriş → hata; çıktı giriş içinde → hata
- **Giriş klasörü değişmezlik testi:** tüm akış sonrası `input_snapshot` önce/sonra eşit (§38 kriter 17)

## Tamamlanma Kriterleri

- [ ] `process_papers.py tests/fixtures` çalıştırıldığında `tests/fixtures_output/processing_state.json` oluşur, tüm PDF'ler `pending` ve SHA-256 değerleriyle kaydedilir
- [ ] İkinci terminalde aynı komut kilit sürerken çalıştırılırsa çıkış kodu 2
- [ ] Giriş klasörüne hiçbir dosya yazılmaz
- [ ] `pytest` yeşil
