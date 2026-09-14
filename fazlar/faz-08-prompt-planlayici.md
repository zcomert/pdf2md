# Faz 08 — Prompt Planlayıcı ve İşleme Planı

**İlgili bölümler:** §5, §10.1–§10.5, §17.3, §21.2, §9.3 (plan hash tanımı)
**Önkoşul:** Faz 07
**Tahmini büyüklük:** Orta

## Amaç

Kullanıcının doğal dil promptunu, şemayla doğrulanmış bir **işleme planına** dönüştürmek. Plan; kapsamı, istenen alanları, hangi pahalı işlemlerin gerektiğini ve çıktı başlıklarını belirler. Bu faz sonunda `--plan-only` çalışır.

## Modüller

`src/field_catalog.py`, `src/llm_client.py`, `src/prompt_planner.py` (yeni); `src/schemas.py` (plan şeması, `RunSummary.plan_hash/text_llm_calls`), `src/batch_processor.py` (plan hash ile atlama, plan `needs`), `src/cli.py` (`--plan-only`, plan kaydı), `src/ollama_backend.py` ve `src/model_clients.py` (`system` mesajı), `tests/fakes.py`

## Görevler

### 1. Alan kataloğu — `src/field_catalog.py`

- [x] §17.3 tablosu 27 alan: `key` (`dataset.sample_count`), `group`, `label_tr`, `label_en`, `value_type`, `hint_sections` (İngilizce + Türkçe bölüm adları; Faz 09 bölüm seçimi için), `needs`
- [x] Gruplar: `bibliographic`, `research`, `dataset`, `methodology`, `results`, `equations`, `evaluation`
- [x] Katalog dışı istek → `custom.<slug>` (ASCII, Türkçe karakterler dönüştürülür: "Etik Kurul Onayı" → `custom.etik_kurul_onayi`)
- [x] Özel alan `full_conversion` (varsayılan plan; tüm `needs` açık)
- [x] Grup öneksiz adlar tek alana karşılık geliyorsa kabul edilir (`title` → `bibliographic.title`)

### 2. Plan şeması — `src/schemas.py`

- [x] `ProcessingPlan` (§10.2 örneği): `schema_version`, `scope_reason`, `scope`, `targets.include`, `requested_fields`, `custom_fields[{key, description}]`, `needs{tables, equations, figures, full_text}`, `comparison_dimensions`, `output_language` (ISO kodu veya `source`), `output_outline`, `collection_name_suggestion`
- [x] Doğrulayıcılar: alanlar katalogda veya `custom.` önekli; `output_outline` boş olamaz; `custom_fields` anahtarları `requested_fields` içinde olmalı; `scope_reason` zorunlu
- [x] Koleksiyon kapsamında boş `comparison_dimensions` şema hatası değil, `plan_no_comparison_dimensions` uyarısı

**Karar (alan sırası):** Şemalı üretimde model alanları şemadaki sırayla yazar. `scope_reason` önceden `scope`'tan sonra ve isteğe bağlıydı; Gemma boş gerekçeyle "Başlık, veri seti… çıkar" isteğine `collection` dedi. Gerekçe zorunlu yapılıp kapsamdan önceye alındı.

### 3. Metin istemcisi — `src/llm_client.py`

- [x] `TextClient.generate_structured(system, user, schema_model, task, max_retries, errors_dir, prepare, max_output_tokens)` → `format=<şema>`, `options={temperature: 0, num_ctx, num_predict}`, sistem mesajı ayrı
- [x] JSON parse + Pydantic doğrulama; hata → ham yanıt `errors/<görev>_<deneme>.json`, doğrulama hatası bir sonraki denemede modele iletilir (§18)
- [x] `prepare`: doğrulamadan önce deterministik düzeltme (planlayıcıda alan adı eşleme)
- [x] Çağrı sayacı `TextClient.calls` → `RunSummary.text_llm_calls`
- [x] `estimate_tokens(text) = ⌈len/3,5⌉` (Faz 09)
- [x] Zaman aşımı / model yok → hata sonucu; `ModelUnavailable` yayılır

**Karar (`llm.max_retries`):** §18'deki `llm.max_retries` anahtarı §25 yapılandırmasında yok. Yeni anahtar eklenmedi; yeniden deneme sayısı çağıran tarafından verilir: planlayıcı §10.2 gereği 1, çıkarım (Faz 09) `ollama.max_retries`. Belgeye not düşülmeli.

### 4. Planlayıcı — `src/prompt_planner.py`

- [x] Prompt kaynağı çözümleme (§10.1) Faz 04'teki `resolve_prompt` ile; öncelik testleri eklendi
- [x] Varsayılan / boş prompt → LLM çağrılmadan `default_plan()`
- [x] Sistem promptu: alan kataloğu, kapsam kuralları ve örnekleri (§21.2), dil kuralı (§10.5), `needs` kuralı, prompt injection koruması (istek veri olarak `<<<REQUEST … REQUEST>>>` arasında)
- [x] Girdi bağlamı: prompt, giriş tipi (klasör / tek PDF), CLI'dan sabitlenen kapsam ve hedefler
- [x] Şema hatası → **1 kez** yeniden deneme; yine başarısız → varsayılan plan + `plan_fallback_default` uyarısı (§10.2)
- [x] **Normalleştirme:** öneksiz katalog adları eşlenir, katalog dışı anahtarlar `custom.<slug>` olur ve açıklamasızsa açıklama eklenir, tekrarlar kaldırılır (tek yeniden deneme hakkı bu kolay düzeltilebilir hatalara harcanmaz)
- [x] **CLI geçersiz kılma** (§10.2): `--scope` (auto dışı) ve `--include` (CLI veya config) plandakini ezer; gerekçeye not düşülür
- [x] Kapsam son kararı (§21.2): tek PDF girişi → `document` (açık `--scope collection` yoksa)
- [x] Katalog `needs` ile model `needs` birleştirilir (OR)
- [x] Dil yedeği: model `output_language` boş dönerse açık dil isteği ("İngilizce", "in Turkish") veya Türkçe karakter/kelime heuristiği
- [x] Plan hedefleri (`targets.include`) keşfedilen belgelere uygulanır (CLI `--include` yoksa)
- [x] Plan çıktı token sınırı 1024: Gemma bir çağrıda bitmeyen dizgi üretip 64 sn sürdü (plan ~150–300 token)

**Karar (PDF sayısı):** Faz planında girdi bağlamına "keşfedilen PDF sayısı" vardı. Gerçek denemede "a folder with 9 PDF files" bilgisi, tek tek çıkarım isteklerini (ör. "Extract the ethics approval…") de koleksiyon sanmasına yol açtı. Sayı modele verilmez; yalnızca "klasör" / "tek PDF" bilgisi verilir.

### 5. Plan hash

- [x] `compute_plan_hash` tek yerde: plan içeriği (`scope`, `requested_fields`, `custom_fields`, `needs`, `comparison_dimensions`, `output_language`, `output_outline`), `prompt_sha256`, `mode`, metin modeli adı+digest'i, görsel model adı+digest'i, `PARSER_VERSION`, belge ve plan şema sürümleri
- [x] Canonical JSON: `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`
- [x] Varsayılan planda metin modeli hash'e **dahil edilmez** (Gemma güncellenince tam dönüşümler gereksiz yenilenmez; kod yorumunda)
- [x] `targets` hash'e girmez: hangi belgelerin işleneceğini seçer, tek belgenin çıktısını değiştirmez
- [x] Atlama kuralı (§9.3) artık `prompt_sha256` yerine `plan_hash` karşılaştırır: mod veya model digest'i değişince belge yeniden işlenir (ayrıştırma ve görsel önbellek yeniden kullanılır); eski kayıt `history`'ye geçer
- [x] Plan ve `plan_hash` loga (INFO özet, DEBUG tam JSON), belge state kaydına ve çalıştırma özetine yazılır
- [x] Plan `needs` görsel tetikleyicilere iletilir (`select_vision_jobs`); varsayılan planda hepsi açık, davranış değişmedi

**Geçiş notu:** Faz 07 ve öncesinde oluşturulmuş state kayıtlarında `plan_hash` yok; bu kayıtlar ilk çalıştırmada bir kez yeniden işlenir (önbellekten, model çağrısı olmadan).

### 6. Planlayıcı önbelleği

- [x] `<output>/_cache/plans/<anahtar>.json`; anahtar = `prompt_sha256` + metin modeli digest'i + planlayıcı sürümü + plan şema sürümü
- [x] Önbellekte modelin **ham** planı tutulur; CLI geçersiz kılmaları, tek PDF kuralı ve `needs` birleştirmesi her çalıştırmada sonradan uygulanır. Bu yüzden faz planındaki "CLI geçersiz kılmaları anahtara girer" gereksizleşti
- [x] `--force` önbelleği atlar; planlayıcı istemi değişince `PLANNER_VERSION` artırılır

### 7. `--plan-only`

- [x] Preflight (Ollama ve modeller dahil, kilit hariç) → keşif (yalnızca dosya listesi; SHA-256 hesaplanmaz, PDF açılmaz) → plan → konsola: kaynak, kapsam + gerekçe, hedef filtresi ve dosyalar, istenen alanlar (etiketleriyle), `needs`, karşılaştırma boyutları, dil, çıktı başlıkları, `plan_hash`, uyarılar
- [x] Çıkış kodu 0 (§38 kriter 7); planlayıcı sırasında Ollama kapanırsa 2
- [x] Kilit alınmaz, çıktı klasörü oluşturulmaz, plan önbelleğe yazılmaz (varsa okunur), log yalnızca konsola

Prompt tabanlı çıkarım Faz 09'da geldiği için varsayılan olmayan prompt `--plan-only` olmadan hâlâ başlangıçta reddedilir (çıkış 2).

## Gerçek Gemma Sonuçları (`gemma4:latest`)

| Prompt | Kapsam | Alanlar (özet) | Süre |
|---|---|---|---:|
| Başlık, veri seti, yöntem ve en iyi sonuçları çıkar. | document | title, dataset.name, methodology.*, results.best | ~12 sn (yükleme dahil) |
| Bu makale grubunu akademik olarak özetle. | collection | — | ~10 sn |
| İlgili makalelerde kullanılan veri setlerini karşılaştır. | collection | dataset.name | ~9 sn |
| Çalışmaların özgün yönlerini ve ortak katkılarını çıkar. | collection | research.contributions | ~9 sn |
| Kullanılan yöntemleri, modelleri ve performans metriklerini tablo halinde karşılaştır. | collection | methodology.models, results.metrics | ~10 sn |
| Sınırlılıkları ve gelecek çalışma önerilerini sentezle. | collection | evaluation.limitations, evaluation.future_work | ~7 sn |
| Extract the ethics approval and code availability statements. | document | custom.ethics_approval, custom.code_availability (açıklamalı) | ~9 sn |
| Bu makalede kullanılan formülleri açıklamalarıyla listele. | document | equations.important | ~10 sn |

Tamamlanma kriteri komutu (gerçek set, 9 PDF): `collection`, alanlar `dataset.name, dataset.sample_count, dataset.classes, results.best`, `tables=evet`, karşılaştırma boyutları `dataset, results`, dil `tr`, PDF işlenmedi, çıktı klasörü oluşmadı.

## Bilinen Sınırlamalar

- `scope_reason` ve kapsam kararı modele bağlıdır; `--scope` her zaman kesin sonuç verir. İlk denemede (örneksiz, sayı bilgili istem) 6 örnekten 1'i yanlıştı; istem düzeltmesinden sonra 8/8 doğru
- Gerekçe metni İngilizce gelebilir (çıktı dili yalnızca başlıklar için uygulanır)
- `collection_name_suggestion` bazen uzun; koleksiyon adı Faz 10'da güvenli ada dönüştürülecek
- Plan önbelleği ham planı tuttuğundan, aynı prompt farklı giriş türüyle (klasör / tek PDF) ilk planın alanlarını kullanır; kapsam kuralı yine uygulanır

## Testler

- [x] `test_prompt_planner.py` — katalog grupları, takma ad ve `custom` slug; katalog `needs`; şema doğrulayıcıları; normalleştirme; prompt kaynak önceliği; varsayılan promptun LLM çağırmaması; sistem promptu ve seçenekler; geçersiz JSON → 1 yeniden deneme → varsayılan plan + uyarı + `errors/` kaydı; ikinci denemede başarı; `ModelUnavailable` yayılması; `--scope` geçersiz kılma; tek PDF + karşılaştırma → `document` (§38 kriter 8); `--include` ve plan hedef filtresi; boyutsuz koleksiyon uyarısı; dil yedeği; plan önbelleği (yeniden kullanım, `force`, model digest değişimi, yazmama); plan hash (sabitlik, mod/prompt/görsel digest ile değişim, varsayılan planda metin digest'inden bağımsızlık, hedeflerden bağımsızlık); CLI `--plan-only` (koleksiyon planı, çıktı klasörü yok, tek PDF, `--scope`); state ve özetteki `plan_hash`; **gerçek Gemma** ile §21.3 örnekleri + çıkarım promptu (6 test)
- [x] `test_batch_processor.py` — `decide` plan hash'e göre; mod değişince yeniden işleme ve `history`

## Tamamlanma Kriterleri

- [x] `process_papers.py tests\fixtures\real --prompt "Veri setlerini ve en iyi sonuçları karşılaştır." --plan-only` → `collection` kapsamlı plan, PDF işlenmez
- [x] Çıktı klasörü `--plan-only` ile oluşturulmaz
- [x] Plan hash state'e yazılıyor
- [x] `pytest` yeşil — 449 test (441 sahte arka uçla + 8 `requires_ollama`)
