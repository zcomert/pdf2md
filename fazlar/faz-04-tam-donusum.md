# Faz 04 — Deterministik Tam Dönüşüm ve Batch Orkestrasyonu v1

**İlgili bölümler:** §3.1, §7 (son not), §10.3, §16.3, §20.1–§20.3, §29 (temel)
**Önkoşul:** Faz 03
**Tahmini büyüklük:** Orta

## Amaç

Varsayılan prompt ile uçtan uca çalışan ilk kullanılabilir sürümü çıkarmak: klasör verilir, her PDF için tam yapısal Markdown dönüşümü `A.md` olarak yazılır. Bu faz, §37 **Aşama 1**'in sonudur.

## Modüller

`src/markdown_builder.py`, `src/batch_processor.py`, `src/default_prompt.py`

## Görevler

### 1. Varsayılan prompt — `src/default_prompt.py`

- [ ] `DEFAULT_PROMPT` metni (tam yapısal dönüşüm isteği, belge dilini koru)
- [ ] `DEFAULT_PLAN` — sabit plan nesnesi (Faz 08'deki plan şemasının ilk hali): `scope=document`, `requested_fields=["full_conversion"]`, `needs={tables, equations, figures, full_text: true}`, `output_language="source"`
- [ ] `is_default_plan(plan)` — markdown builder'ın LLM'siz yolu seçmesi için
- [ ] Prompt kaynağı çözümleme (§10.1, §10.3) şimdiden:
  - Hiç prompt yok → varsayılan, INFO log
  - Boş/boşluk prompt → varsayılan + belge uyarısı `empty_prompt`
  - Dolu prompt → Faz 08'e kadar "henüz desteklenmiyor" hatası (çıkış kodu 2)

### 2. Markdown üretici — `src/markdown_builder.py`

- [ ] `build_full_conversion(doc: DocumentModel, ctx) -> str` — **saf ve deterministik** (aynı girdi → bayt bayt aynı çıktı; `generated` zaman damgası front matter'da olduğundan testlerde enjekte edilebilir saat kullanılır)
- [ ] Front matter (§20.2) — `output.front_matter` açıksa; YAML güvenli yazım (`yaml.safe_dump`, alan sırası sabit)
  - `models` bu fazda yalnızca kullanılan modeller (varsayılan promptta metin modeli yok; görsel model Faz 07'den sonra)
- [ ] Bloklar `order`'a göre gezilir, `header_footer` atlanır
- [ ] `heading` → `#` × seviye (en fazla 6)
- [ ] `paragraph` → satır sonu tirelemesi birleştirilir (`exam-\nple` → `example`), tek satır sonları boşluğa çevrilir
- [ ] `list` → `- ` veya `1. `
- [ ] `table` / `equation` / `figure` → `ref_id` ile ilgili kayda bakılır; kayıt yoksa (Faz 05 öncesi) blok metni olduğu gibi yazılır
- [ ] `algorithm` → fenced code block
- [ ] `caption`, `footnote` → düz paragraf (dipnot için `> ` veya `[^n]` biçimi; basit tut)
- [ ] Sayfa geçişlerinde `<!-- page: n -->` (`output.page_markers`)
- [ ] Markdown özel karakter kaçışı: satır başındaki `#`, `>`, `-`, `1.` gibi yanlış yorumlanabilecek metinler kaçırılır; LaTeX içeriğine dokunulmaz
- [ ] Parse hatalı sayfa için `<!-- page: n [parse_error] -->` ve uyarı
- [ ] `[unreadable_page]` işareti (Faz 06–07'de dolacak) için yer tutucu desteği

### 3. Batch işlemcisi v1 — `src/batch_processor.py`

```text
for pdf in discovered (deterministik sıra):
    state → processing
    try:
        doc = cache.load_document(sha) or parse_pdf(...)
        md  = build_full_conversion(doc, ctx)
        atomic_write(output_path, md)
        state → completed | completed_with_warnings
    except DocumentError as e:
        state → failed(error_stage, error)
    except FatalBatchError:
        state kaydet, döngüden çık
```

- [ ] `BatchProcessor(config, state, cache, events)` sınıfı
- [ ] **Olay/ilerleme arayüzü** (GUI için baştan, Faz 13): `events.on_document_start(rel_path)`, `on_stage(rel_path, stage)`, `on_document_end(rel_path, status, warnings)`, `on_run_end(summary)`. CLI uygulaması bunu `tqdm`'e bağlar
- [ ] **İptal/duraklatma tokenı:** `CancelToken` (`threading.Event` tabanlı `cancel`, `pause`). Belgeler arasında ve aşamalar arasında kontrol edilir. CLI'da `Ctrl+C` → iptal tokenı → mevcut belgeyi yarım bırakmadan state kaydı ve çıkış
- [ ] Uyarı toplama: belge uyarıları (`doc.warnings` + çalışma uyarıları) → `completed_with_warnings`
- [ ] `processing_time_sec`, `attempts`, `last_run_id`, `output_path`, `prompt_sha256` state'e yazılır
- [ ] Basit atlama (tam kural Faz 10'da): durum `completed*`, sha aynı, `prompt_sha256` aynı ve çıktı dosyası mevcut/boş değil → `skipped`
- [ ] `--force` → önbellek okunmaz, atlama yok
- [ ] Çalıştırma sonu özet: toplam/completed/warnings/failed/skipped + süre → konsol ve log (§29)
- [ ] Çıkış kodu: herhangi `failed` → 1, değilse 0

### 4. `assets/` kuralı

- [ ] Bu fazda görsel referans yok → `assets/` **oluşturulmaz** (§6.2). Kopyalama mantığı Faz 05'te.

## Testler

- Deterministiklik: aynı `document.json` iki kez → aynı Markdown (sabit saat ile)
- `synthetic_single_column.pdf` için beklenen Markdown'ın "golden file" karşılaştırması (`tests/golden/`)
- Başlık seviyeleri, listeler, sayfa işaretleri, üst/alt bilginin çıkarılması
- `page_markers: false` ve `front_matter: false` seçenekleri
- Entegrasyon: fixture klasöründe tam çalıştırma
  - Aynı adlı iki PDF (kök + `subdir/`) çıktıları çakışmaz (§38 kriter 3)
  - Bozuk/şifreli `failed`, diğerleri `completed*`, çıkış kodu 1
  - Belge klasöründe `.md` dışında içerik dosyası yok (§38 kriter 2)
  - İkinci çalıştırmada tümü `skipped`
  - Boş prompt (`--prompt "  "`) → `completed_with_warnings` (§38 kriter 6)
- Giriş klasörü önce/sonra hash'leri aynı (§38 kriter 17)

## Tamamlanma Kriterleri

- [ ] `.venv\Scripts\python.exe process_papers.py tests\fixtures --recursive` ile her geçerli PDF için okunabilir bir `A.md` üretilir
- [ ] Gerçek makalelerden en az ikisinin çıktısı elle incelenmiş, başlık/paragraf/sıra hataları not edilmiş ve kritik olanları düzeltilmiş
- [ ] §38 kriterleri 1, 2, 3, 4 (LLM çağrısı yok), 6, 11, 17 bu kapsamda karşılanıyor
- [ ] `pytest` yeşil

> **Kilometre taşı:** Aşama 1 tamamlandı. Bu noktada commit + etiket (`v0.1-asama1`) önerilir.
