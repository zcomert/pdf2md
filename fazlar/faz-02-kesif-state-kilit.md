# Faz 02 — Keşif, Kimlik, State, Kilit ve Başlangıç Kontrolleri

**İlgili bölümler:** §6.2, §8, §9, §20.1, §26 (Ollama hariç), §32
**Önkoşul:** Faz 00, 01
**Tahmini büyüklük:** Orta

## Amaç

PDF'leri deterministik biçimde bulan, içerik kimliğini hesaplayan, işlem durumunu güvenle saklayan ve aynı çıktı klasöründe eşzamanlı çalışmayı engelleyen altyapıyı kurmak. Bu faz, ileride "yarım dosya kalmaz", "giriş klasörü değişmez" gibi sağlamlık kriterlerinin temelidir.

## Modüller

`src/paths.py`, `src/atomic_io.py`, `src/pdf_discovery.py`, `src/state_manager.py`, `src/schemas.py` (state kısmı), `src/preflight.py`, `src/dependencies.py`

## Görevler

### 1. Yol yardımcıları — `src/paths.py`

- [x] `normalize(path) -> Path` — mutlak, `resolve()` edilmiş
- [x] `input_root(input)` — klasörse kendisi, tek PDF ise PDF'in klasörü (göreli yolların ve "giriş klasörü" kurallarının kökü)
- [x] `default_output_dir(input)` — `D:\papers` → `D:\papers_output`; tek PDF için PDF'in klasörü esas alınır: `D:\papers\a.pdf` → `D:\papers_output`. Sürücü kökü girişinde `--output` istenir
- [x] `is_within(child, parent)` — Windows'ta büyük/küçük harf duyarsız, `D:\ab` ⊄ `D:\a`
- [x] `ensure_under_output(path, output_dir)` — değilse `ValueError` (path traversal, §32.3)
- [x] `safe_filename(name)` / `safe_stem(filename)` — §20.1 kuralları; ayrılmış ad kontrolü ilk noktadan önceki kısma, harf duyarsız uygulanır; boş sonuç `_`
- [x] `document_output_path(rel)` — `<göreli_klasör>/<güvenli_ad>/<güvenli_ad>.md`; klasör bileşenleri de `safe_filename`'den geçer
- [x] `resolve_output_paths(docs, existing)` — normalizasyon sonrası harf duyarsız çakışmada `_<sha8>` (gerekirse `_<sha8>_<n>`) eki

**Uygulamada ortaya çıkan kararlar:**

- **Tek PDF için çıktı klasörü:** İlk plandaki `<pdf_klasörü>/<pdf_klasör_adı>_output`, çıktıyı PDF'in bulunduğu klasörün içine yazar ve §32.2'yi ihlal eder. Klasör girişindeki kuralın aynısı uygulanır; böylece aynı klasördeki tek PDF ile tüm klasör aynı çıktı klasörünü ve state kayıtlarını paylaşır.
- **Çıktı kökündeki ayrılmış adlar:** Giriş kökünde `logs.pdf` veya `_cache/` gibi adlar sistem klasörleriyle (`_cache`, `logs`, `collections`) çakışır. İlk bileşene `_` eklenir (`logs_/logs_.md`).
- **Kararlı çıktı yolları:** State'te kayıtlı `output_path` değerleri önce ayrılır. Sonradan eklenen ve alfabetik olarak önce gelen bir PDF, daha önce işlenmiş belgenin yolunu değiştiremez. (Faz 04 yolları state'e yazarken bunu kullanır.)

### 2. Atomik yazım — `src/atomic_io.py`

- [x] `atomic_write_text(path, text, encoding="utf-8", bom=False)`, `atomic_write_bytes`, `atomic_write_json` (Pydantic modeli veya dict, `ensure_ascii=False`)
- [x] Aynı klasörde `mkstemp` → yaz → `flush` + `os.fsync` → `os.replace`
- [x] Windows `PermissionError` için üstel beklemeyle 5 deneme
- [x] Hata veya kesmede (`BaseException`) geçici dosya silinir
- [x] `cleanup_temp_files(root)` — yalnızca `.pdf2md.tmp` ekli dosyaları siler; kullanıcının `.tmp` dosyalarına dokunmaz (§38 kriter 15)

### 3. Keşif — `src/pdf_discovery.py`

- [x] `discover(input, recursive, include) -> DiscoveryResult(input_root, documents, excluded_by_filter)`
  - Tek dosya: uzantı `.pdf` (harf duyarsız) değilse hata
  - Klasör: `recursive` ise `rglob`, değilse `glob`
  - Sıralama: göreli yola göre (`casefold`, sonra orijinal) alfabetik (§8.1)
- [x] `include` eşleşme kuralları: `/` içermeyen desen dosya adıyla her derinlikte, içeren desen göreli yolun tamamıyla eşleşir; `*` ve `?` klasör ayırıcıyı geçmez, `**` geçer; harf duyarsız; `\` ve `./` normalize edilir
- [x] `DiscoveredPdf`: `relative_path` (posix), `absolute_path`, `size_bytes`, `mtime` (mikrosaniyeli ISO)
- [x] `compute_sha256(path)` — 1 MiB parçalarla
- [x] `resolve_identity(pdf, record) -> (sha256, rehashed)` — §8.2 hızlı ön kontrol
- [x] `sync_with_state(result, state, summary, logger)`:
  - Yeni belge → `pending`
  - İçerik değişti → `pending`, `attempts=0`, hata alanları temizlenir (yeni belge gibi; önceki `failed` durumu yeni içeriği engellemez)
  - Yalnızca boyut/mtime değişti → yalnızca bu alanlar güncellenir, durum korunur
  - Dosya okunamadı → `failed`, `error_stage: discovery`
  - Filtre dışı kalan kayıtlara dokunulmaz; sayısı `RunSummary.excluded_by_filter`'a yazılır
  - Tüm güncellemeler tek `save()` ile yazılır

### 4. State şeması ve yöneticisi — `src/schemas.py`, `src/state_manager.py`

- [x] Pydantic (`extra="forbid"`): `DocumentStatus`, `ModelRef`, `HistoryEntry`, `DocumentState` (§9.2 alanları + `processed_at`, `history`), `CollectionState`, `RunSummary`, `ProcessingState` (`documents`, `collections`, `runs`)
- [x] `StateManager(output_dir)`
  - `load()` — dosya yoksa boş state. Bozuk JSON, uyumsuz `schema_version` veya şema hatası → `PreflightError` (çıkış 2); **dosyanın üzerine yazılmaz** (resume bilgisi kaybolmasın)
  - `save()` — atomik
  - `get(rel)`, `update(rel, save=True, **fields)` — kayıt şemayla yeniden doğrulanır; toplu işlemlerde `save=False`
  - `recover_interrupted()` — `processing` → `pending`, `attempts` korunur (§9.4)
  - `record_run(summary)`
- [x] `threading.RLock` ile thread-safe; state'e yalnızca ana süreç yazar

### 5. Kilit — `OutputLock` (`src/state_manager.py`)

- [x] Karşılıklı dışlama **işletim sistemi dosya kilidiyle**: Windows `msvcrt.locking` (içerikten uzak bir bayt aralığında), diğerleri `fcntl.flock`
- [x] Kilit alınamazsa dosyadaki bilgilerle (`pid`, `hostname`, `started_at`, `run_id`) `PreflightError` → çıkış kodu 2 (§38 kriter 16)
- [x] Kilit alındığında dosyada önceki bir çalıştırmanın bilgisi varsa o çalıştırma kilidi temizlemeden sonlanmıştır: `stale_info` doldurulur ve uyarı loglanır (§9.5)
- [x] Serbest bırakma: context manager, `atexit`; `process_papers.py` Windows `SIGBREAK`'i `KeyboardInterrupt`'a çevirir. Windows'ta kilit bırakılıp dosya silinir; POSIX'te önce silinir, kilit alan süreç dosyanın hâlâ aynı dosya olduğunu doğrular

**Karar:** İlk plandaki PID yaşıyor mu kontrolü yerine işletim sistemi kilidi kullanıldı. PID kontrolü iki sürecin aynı anda bayat kilidi silip yeniden oluşturmasına açıktır ve Windows'ta yeniden kullanılan PID'lerde yanılır. İşletim sistemi kilidi süreç çöktüğünde otomatik bırakılır; dosyadaki bilgi yalnızca mesaj ve bayat kilit uyarısı içindir.

### 6. Başlangıç kontrolleri — `src/preflight.py`, `src/dependencies.py`

§26 tablosunun Ollama, model, Tesseract, GPU **dışındaki** satırları. Her kontrol `CheckResult(name, ok, severity, message, hint)` döndürür.

- [x] Python ≥ 3.11
- [x] Sanal ortam (`sys.prefix != sys.base_prefix`); değilse uyarı ve `.venv\Scripts\python.exe process_papers.py ...` önerisi
- [x] Zorunlu paketler (`importlib.util.find_spec`); eksikse paket adları ve `.venv\Scripts\python.exe -m pip install -r requirements.txt` (§38 kriter 19)
- [x] Config geçerliliği (bilgi olarak raporlanır; hata Faz 00 akışında yakalanır)
- [x] Giriş yolu var, okunabilir, tek dosyaysa PDF
- [x] Çıktı giriş klasörüyle aynı veya içinde değil; çıktı yolu dosya değil (§32.3). Tek PDF'te "giriş klasörü" PDF'in klasörüdür
- [x] Boş disk ≥ `min_free_disk_mb` (çıktı klasörü yoksa var olan en yakın üst klasörde ölçülür)
- [x] `raise_on_errors(results)` — tüm hataları öneriyle birlikte tek mesajda toplar

**Karar:** Paket kontrolü `src/dependencies.py` içinde yalnızca standart kütüphaneyle yazıldı ve `process_papers.py` içinde `src.cli` içe aktarılmadan önce çalışır. Aksi halde `pydantic`/`pyyaml` eksikken uygulama `src.config` içe aktarılırken `ModuleNotFoundError` ile çöker ve anlaşılır mesaj veremez.

### 7. CLI entegrasyonu

- [x] Akış: argüman → config → çıktı yolu → preflight → (`--plan-only` ise burada biter, çıktı klasörü oluşturulmaz) → çıktı klasörü → **kilit** → state yükle → benzersiz `run_id` → log dosyası → geçici dosya temizliği → `recover_interrupted` → keşif + `sync_with_state` → `runs[run_id]` → özet → kilidi bırak
- [x] Konsol özeti: `Keşif: N PDF (yeni, değişen, değişmeyen, okunamayan), filtre dışı M` + state ve log yolları
- [x] Çıkış kodu: okunamayan belge varsa 1, preflight/kilit/state hatası 2, aksi halde 0

**Karar (benzersiz `run_id`):** `run_id` saniye çözünürlüğündedir. Aynı saniyede başlayan iki çalıştırma aynı log dosyasına yazıyor ve `runs` kaydını eziyordu (test sırasında yakalandı). Kilit alındıktan sonra log dosyası veya `runs` içinde çakışma varsa `-2`, `-3` eki verilir (`20260913-143012-2` → `process_2026-09-13_143012-2.log`).

## Testler

- [x] `test_paths.py` — `safe_filename`/`safe_stem` (`CON.pdf`→`_CON`, `a:b?.pdf`→`a_b_`, `"x. "`→`x`, `COM10` ayrılmış değil), ayrılmış çıktı klasörleri, `A?.pdf`/`A_.pdf` çakışması, harf duyarsız çakışma, kayıtlı yolların korunması, aynı sha önekli üçlü çakışma, varsayılan çıktı klasörü (klasör, tek PDF, sürücü kökü), `is_within`, path traversal
- [x] `test_atomic_io.py` — içerik ve üst klasör, BOM, JSON (model/dict), `fsync` ve `replace` hatasında eski dosya korunur ve geçici dosya kalmaz, `PermissionError` yeniden denemesi, yalnızca kendi geçici dosyalarının temizlenmesi
- [x] `test_discovery.py` — recursive açık/kapalı, `.PDF`, deterministik sıra, `include` ve filtre dışı listesi, tek dosya, PDF olmayan/olmayan giriş, `include` eşleşme tablosu, hash ön kontrolü, yeni kayıt, **sadece mtime değişince durum korunur**, içerik değişince `pending`, filtre dışı kayda dokunulmaz, okunamayan dosya `failed(discovery)`, fixture'larda aynı içerik aynı hash
- [x] `test_state_lock.py` — boş state, round-trip, alan doğrulaması, `recover_interrupted`, bozuk/uyumsuz/geçersiz state'in üzerine yazılmaması, ikinci kilit reddi ve bırakınca dosyanın silinmesi, bayat kilidin devralınması, **başka süreçteki kilit**, **öldürülen sürecin kilidinin devralınması**
- [x] `test_preflight.py` — Python sürümü, sanal ortam uyarısı, eksik paket ve kurulum komutu, `bootstrap_check`, giriş kontrolleri, çıktı = giriş / giriş içinde / tek PDF klasörü içinde / dosya, disk, `raise_on_errors`
- [x] `test_cli_discovery.py` — uçtan uca kayıt (11 sentetik PDF `pending` + SHA-256, kilit silinmiş, log var), **giriş klasörü önce/sonra aynı** (§38 kriter 17), ikinci çalıştırmada değişmeyen, varsayılan çıktı klasörü, çıktı giriş içindeyse yazmadan çıkış 2, geçici dosya temizliği, yarıda kalan kaydın kurtarılması, **eşzamanlı çalıştırma çıkış kodu 2** (§38 kriter 16), **`process_papers.py` eksik paketi üçüncü taraf içe aktarımlardan önce bildirir** (§38 kriter 19)
- [x] `tmp_input_copy` artık `real/` klasörünü kopyalamaz (22 MB; sentetik set için tasarlanmıştı)

## Tamamlanma Kriterleri

- [x] `process_papers.py tests/fixtures --recursive` çalıştırıldığında `tests/fixtures_output/processing_state.json` oluşur, tüm PDF'ler (11 sentetik + 9 gerçek) `pending` ve SHA-256 değerleriyle kaydedilir; ikinci çalıştırmada hepsi değişmeyen
- [x] Kilit sürerken ikinci çalıştırma çıkış kodu 2 (başka süreçte tutulan kilitle otomatik test)
- [x] Giriş klasörüne hiçbir dosya yazılmaz (otomatik test)
- [x] `pytest` yeşil (141 geçti, 1 atlandı — Tesseract kurulu değil)
