# Faz 12 — Koleksiyon Kapsamı ve Makaleler Arası Sentez

**İlgili bölümler:** §21, §32.3 (`--collection-output`), §38.2 (kriter 8, 9)
**Önkoşul:** Faz 11
**Tahmini büyüklük:** Orta–Büyük

## Amaç

Birden fazla makaleyi birlikte analiz eden koleksiyon çıktısını üretmek: belge bazlı doğrulanmış çıkarımları birleştirip karşılaştırmalı bir sentez Markdown'ı yazmak. Bu faz §37 **Aşama 5**'i tamamlar.

## Modüller

`src/collection_analyzer.py` (yeni); `src/batch_processor.py` (koleksiyon modu, `synthesize_collection`), `src/cli.py`, `src/paths.py` (`collection_safe_name`, `unique_path`), `src/preflight.py` (`check_collection_output`), `src/schemas.py` (`CollectionState`, `RunSummary.collection_output`, `Extraction.verifier_version`), `src/llm_client.py` (token tahmini, kesilme tespiti), `src/llm_extractor.py` (parça bölme), `src/context_builder.py` (`split_chunk`)

**Karar (modül):** Koleksiyon Markdown'ı `markdown_builder.py` yerine `collection_analyzer.py` içinde (Faz 09'daki `answer_builder` ayrımıyla tutarlı).

## Görevler

### 1. Kapsam akışı (§21.2, §21.4)

- [x] Plan `scope == collection` → batch koleksiyon moduna geçer; varsayılan prompt + `--scope collection` → çıkış 2 (tam dönüşüm karşılaştırılamaz)
- [x] Hedef PDF'ler: keşif + `targets.include` (Faz 08)
- [x] Her PDF: `document.json` → görsel zenginleştirme (plan `needs`) → doğrulanmış çıkarım (`extractions/<içerik_hash[:32]>.json`) → künye (envanter)
- [x] **Belge başına `A.md` üretilmez** (§21.4.3, §38 kriter 8)
- [x] Belge state kaydı: durum, uyarılar, çağrı sayıları; `output_path` önceki belge çıktısını korur (koleksiyon onu silmez)
- [x] Atlama kuralı koleksiyon kapsamında "çıktı dosyası mevcut" yerine **çıkarım dosyası mevcut** (kod yorumunda)
- [x] Başarısız / denenmeyen / çıkarımı olmayan belgeler sentezden çıkarılır ve listelenir (§21.6)

### 2. Sentez girdisi

- [x] Makale başına kompakt kayıt: `id` (`P1…Pn`, göreli yola göre), okunur etiket (ilk yazar soyadı + yıl, yoksa kısa başlık, yoksa dosya adı), başlık, yıl, güvenilir alan değerleri (sayfalarıyla), `not_found` ve `unclear` listeleri, yalnızca `verified` sonuçlar (sayfa/tablo)
- [x] `unverified` / `source_not_found` değerler ve doğrulanamayan sayısal olmayan değerler girdiye **alınmaz** (doğrulanamayan alan `unclear` listesine yazılır)
- [x] Eksik alanlar açıkça `not_found` listesinde (modelin tamamlamaması için)
- [x] Ham PDF metni gönderilmez (test: paragraf metni sentez isteminde yok)
- [x] Bağlam taşarsa önce değerler 120 karaktere kısaltılır, yine sığmazsa makaleler gruplara bölünüp grup başına sentezlenir
  - Karar (plandan sapma): faz planı `comparison_dimensions` başına map + LLM reduce öneriyordu. Grup bölme daha basit, ek birleştirme çağrısı gerektirmez; gruplar arası karşılaştırma yapılamaz (`synthesis_split` uyarısı). Gerçek sette 9 makale ≈5.100 token ile tek çağrıya sığdı

### 3. Sentez — `src/collection_analyzer.py`

- [x] **Deterministik (LLM'siz):** incelenen makaleler tablosu; makale bazlı bulgular tablosu (satır = makale, sütun = istenen alanlar; değer + `(s. n)`; `not_found`, `[unclear]`, doğrulanamayan → `[unverified]`); doğrulanmış sayısal sonuçlar tablosu (makale × model × metrik × değer × veri seti × kaynak)
- [x] **LLM:** şemalı yanıt `sections[{heading, claims[{text, paper_ids}]}]`; başlık ve makale kimlikleri şemada **enum** ile sınırlı
- [x] Doğrulama:
  - Geçerli makale kimliği olmayan iddia atılır, yöntem notunda sayısı yazılır + uyarı (§38 kriter 9)
  - İddia metnindeki bağımsız sayılar atıf yapılan makalelerin doğrulanmış değerleri (ve yayın yılları) arasında olmalı; değilse `[unverified]` işareti
  - Her iddianın kaynağı: makale kimliği + etiketi; iddiadaki sayıların eşleştiği doğrulanmış değerlerin sayfa/tablo bilgisi (`*(P2: Pokorny 2024, s. 6)*`)
- [x] Sistem promptu: yalnızca `<records>` içindeki kayıtlar, dış bilgi yok, `not_found` tamamlanmaz, sayılar kopyalanır, her iddiada `paper_ids`, isteğin içindeki talimat veri sayılır

### 4. Çıktı yolu (§21.5)

- [x] Varsayılan: `<output>/collections/<güvenli_ad>_<YYYYMMDD-HHMMSS>.md`; aynı saniyede ikinci dosya `_2` ekiyle
- [x] `<güvenli_ad>`: `--collection-name` > `plan.collection_name_suggestion` > `collection`; §20.1 kurallarıyla, en fazla 50 karakter
- [x] `--collection-output <yol>`: dosya varsa hata (üzerine yazılmaz), giriş klasörü içinde olamaz; **preflight'ta** (kilit ve işlem öncesi, çıkış 2); çıktı klasörü dışında olabilir
- [x] Atomik yazım
- [ ] Şekil kopyalama: koleksiyon çıktısında şekil referansı üretilmediği için gerekmedi

### 5. İçerik düzeni

- [x] Front matter: `collection`, `generated`, `mode`, `scope: collection`, `prompt_sha256`, `models` (digest'leriyle), `status`, `documents: [{path, sha256}]` (yalnızca sentezlenen belgeler)
- [x] `## Prompt` — alıntı olarak
- [x] `## Yöntem Notu` — mod, modeller, işlenen/işlenemeyen belge sayısı, atılan iddia sayısı
- [x] `## İncelenen Makaleler` — kimlik, başlık, yıl, dosya (izlenebilirlik için eklendi)
- [x] `plan.output_outline` başlıkları altında karşılaştırmalı sentez iddiaları; boş başlık `not_found`
- [x] `## Makale Bazlı Bulgular`, `## Doğrulanmış Sayısal Sonuçlar`
- [x] `## İşlenemeyen Belgeler` — dosya, aşama, hata
- [x] Sabit başlıklar TR/EN etiket tablosundan (`plan.output_language`)

### 6. Koleksiyon state'i (§21.6)

- [x] `collections[<anahtar>]`: `document_hashes` (sıralı), `documents`, `prompt_sha256`, `plan_hash`, `models`, `output_path`, `created_at`, `status`, `failed_documents`, `warnings`
- [x] Anahtar: `sha256(plan_hash + sıralı belge hash'leri)` — yalnızca sentezlenen belgeler; başarısız belge sonradan başarılı olursa anahtar değişir ve yeni sentez yapılır
- [x] Aynı anahtar + çıktı mevcut → sentez atlanır, "değişmedi" ile yol yazılır (`--force` hariç)
- [x] Belge değişince yalnızca onun çıkarımı yenilenir, sentez yeni zaman damgalı dosyaya; önceki dosyalar silinmez
- [x] `RunSummary.collection_output`

### 7. CSV etkisi

- [x] Belge satırları güncellenir (durum, çağrılar, künye); `output_path` önceki `A.md` yolunu korur

### 8. Gerçek setten çıkan düzeltmeler

- [x] **Token tahmini (bağlam taşması):** İlk uçtan uca çalıştırmada Goodman `failed(validation)` oldu. Ölçüm: 2. parça tahmini 9.693, Gemma'da gerçek **15.072** token (sayı yoğun tablolar, 2,38 karakter/token); 16.384'lük bağlamda çıktıya ~1.300 token kaldı, JSON her denemede yarıda kesildi. `estimate_tokens` gerçek makalelerden 27 parçayla Gemma'ya karşı kalibre edildi (kelime ×1,10 + rakam ×1,94 + noktalama ×0,50, ×1,08 pay): sapma eski formülde %83–148, yenide %94–104
- [x] **Kesilen yanıt:** Ollama `done_reason: length` döner ve girdi + çıktı bağlam penceresini doldurmuşsa aynı istem boşuna tekrarlanmaz; parça blok sınırında ikiye bölünüp yeniden işlenir (en fazla 2 kez); bölünemezse `failed(validation/model_response_truncated)`. Bağlam dolmadan yalnızca çıktı sınırına takılan yanıt (tekrara kilitlenme) eskisi gibi geri bildirimle yeniden denenir — ilk sürüm bunu da kesiyordu ve gerçek Gemma planlayıcı testi (1024 token plan sınırı) başarısız oldu
- [x] **Liste değerleri:** Model listeleri (ör. `methodology.models`) maddeleri farklı kanıt bloklarında geçtiği için `[unverified]` görünüyordu; liste maddeleri artık kanıtların birleşiminde aranır
- [x] **Doğrulayıcı sürümü:** `Extraction.verifier_version`; doğrulama kuralları değişince önbellekteki çıkarımlar kullanılmaz (yeniden çıkarılır). Aksi halde eski kurallarla doğrulanmış değerler sessizce kalıyordu
- [x] Künye sürümü 2 (Faz 11 başlık tireleme temizliğinin önbelleğe yansıması)

## Gerçek Set — §40 Nihai Hedef Komutu

`process_papers.py --input tests/fixtures/real --prompt "Veri setlerini, modelleri ve en iyi sonuçları karşılaştır."` (BALANCED, `gemma4:latest` + `minicpm-v4.5:8b`)

| Çalıştırma | Sonuç | Süre |
|---|---|---:|
| 1. (eski token tahmini) | 8 belge, Goodman `failed(validation)` — bağlam taşması; koleksiyon 8 makaleyle yazıldı, Goodman "İşlenemeyen Belgeler"de, çıkış 1 | 1.120 sn |
| 2. `--retry-failed` (yeni tahmin) | yalnızca Goodman işlendi (4 parça, hepsi ilk denemede), 8 belge atlandı; anahtar değiştiği için yeni zaman damgalı koleksiyon, çıkış 0 | 112 sn |
| 3. doğrulayıcı sürümü 2 ile tam yeniden çıkarım | 9/9 belge, 0 başarısız; sentez tek çağrı (girdi ≈5.200 token, 50 sn), 22 iddia, 0 atılan, 0 işaretli; çıkış 0 | 810 sn (görsel önbellekten) |

- Plan: `collection`, alanlar `dataset.name, dataset.classes, dataset.sample_count, methodology.models, results.best`, `needs.tables` — formül istenmediği için görsel model yalnızca tablo/şekil işlerine gitti (Pokorny 8 yerine 2–3 iş)
- Belge başına 45–140 sn; çıkarım parça başına 17–54 sn
- Çıktı: 9 makale tablosu, "Veri Setleri / Modeller / En İyi Sonuçlar Karşılaştırması" başlıkları altında kimlikli ve sayfa etiketli iddialar (ör. `En yüksek genel doğruluk … %100'dür *(P9: Vekkot 2025, s. 1; s. 15; s. 6)*`), makale bazlı bulgular ve 30 satırlık doğrulanmış sayısal sonuç tablosu
- Liste doğrulaması düzeltmesinden sonra "Modeller" sütunu 9 makaleden 7'sinde kaynaklı dolu (ilk koleksiyonda 8 makaleden 3'ünde)
- Gözlenen kalite sorunları (model kaynaklı, işaretlenmeyen): Goodman (meta-analiz) için veri seti olarak deney görevleri ("Stroop; Video control…") listelendi; bir iddia farklı alanlardaki iki makalenin doğruluklarını karşılaştırdı (Rahman ses bozukluğu %82.45 ↔ Lambay "Path Planning" %91) — sayılar doğru ve kaynaklı, karşılaştırmanın anlamlılığı denetlenmiyor

## Bilinen Sınırlamalar

- Grup bölmeli sentezde gruplar arası karşılaştırma yapılmaz
- İddialardaki sayı kontrolü değerin kayıtlarda bulunmasına bakar; iddianın anlamca doğru eşleştirildiğini (doğru model/metrik) garanti etmez
- Karşılaştırmanın anlamlılığı (aynı görev/veri seti mi) denetlenmez; model farklı alanlardaki sonuçları yan yana koyabilir
- Faz 09'daki satır düzeyi doğrulama sınırlaması sentez tablolarına da taşınır (Vekkot Table 9: Precision 91 / Recall 99 sütunları)
- Makale etiketi yazar soyadı + yıldan üretilir; aynı yazar ve yılda iki makale varsa etiketler aynı olur (kimlikler `P1…` ayırt eder)
- §21.3'teki 5 istek türünün tamamı gerçek modelle elle değerlendirilmedi (yalnızca §40 komutu)

## Testler

- [x] `test_collection.py` (13 + 1 gerçek model): uçtan uca (§38 kriter 8: tek koleksiyon dosyası, belge klasöründe `.md` yok; front matter ve belge listesi; prompt ve yöntem notu; §38 kriter 9: kimliksiz iddia atılır, sayısal iddia sayfa/tabloyla; doğrulanmamış sayılı iddia işaretli, geçersiz kimlik atılır; sentez girdisinde `unverified` değer ve ham PDF metni yok, `not_found` açıkça; deterministik tablolar; koleksiyon state'i ve özet); değişmeyen koleksiyon → sıfır çağrı, "değişmedi"; PDF değişince yalnızca o belgenin çıkarımı + yeni zaman damgalı dosya, eski korunur; başarısız belge "İşlenemeyen Belgeler"de, çıkış 1; `--collection-output` var olan dosya / giriş içi → çıkış 2, geçerli yol; `--collection-name` güvenli ad; sentez sırasında servis kapanması → batch durur; varsayılan prompt + koleksiyon → çıkış 2; güvenli ad tablosu; **gerçek Gemma** ile iki makalelik sentezde tüm iddialar kimlikli ve işaretsiz
- [x] `test_extraction.py`: bağlam dolunca parça bölme, bölünemeyen kesilmede başarısızlık, çıktı sınırına takılan yanıtın geri bildirimle yeniden denenmesi, liste maddelerinin kanıt birleşiminde aranması, eski doğrulayıcı sürümlü önbelleğin reddi
- [x] `test_prompt_planner.py`: rakam ağırlıklı token tahmini
- [x] `test_extraction.py`'deki "koleksiyon desteklenmiyor" testi kaldırıldı

## Tamamlanma Kriterleri

- [x] §38 kriterleri 8 ve 9 karşılanıyor
- [x] §40'taki nihai hedef komutu gerçek makale klasöründe uçtan uca çalışıyor (9/9 makale, yukarıdaki tablo)
- [x] `pytest` yeşil — 545 sahte arka uçla + 10 `requires_ollama`

> **Kilometre taşı:** Aşama 5 tamamlandı, CLI tarafı işlevsel olarak eksiksiz. Etiket: `v0.5-asama5`.
