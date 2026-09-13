# Faz 08 — Prompt Planlayıcı ve İşleme Planı

**İlgili bölümler:** §5, §10.1–§10.5, §17.3, §21.2, §9.3 (plan hash tanımı)
**Önkoşul:** Faz 07
**Tahmini büyüklük:** Orta

## Amaç

Kullanıcının doğal dil promptunu, şemayla doğrulanmış bir **işleme planına** dönüştürmek. Plan; kapsamı, istenen alanları, hangi pahalı işlemlerin gerektiğini ve çıktı başlıklarını belirler. Bu faz sonunda `--plan-only` çalışır.

## Modüller

`src/prompt_planner.py`, `src/schemas.py` (plan şeması), `src/field_catalog.py`, `src/llm_client.py`

## Görevler

### 1. Alan kataloğu — `src/field_catalog.py`

§17.3 tablosu makine tarafından okunabilir hale getirilir:

- [ ] Her alan: `key` (`dataset.sample_count`), `group`, `label_tr`, `label_en`, `value_type` (`str|int|float|list[str]|table|equations|results`), `hint_sections` (`["Method", "Dataset", "Yöntem", "Veri"]`), `needs` (örn. `results.*` → `tables: true`; `equations.important` → `equations: true`)
- [ ] Gruplar: `bibliographic`, `research`, `dataset`, `methodology`, `results`, `equations`, `evaluation`
- [ ] Katalog dışı istek → `custom.<slug>` alanı, `value_type: str`, açıklama metniyle
- [ ] Özel alan: `full_conversion` (varsayılan plan)

### 2. Plan şeması — `src/schemas.py`

§10.2 örneği temel alınır:

- [ ] `ProcessingPlan`: `schema_version`, `scope` (`document|collection`), `scope_reason: str`, `targets.include: list[str]`, `requested_fields: list[str]`, `custom_fields: list[{key, description}]`, `needs: {tables, equations, figures, full_text}`, `comparison_dimensions: list[str]`, `output_language` (ISO kodu veya `source`), `output_outline: list[str]`, `collection_name_suggestion: str | None`
- [ ] Doğrulayıcılar: `requested_fields` katalogda veya `custom.` önekli; `output_outline` boş değil; `scope=collection` ise `comparison_dimensions` boş olabilir ama uyarı

### 3. Metin istemcisi — `src/llm_client.py`

- [ ] Faz 07'deki `TextClient` arayüzünün Ollama gerçeklemesi
- [ ] `generate_structured(messages, schema)` → Ollama `format=schema.model_json_schema()`, `options={num_ctx, num_predict: max_output_tokens, temperature: 0}`
- [ ] JSON parse + Pydantic doğrulama; hata → ham yanıt `errors/` altına, doğrulama hatası mesajı bir sonraki denemede modele iletilir (§18), `llm.max_retries` kadar (config'te yoksa `ollama.max_retries` kullanılır — belgede `llm.max_retries` anahtarı §25'te yok; öneri: `ollama.max_retries` ile birleştir ve belgeye not düş)
- [ ] `stats.text_llm_calls += 1`
- [ ] Token tahmini: basit `len(text) / 3.5` yaklaşıklığı (bağlam sığma kontrolü için Faz 09'da kullanılacak)

### 4. Planlayıcı — `src/prompt_planner.py`

- [ ] Prompt kaynağı çözümleme (§10.1): `--prompt` > `--prompt-file` > config `prompt` > config `prompt_file` > varsayılan. Dosya UTF-8 okunur
- [ ] Varsayılan / boş prompt → LLM çağrılmadan `DEFAULT_PLAN` (Faz 04)
- [ ] Planlayıcı sistem promptu:
  - Alan kataloğu (key + açıklama) listesi
  - Kapsam kuralları (§21.2): karşılaştırma, sentez, "bu makaleler", "grup", "compare", "across" → `collection`
  - Dil kuralı (§10.5): promptta dil belirtilmişse o, değilse promptun dili
  - `needs` belirleme kuralı
  - Yalnızca şemaya uygun JSON dönmesi
- [ ] Girdi bağlamı: prompt metni, giriş tipi (klasör/tek PDF), keşfedilen PDF sayısı, CLI'dan açıkça verilen alanlar
- [ ] Şema hatası → **1 kez** yeniden dene; yine başarısız → `DEFAULT_PLAN` + uyarı `plan_fallback_default` (§10.2)
- [ ] **CLI geçersiz kılma** (§10.2): `--scope` (auto dışı) ve `--include` açıkça verildiyse plandaki karşılıkları ezilir
- [ ] Kapsam son kararı (§21.2): tek PDF girişi → `document` (CLI `--scope collection` vermediyse)
- [ ] Katalogdaki `needs` değerleri ile modelin `needs` değerleri birleştirilir (OR) — model unutmuş olsa bile `results.*` isteniyorsa tablolar açılır
- [ ] Deterministik dil tespiti yedeği: model `output_language` boş dönerse Türkçe karakter/kelime sıklığına dayalı basit heuristik

### 5. Plan hash

§9.3 tanımı — tek bir yerde hesaplanır:

- [ ] `plan_hash = sha256(canonical_json({plan (scope, fields, needs, outline, language, dimensions), prompt_sha256, mode, text_model_name, text_model_digest, vision_model_name, vision_model_digest, parser_version, schema_versions}))`
- [ ] Canonical JSON: `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`
- [ ] Varsayılan planda metin modeli kullanılmadığından hash'e metin modeli **dahil edilmez** (aksi halde Gemma güncellenince tam dönüşüm gereksiz yeniden yapılır). Kararı kod yorumunda belirt
- [ ] Plan ve `plan_hash` loga ve belge state kaydına yazılır (§10.2)

### 6. Planlayıcı önbelleği

- [ ] Aynı prompt + aynı metin modeli digest'i + aynı CLI geçersiz kılmaları → `<output>/_cache/plans/<anahtar>.json`'dan plan yeniden kullanılır (LLM çıktısı deterministik olmayabilir; aynı prompt için planın değişmesi gereksiz yeniden işleme ve hash oynamasına yol açar)
- [ ] `--force` önbelleği atlar

### 7. `--plan-only`

- [ ] Preflight (kilit dahil değil — PDF işlenmiyor, çıktıya yazılmıyor; ancak plan önbelleği yazılmaz) → keşif (sadece sayım ve hedef listesi) → plan → konsola okunabilir biçimde yazdır: kapsam + gerekçe, hedef dosyalar, istenen alanlar (etiketleriyle), `needs`, çıktı başlıkları, dil, `plan_hash`
- [ ] PDF açılmaz, çıkış kodu 0 (§38 kriter 7)
- [ ] `--plan-only` ile kilit ve çıktı klasörü oluşturma atlanır (log yalnızca konsola)

## Testler

- Prompt kaynak önceliği (dosya + CLI + config kombinasyonları)
- `FakeTextClient` ile: geçersiz JSON → 1 yeniden deneme → varsayılan plan + uyarı
- `--scope document` verildiğinde planlayıcı `collection` dese de sonuç `document`
- Tek PDF girişi + karşılaştırma promptu (scope auto) → `document` (§38 kriter 8)
- Plan hash: mod değişince değişir; aynı girdiyle sabit; model digest değişince değişir
- Katalog `needs` birleştirmesi
- `@requires_ollama` gerçek Gemma ile örnek promptlar (§21.3 listesi + "Başlık, veri seti, yöntem ve en iyi sonuçları çıkar.") → plan şemadan geçer, beklenen alanlar ve kapsam makul (snapshot olarak kaydedilir, elle incelenir)

## Tamamlanma Kriterleri

- [ ] `process_papers.py tests\fixtures\real --prompt "Veri setlerini ve en iyi sonuçları karşılaştır." --plan-only` → `collection` kapsamlı plan, PDF işlenmez
- [ ] Çıktı klasörü `--plan-only` ile oluşturulmaz
- [ ] Plan hash state'e yazılıyor
- [ ] `pytest` yeşil
