# Faz 10 — Sağlamlık, Resume, Paralellik ve Ayrıntılı Günlükleme

**İlgili bölümler:** §9.3–§9.5, §24 (çıkış kodları), §27, §28, §29
**Önkoşul:** Faz 09
**Tahmini büyüklük:** Orta–Büyük

## Amaç

Önceki fazlarda temel hali kurulan hata, durum ve atlama mantığını gereksinimdeki tam kurallara getirmek; uzun batch'lerin kesintiye dayanıklı, paralel ve izlenebilir çalışmasını sağlamak. Bu faz §37 **Aşama 4**'tür.

## Görevler

### 1. Hata politikası tablosu (§28)

Tek bir merkezde (`src/error_policy.py`) istisna → davranış eşlemesi:

- [ ] Bozuk / şifreli PDF → `failed(parse)`, devam
- [ ] Tek sayfa okuma hatası → uyarı, devam
- [ ] Ollama erişilemiyor (retry sonrası) → belge `failed`, **batch durur** (`FatalBatchError`), state kaydedilir
- [ ] Görsel model timeout → bölge `[unclear]` + uyarı
- [ ] Metin model timeout → `failed(llm)`
- [ ] Görsel işleme hatası → `[unclear]`, `completed_with_warnings`
- [ ] JSON/şema hatası (retry sonrası) → `failed(validation)`
- [ ] Disk yazma hatası → `failed(write)`; **ardışık** 2. yazma hatası → batch durur
- [ ] Yetersiz disk → her belgeden önce `shutil.disk_usage` kontrolü; yetersizse batch durur
- [ ] Her hata kaydı: kaynak dosya, aşama, hata türü, mesaj, deneme numarası (§28)
- [ ] Batch durduğunda işlenmemiş belgeler `pending` kalır; konsola "yeniden çalıştırınca devam edilecek" mesajı

### 2. Tam atlama kuralı (§9.3)

- [ ] `should_skip(record, sha, plan_hash, output_path)` — dört koşulun hepsi
- [ ] `plan_hash` Faz 08 tanımı (mod + modeller + digest'ler + parser sürümü dahil)
- [ ] Filtre dışı belgeler: bu çalıştırmada `skipped` sayılır (run özeti) ama kalıcı state durumu ezilmez — Faz 02 kararı ile tutarlı olduğunu doğrula
- [ ] Yeniden işlemede önbellekteki geçerli ara dosyalar kullanılır; `A.md` atomik olarak yeniden yazılır
- [ ] Prompt/plan değiştiğinde önceki `prompt_sha256`, `plan_hash`, `output_path`, `processed_at` → `history[]` (§9.3)
- [ ] Skip edilen belgede **hiç model çağrısı yapılmaz** — planlayıcı önbelleği (Faz 08) sayesinde plan için de çağrı yok (§38 kriter 12). Doğrulamak için run başına model çağrı sayacı

### 3. Yeniden başlatma (§9.4)

- [ ] `processing` → `pending` (Faz 02'de yapıldı, entegrasyon testi ekle)
- [ ] `failed` varsayılan olarak denenmez; `--retry-failed` veya `processing.retry_failed: true`
- [ ] `attempts` her denemede artar
- [ ] `--force`: atlama yok, `document.json`/görsel katman/çıkarım önbelleği okunmaz (yazılır)

### 4. Kesinti güvenliği

- [ ] `Ctrl+C` (SIGINT) ve Windows `SIGBREAK`: iptal tokenı set edilir; mevcut model çağrısı bitince veya belge sınırında durulur; ikinci `Ctrl+C` → hemen çık (kilit `atexit` ile bırakılır)
- [ ] Süreç zorla öldürülse bile: tüm yazımlar atomik → yarım dosya yok; başlangıçta `.tmp` artıkları temizlenir; bayat kilit kaldırılır (§38 kriter 15)
- [ ] Kesinti simülasyon testi: alt süreçte batch başlat, N. belgede `kill`, yeniden başlat, sonuçları karşılaştır

### 5. Paralellik (§27)

- [ ] **CPU aşaması:** `ProcessPoolExecutor(max_workers=cpu_workers)` ile `parse_pdf` + OCR + render (saf fonksiyonlar, Faz 03 tasarımı). Worker'lar yalnızca `_cache/<sha>/` altına yazar; state'e yalnızca ana süreç yazar
- [ ] Aynı sha'lı iki belge aynı anda ayrıştırılmaz (sha bazlı tekilleştirme) (§9.5)
- [ ] **Model aşaması:** `ModelCallQueue` (Faz 07), `llm_workers` eşzamanlılığı
- [ ] Boru hattı: CPU havuzu belgeleri önden hazırlar (sınırlı tampon, ör. `cpu_workers × 2`), model aşaması belge sırasıyla tüketir; bir belgenin tüm görsel çağrıları metin çağrılarından önce (§27)
- [ ] Belge sırası: çıktı ve state güncellemeleri deterministik sırayı zorunlu kılmaz ama log okunabilirliği için başlangıç/bitiş olayları belge adıyla loglanır
- [ ] State yazımı sıklığı: her belge sonunda (kilit altında)
- [ ] Windows `spawn` davranışı: `process_papers.py` içinde `if __name__ == "__main__":` koruması; worker'a aktarılan nesneler picklable

### 6. Ayrıntılı günlükleme (§29)

- [ ] Belge başına: başlangıç/bitiş zamanı, süre, sayfa sayısı, sayfa sınıfı dağılımı (`text=12 mixed=2 scanned=1`), OCR/görsel/metin çağrı sayıları, uyarılar, hatalar, sonuç
- [ ] Model çağrısı başına: Faz 07'de kuruldu — tüm alanların (tetikleyici dahil) eksiksiz olduğunu doğrula
- [ ] `tqdm` ilerleme çubuğu: toplam belge, mevcut belge adı, aşama
- [ ] Çalıştırma sonu özeti: toplam, completed, completed_with_warnings, failed, skipped, toplam süre → konsol + log + `processing_state.json → runs[run_id]` (§22.5)
- [ ] Log dosyasında hiçbir PDF içeriği/model yanıtı yok (`log_model_content: false`) — test ile doğrula

### 7. Çıkış kodları (§24)

- [ ] 0: failed yok
- [ ] 1: en az bir `failed` (bu çalıştırmada işlenen belgeler için; önceki çalıştırmadan kalan ve denenmeyen `failed` kayıtlar çıkış kodunu etkilemez — kararı README'ye yaz)
- [ ] 2: preflight/kilit
- [ ] Batch sistem hatasıyla durduysa: 1 (en az bir belge failed) + açıklayıcı mesaj

## Testler

- §38 kriter 12: ikinci çalıştırma → tümü `skipped`, `FakeTextClient`/`FakeVisionClient` çağrı sayısı 0
- §38 kriter 13: yalnızca mtime değişen PDF işlenmez; içerik değişen yeniden işlenir
- §38 kriter 14: prompt değişince `parse` yok, `history` dolu
- §38 kriter 15: kill + restart testi
- §38 kriter 16: eşzamanlı ikinci çalıştırma → 2
- `FakeTextClient` bağlantı hatası → batch durur, kalan belgeler `pending`
- Disk yazma hatası simülasyonu (hedefi salt okunur klasör yap) → `failed(write)`, ikinci hatada batch durur
- `--retry-failed` / `--force` davranışları
- `cpu_workers=4` ile sonuçlar `cpu_workers=1` ile aynı (içerik eşitliği)

## Tamamlanma Kriterleri

- [ ] §38 kriterleri 11–17 ve 24 otomatik testlerle karşılanıyor
- [ ] 20+ PDF'lik bir klasörde Ollama çalışma ortasında kapatıldığında batch güvenle duruyor ve yeniden başlatınca kaldığı yerden devam ediyor (elle test)
- [ ] `pytest` yeşil

> **Kilometre taşı:** Aşama 4 tamamlandı. Etiket: `v0.4-asama4`.
