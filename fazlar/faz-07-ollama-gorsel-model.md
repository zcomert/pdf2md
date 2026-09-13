# Faz 07 — Ollama İstemci Katmanı, Görsel Model ve Çalışma Modları

**İlgili bölümler:** §12.1, §12.3, §13 (3. adım ve kurallar), §14, §17.1 (digest), §19.3, §23, §26 (Ollama/model/GPU satırları), §27, §28 (model satırları), §32.1
**Önkoşul:** Faz 06; Ollama çalışıyor, `minicpm-v4.5:8b` ve `gemma4:latest` kurulu
**Tahmini büyüklük:** Büyük

## Amaç

Tüm model çağrılarının geçeceği ortak, arayüz tabanlı Ollama katmanını kurmak; görsel modeli tablo/formül/şekil/taranmış sayfa işlemede devreye almak ve FAST/BALANCED/FULL modlarını tetikleyici tablosuna göre uygulamak. Bu faz §37 **Aşama 2**'yi tamamlar ve Aşama 3'ün istemci altyapısını hazırlar.

## Modüller

`src/model_clients.py` (arayüzler), `src/ollama_backend.py`, `src/vision_client.py`, `src/llm_client.py` (temel), `src/vision_triggers.py`, `src/evidence_verifier.py` (LaTeX kısmı), `src/preflight.py` (güncelleme)

## Görevler

### 1. Arayüzler — `src/model_clients.py`

§33 son paragrafı: model değişikliği diğer modülleri etkilememeli.

- [ ] `VisionClient` protokolü: `analyze(image: Path, task: VisionTask, context: dict) -> VisionResult`
- [ ] `TextClient` protokolü: `generate(messages, schema: type[BaseModel] | None, options) -> TextResult`
- [ ] `ModelInfo(name, digest, size_bytes)`
- [ ] Testler için `FakeVisionClient`, `FakeTextClient` (kayıtlı yanıt döndüren) — `tests/fakes.py`

### 2. Ollama arka ucu — `src/ollama_backend.py`

- [ ] Endpoint doğrulama: host yalnızca `127.0.0.1`, `localhost`, `::1` (§32.1); aksi halde `PreflightError`
- [ ] `ollama.Client(host=endpoint, timeout=timeout_sec)`
- [ ] `list_models()`, `model_info(name) -> ModelInfo` (digest `ollama.show` / `list` yanıtından)
- [ ] `running_models()` (`ps`) — GPU/VRAM bilgisi için
- [ ] **Tek model çağrı kuyruğu** (§27): `ModelCallQueue` — `llm_workers` kadar eşzamanlılık (`threading.Semaphore`); varsayılan 1
- [ ] Retry: `max_retries`, `retry_backoff_sec` × 2^deneme (üstel), yalnızca bağlantı/timeout/5xx hatalarında
- [ ] Hata sınıflandırması:
  - Bağlantı reddedildi / tüm denemeler bitti → `OllamaUnavailable` (Faz 10'da `FatalBatchError`'a çevrilir)
  - Timeout → `ModelTimeout`
  - Model yok → `ModelNotFound`
- [ ] `keep_alive` her çağrıya geçirilir
- [ ] Her çağrı için log kaydı (§29): model, tetikleyici, sayfa/bölge, giriş boyutu (piksel veya tahmini token), süre, deneme no, hata nedeni
- [ ] `log_model_content: true` değilse prompt/yanıt içeriği loglanmaz
- [ ] Ham yanıtlar `_cache/<sha>/model_raw/<çağrı_id>.json` altına yazılır (§6.2)

### 3. Preflight güncellemesi

- [ ] Ollama endpoint erişilebilir ve loopback → değilse hata (çıkış 2)
- [ ] Metin modeli kurulu → değilse hata + `ollama pull <model>` (§38 kriter 18). *Not:* Varsayılan prompt + metin LLM gerektirmeyen çalıştırmada bu kontrolün hata mı uyarı mı olacağı kararı: belge §26'da koşulsuz hata diyor; öneri — belgeye uy, koşulsuz hata.
- [ ] Görsel modeli kurulu → `fast` modunda veya `vision_required: false` ise uyarı, değilse hata + `ollama pull`
- [ ] GPU bilgisi (`ollama ps` / `nvidia-smi` varsa) → bilgi/uyarı logu
- [ ] Model adları ve digest'ler logga ve çalışma bağlamına (`RunContext.models`) yazılır
- [ ] Mesaj biçimi §26 örneğiyle aynı

### 4. Tetikleyici motoru — `src/vision_triggers.py`

§12.3 tablosu tek bir veri yapısı olarak kodlanır (test edilebilir, kopyala-yapıştır if zinciri değil):

| Tetikleyici kodu | FAST | BALANCED | FULL |
|---|:---:|:---:|:---:|
| `scanned_no_ocr` / `scanned_ocr_failed` | ✓ | ✓ | ✓ |
| `table_inconsistent` | – | ✓ | ✓ |
| `equation_requested` | – | ✓ | ✓ |
| `figure_requested` | – | ✓ | ✓ |
| `reading_order_uncertain` | – | ✓ | ✓ |
| `candidate_full` (tüm adaylar) | – | – | ✓ |
| `page_full_analysis` (mixed/scanned tüm sayfa) | – | – | ✓ |

- [ ] `select_vision_jobs(doc, mode, plan_needs) -> list[VisionJob]`
- [ ] Plan `needs` henüz yok (Faz 08) → varsayılan plan `needs` (hepsi `true`) kullanılır
- [ ] Görsel model yoksa (`vision_required: false`) iş listesi boş + ilgili uyarılar

### 5. Görsel istemci — `src/vision_client.py`

Görev başına ayrı sistem promptu ve **şemalı JSON** yanıt (Ollama `format=<json_schema>`):

- [ ] `table` → `{"header": [...], "rows": [[...]], "merged_cells": [...], "caption": str|null}`; okunamayan hücre `"[unclear]"` — tahmin yasağı promptta açık
- [ ] `equation` → `{"latex": str, "number": str|null}`
- [ ] `figure` → `{"figure_type": "chart|diagram|photo|...", "caption": str|null}` (şekil **yeniden üretilmez**)
- [ ] `page_text` (taranmış/bozuk/okuma sırası belirsiz) → sıralı blok listesi `{type, text, heading_level}`
- [ ] Görsel = Faz 05'teki kırpılmış bölge (tam sayfa yalnızca sayfa görevlerinde)
- [ ] Yanıt parse/şema hatası → ham yanıt `errors/` altına, yeniden deneme, sonunda bölge `[unclear]` + uyarı (§28)
- [ ] Timeout sonrası → bölge `[unclear]` + uyarı (§28)
- [ ] `stats.vision_calls += 1`

### 6. Sonuçların `DocumentModel`'e işlenmesi

- [ ] **Tablo** (§13 kuralı): görselden gelen sayısal hücreler, aynı bölgenin metin katmanındaki sayılarla karşılaştırılır; uyuşmazlıkta metin katmanı değeri kullanılır + `table_value_mismatch` uyarısı
- [ ] **Formül:** `latex`, `source_method: vision`; LaTeX doğrulaması (aşağıda)
- [ ] **Taranmış sayfa (OCR yok):** görsel modelden gelen bloklar `source_method: vision` ile eklenir; hem OCR hem görsel model yoksa `[unreadable_page]`
- [ ] **Okuma sırası belirsiz:** model sırası yalnızca blok **sırasını** belirlemek için kullanılır; metin, metin katmanından alınır (metin eşleşmesiyle)
- [ ] Belgenin tüm görsel çağrıları, metin çağrılarından önce tamamlanır (§27)
- [ ] `document.json` güncellenir ve önbelleğe yazılır. Görsel sonuçlar **mod ve görsel model digest'ine bağlıdır** → önbellek anahtarı: `document.json` temel ayrıştırma + `vision/<mode>_<digest8>.json` katmanı olarak ayrı saklanması önerilir (mod değişince yeniden ayrıştırma yapılmaz, sadece görsel katman)

### 7. LaTeX doğrulama — `src/evidence_verifier.py` (ilk kısım)

§19.3:

- [ ] Süslü parantez dengesi (kaçışlı `\{` hariç)
- [ ] `\left` / `\right` sayısı eşit
- [ ] `\begin{x}` / `\end{x}` yığın eşleşmesi
- [ ] `pylatexenc.latexwalker.LatexWalker(...).get_latex_nodes()` istisnasız çalışıyor mu
- [ ] Geçersiz → `latex_valid: false`, Markdown'da formülün yanına `[latex_unverified]`

### 8. Çalışma modları

- [ ] `--mode` ve config `mode` → `RunContext.mode`
- [ ] Mod, front matter'a ve (Faz 08'de) plan hash'ine yazılır
- [ ] Her görsel çağrı logunda tetikleyici kodu (§23, §38 kriter 24)

### 9. VRAM kontrolü (§27)

- [ ] `llm_workers > 1` ise: boş VRAM (`nvidia-smi --query-gpu=memory.free` varsa) < iki modelin toplam boyutu → `llm_workers = 1` + uyarı

## Testler

- Tetikleyici tablosu: her mod × her tetikleyici kombinasyonu için parametrik test
- Loopback dışı endpoint (`http://192.168.1.10:11434`) → preflight hatası
- `FakeVisionClient` ile: tablo uyuşmazlığında metin katmanı değeri kazanır; parse hatası → `errors/` dosyası + `[unclear]`
- LaTeX doğrulama: `\frac{a}{b}` geçerli, `\frac{a}{b` geçersiz, `\left( x` geçersiz, `\begin{align} \end{matrix}` geçersiz
- `@requires_ollama` entegrasyon: `synthetic_table_equation.pdf` BALANCED modda formüller LaTeX'e çevrilir; FAST modda görsel çağrı yapılmaz (log kontrolü)
- Eksik model adı (`--model-vision olmayan:model`) → çıkış 2 + `ollama pull` mesajı

## Tamamlanma Kriterleri

- [ ] Taranmış PDF, Tesseract devre dışıyken görsel modelle metne dönüşür (§38 kriter 10 tamam)
- [ ] BALANCED modda tutarsız tablolar ve formüller görsel modelle işlenir; FULL modda daha fazla çağrı yapıldığı logdan görülür (§38 kriter 24)
- [ ] Ollama kapalıyken başlatılırsa çıkış kodu 2 ve anlaşılır mesaj
- [ ] `pytest` yeşil (Ollama gerektiren testler işaretli)

> **Kilometre taşı:** Aşama 2 tamamlandı. Etiket: `v0.2-asama2`.
