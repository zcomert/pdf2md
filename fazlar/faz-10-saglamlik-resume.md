# Faz 10 — Sağlamlık, Resume, Paralellik ve Ayrıntılı Günlükleme

**İlgili bölümler:** §9.3–§9.5, §24 (çıkış kodları), §27, §28, §29
**Önkoşul:** Faz 09
**Tahmini büyüklük:** Orta–Büyük

## Amaç

Önceki fazlarda temel hali kurulan hata, durum ve atlama mantığını gereksinimdeki tam kurallara getirmek; uzun batch'lerin kesintiye dayanıklı, paralel ve izlenebilir çalışmasını sağlamak. Bu faz §37 **Aşama 4**'tür.

## Modüller

`src/error_policy.py`, `src/parse_pool.py` (yeni); `src/errors.py` (hata türü, pickle), `src/batch_processor.py`, `src/cli.py` (SIGBREAK), `src/schemas.py` (`DocumentState.error_type`), `src/pdf_parser.py` ve `src/llm_extractor.py` (hata türleri); `tests/kill_target.py`

## Görevler

### 1. Hata politikası tablosu (§28) — `src/error_policy.py`

Modül başındaki tablo ve `classify(exc, stage)` tek merkez; `BatchProcessor._process` yalnızca sonucu uygular.

- [x] Bozuk / şifreli PDF → `failed(parse)` (`corrupt_pdf`, `encrypted_pdf`), devam
- [x] Tek sayfa okuma hatası → `parse_error` uyarısı, devam (Faz 03)
- [x] Model servisi erişilemiyor (retry sonrası) → **batch durur**, state kaydedilir (`model_unavailable`)
- [x] Görsel model timeout → bölge işaretli + uyarı (Faz 07, belge hatası değil)
- [x] Metin model timeout → `failed(llm)` (`model_timeout`)
- [x] Görsel işleme hatası → işaretli, `completed_with_warnings` (Faz 07)
- [x] JSON/şema hatası (retry sonrası) → `failed(validation)` (`invalid_model_response`)
- [x] Disk yazma hatası → `failed(write)` (`write_error`); **art arda** ikinci yazma hatası → batch durur (`repeated_write_error`); başarılı veya farklı türde sonuç sayacı sıfırlar
- [x] Disk dolu (`ENOSPC`) → batch hemen durur (`disk_full`)
- [x] Yetersiz disk → her belgeden önce `shutil.disk_usage` ile `processing.min_free_disk_mb` kontrolü; yetersizse belgeye dokunmadan batch durur (`insufficient_disk`)
- [x] Hata kaydı: state'te `error_stage`, `error_type`, `error`, `attempts`; logda `Başarısız [aşama/tür]: dosya (deneme n) — mesaj` (§28)
- [x] Batch durduğunda işlenen belge ve işlenmemiş belgeler `pending`; konsola "yeniden çalıştırınca kaldığı yerden devam edilir"
- [x] Beklenmeyen istisna → o anki aşamada `failed` (`unexpected_error`), yığın izi loga

**Karar (§28'den sapma, Faz 07'den):** Model servisi kapanınca ve disk dolunca belge `failed` değil `pending` bırakılır. `failed` belgeler `--retry-failed` olmadan denenmediği için, sorun giderilince belge sessizce atlanırdı. §28 metnine not düşülmeli.

### 2. Tam atlama kuralı (§9.3)

- [x] `decide(record, plan_hash, output_file, retry_failed, force)` — durum tamamlanmış + plan hash aynı + çıktı mevcut ve boş değil; SHA değişimi keşifte `pending` yapar (Faz 02/08)
- [x] `plan_hash` Faz 08 tanımı (mod, modeller, digest'ler, ayrıştırıcı sürümü)
- [x] Filtre dışı belgeler: çalıştırma özetinde ayrı `excluded_by_filter` sayacı, kalıcı durum ezilmez (Faz 02 kararı; `test_filtered_out_records_are_untouched`). §9.1'deki "filtre dışında kaldığı için skipped" ifadesi özet satırında "filtre dışı N" olarak gösterilir
- [x] Yeniden işlemede geçerli önbellek (ayrıştırma, görsel, çıkarım) kullanılır; `A.md` atomik yeniden yazılır
- [x] Plan değişince önceki kayıt `history[]`'ye (Faz 04/08)
- [x] Atlanan belgede hiç model çağrısı yok; plan önbellekten — FULL modda taranmış sayfa ve adaylarla ikinci çalıştırmada çağrı sayısı değişmez (§38 kriter 12)

### 3. Yeniden başlatma (§9.4)

- [x] `processing` → `pending` (kesinti testinde uçtan uca doğrulandı, `recovered_interrupted` özeti)
- [x] `failed` varsayılan olarak denenmez; `--retry-failed` / `processing.retry_failed: true`
- [x] `attempts` her denemede artar (kesinti sonrası 2)
- [x] `--force`: atlama yok, ayrıştırma/görsel/çıkarım önbellekleri okunmaz, yazılır

### 4. Kesinti güvenliği

- [x] `Ctrl+C` ve Windows `Ctrl+Break` (`SIGBREAK`) aynı işleyici: iptal tokenı, güvenli noktada durulur; ikinci sinyal → hemen çık; kilit `atexit` + `finally` ile bırakılır. Paralel worker'lar sinyali yok sayar, iptal kararını ana süreç verir
- [x] Zorla sonlandırma: yazımlar atomik; başlangıçta `.pdf2md.tmp` artıkları silinir; bayat kilit uyarıyla devralınır
- [x] **Kesinti testi** (`tests/kill_target.py`): alt süreç ikinci Markdown'ın geçici dosyasını yazıp yerine koymadan bekler, test süreci öldürür (`TerminateProcess`). Doğrulananlar: geçici dosya kalmış, bir belge `processing`; yeniden başlatınca geçici dosya yok, bayat kilit ve temizlik logda, tüm belgeler `completed`, kesilen belgenin `attempts` = 2, çıktılar temiz bir çalıştırmayla birebir aynı (§38 kriter 15)

### 5. Paralellik (§27) — `src/parse_pool.py`

- [x] **CPU aşaması:** `ProcessPoolExecutor(max_workers=cpu_workers)` ile `parse_pdf` + OCR; worker yalnızca `_cache/<sha>/document.json` yazar, state ve log ana süreçte
- [x] Aynı SHA'lı belgeler bir kez ayrıştırılır (future SHA ile tekilleştirilir)
- [x] Ön hazırlık tamponu `cpu_workers × 2`: işlenecek belgelerin önündekiler havuza verilir; önbellek başlığı (şema, ayrıştırıcı sürümü, ayar hash'i) geçerliyse gönderilmez
- [x] Worker hataları (`DocumentError`) pickle ile ana sürece aynı aşama ve türle taşınır
- [x] `cpu_workers=1` veya tek belge → havuz açılmaz (süreç başlatma maliyeti yok)
- [x] State her belge sonunda yazılır (Faz 02)
- [x] Windows `spawn`: `process_papers.py` `__main__` korumalı; görev argümanları picklable (yol, frozen config, OCR ayarları)

**Karar (model aşaması):** Model aşaması (görsel + metin) belge sırasıyla ana süreçte ilerler; bir belgenin görsel çağrıları metin çağrılarından önce biter (§27). `llm_workers` `ModelCallQueue` ile eşzamanlı çağrı üst sınırıdır; belgeler arası paralel model çağrısı yapılmaz (varsayılan 1, tek GPU'da iki modelin aynı anda çalışması VRAM'i aşar). İleride belge başına model aşaması iş parçacığına alınabilir.

**Gerçek set (9 makale, FAST, önbelleksiz):** `cpu_workers=1` 21,7 sn → `cpu_workers=4` 14,2 sn; 9 Markdown birebir aynı. Kazanç, sıralı kalan görsel çıkarma/yazım adımları ve 9 belgenin azlığıyla sınırlı.

### 6. Ayrıntılı günlükleme (§29)

- [x] Belge başında `Başladı: dosya (i/n)`; sonunda `Belge özeti: dosya — süre, sayfa (text/mixed/scanned), OCR sayfa, görsel çağrı, metin çağrı, uyarı türleri×sayı, durum`
- [x] Model çağrısı başına alanlar (model, görev, tetikleyici, sayfa/bölge, girdi boyutu, süre, deneme, hata) Faz 07/08'de; metin çağrılarında girdi token sayısı
- [x] `tqdm`: toplam belge, belge adı, aşama (Faz 04)
- [x] Çalıştırma sonu özeti konsol + log + `runs[run_id]`
- [x] Logda PDF içeriği ve model yanıtı yok (`log_model_content: false`) — test: paragraf metni ve çıkarılan değer logda geçmez

### 7. Çıkış kodları (§24)

- [x] 0: bu çalıştırmada `failed` yok
- [x] 1: bu çalıştırmada en az bir `failed` (keşifte okunamayan dahil) veya batch sistem hatasıyla durdu (açıklayıcı mesajla)
- [x] 2: preflight / kilit
- [x] 130: iptal (§24 dışı, Faz 04)

**Karar:** Önceki çalıştırmadan kalan ve bu çalıştırmada denenmeyen `failed` kayıtlar çıkış kodunu etkilemez (özet satırında "önceki hata nedeniyle denenmeyen N" olarak görünür). README Faz 14'te yazılacak; karar oraya taşınmalı.

## Testler

- [x] `test_robustness.py` (19):
  - §28 tablosu parametrik (10 durum), art arda yazma hatası sayacı, hataların pickle ile taşınması
  - Yazma hatası (salt okunur hedef yerine `PermissionError` enjeksiyonu; Windows'ta klasör izinleri güvenilir test edilemiyor): ilk iki belge `failed(write/write_error, deneme 1)`, üçüncü `pending`, çıkış 1, log biçimi
  - `ENOSPC` → batch hemen durur, belge `pending`
  - Yetersiz disk ikinci belgeden önce → 1 tamamlandı, 2 `pending`; yer açılınca devam
  - §38 kriter 12: FULL modda ikinci çalıştırmada model çağrısı yok
  - `cpu_workers=3` sonuçları `cpu_workers=1` ile aynı (Markdown, durum, uyarılar, hata türü, ayrıştırma sayaçları); bozuk PDF hatası worker'dan taşınır; kopya PDF bir kez ayrıştırılır
  - Belge özeti logu; PDF içeriği ve model yanıtı logda yok
  - §38 kriter 15: kill + restart
- [x] Önceki fazlardan: kriter 11 (`test_full_conversion_end_to_end`), 13 (`test_mtime_only_change_does_not_reset_status`, `test_changed_pdf_is_regenerated`), 14 (`test_prompt_change_reuses_parse_and_second_run_skips`), 16 (`test_lock_held_by_other_process`), 17 (`input_snapshot`), 24 (`test_mode_controls_vision_calls_and_log_records_triggers`), servis kapanınca durma (`test_model_service_stopping_mid_run_stops_batch`, `test_text_model_unavailable_stops_batch`), `--retry-failed`, `--force`, iptal ve devam
- [x] Test altyapısı: sahte arka ucun model digest'i SHA-256 ile deterministik yapıldı (`hash()` süreç başına rastgele olduğundan alt süreçte plan hash'i değişiyordu)

## Tamamlanma Kriterleri

- [x] §38 kriterleri 11–17 ve 24 otomatik testlerle karşılanıyor
- [ ] 20+ PDF'lik bir klasörde Ollama çalışma ortasında kapatıldığında batch güvenle duruyor ve yeniden başlatınca kaldığı yerden devam ediyor (**elle test, yapılmadı**): gerçek sette 9 PDF var ve Ollama servisini kapatmak kullanıcının ortamını etkiler. Aynı davranış sahte arka uçla (vision ve metin aşamalarında servis kapanması) otomatik test ediliyor; elle test kullanıcı tarafından yapılmalı
- [x] `pytest` yeşil — 504 sahte arka uçla (+ 9 `requires_ollama`)

> **Kilometre taşı:** Aşama 4 tamamlandı. Etiket: `v0.4-asama4`.
