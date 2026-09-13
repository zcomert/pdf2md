# Faz 04 — Deterministik Tam Dönüşüm ve Batch Orkestrasyonu v1

**İlgili bölümler:** §3.1, §7 (son not), §9.1, §9.3, §10.1, §10.3, §11.4, §16.3, §20.1–§20.3, §29 (temel)
**Önkoşul:** Faz 03
**Tahmini büyüklük:** Orta

## Amaç

Varsayılan prompt ile uçtan uca çalışan ilk kullanılabilir sürümü çıkarmak: klasör verilir, her PDF için tam yapısal Markdown dönüşümü `A.md` olarak yazılır. Bu faz, §37 **Aşama 1**'in sonudur.

## Modüller

`src/default_prompt.py`, `src/markdown_builder.py`, `src/batch_processor.py`, `src/cli.py`

## Görevler

### 1. Prompt çözümleme — `src/default_prompt.py`

- [x] `DEFAULT_PROMPT` (tam yapısal dönüşüm, belge dilini koru)
- [x] `resolve_prompt(args, config) -> ResolvedPrompt(text, source, is_default, empty_prompt)` — öncelik `--prompt` > `--prompt-file` > config `prompt` > config `prompt_file` > varsayılan (§10.1). `merge_cli` CLI değerlerini config'e yazdığı için kaynak ayrımı `args` üzerinden yapılır
- [x] Prompt yok → varsayılan, bilgi logu; boş/boşluk → varsayılan + belge uyarısı `empty_prompt` (§10.3)
- [x] `prompt_sha256` verilen ham metinden: boş prompt ile prompt'suz çalıştırma farklı hash üretir, böylece birbirinin yerine atlanmaz ve durumlar doğru kalır
- [x] Dolu prompt → Faz 08'e kadar `PreflightError` (çıkış 2): "Prompt tabanlı çıkarım henüz desteklenmiyor"
- [x] Prompt dosyası okunamazsa `PreflightError`
- [ ] `DEFAULT_PLAN` → plan şeması Faz 08'de tanımlanacağı için oraya ertelendi; Faz 04 yalnızca `is_default` bilgisini kullanır

### 2. Markdown üretici — `src/markdown_builder.py`

- [x] `build_full_conversion(document, ctx) -> str` — saf ve deterministik; üretim zamanı `RenderContext.generated` ile verilir
- [x] Front matter (§20.2): `source`, `sha256`, `generated`, `mode`, `prompt_sha256`, `models`, `status`; `yaml.safe_dump`, sabit alan sırası; `output.front_matter` ile kapatılabilir
- [x] Her sayfa için `<!-- page: n -->` (`output.page_markers`); ayrıştırma hatalı sayfa `<!-- page: n [parse_error] -->`
- [x] **Okunamayan sayfa:** OCR/görsel model uygulanmamış `scanned` sayfa → `[unreadable_page]` (sayfa işaretleri kapalıyken de) ve `unreadable_page: page n` uyarısı (§11.4). Faz 06–07 bu sayfaları dolduracak
- [x] `header_footer` ve `figure` blokları yazılmaz (şekiller Faz 05'te `assets/` ile)
- [x] `heading` → `#` × seviye (1–6), harf aralıklı başlıklar normalize (`## ABSTRACT`)
- [x] Paragraf, `caption`, `footnote`, `reference` → tek satırda yeniden akış (`reflow`)
- [x] **Satır sonu tirelemesi:** satır tireyle bitiyor ve sonraki satır küçük harfle başlıyorsa kelime birleştirilir (`classifi-cation` → `classification`); **tireli biçim belgede başka yerde geçiyorsa tire korunur** (`pre-trained`); sonraki satır büyük harf/rakamla başlıyorsa tire korunur ve boşluk eklenmez (`Speaker-Dependent`, `1990-2000`); yumuşak tire (U+00AD) silinir
- [x] `list` → madde başına bir satır: `•`/`-` vb. → `- `, `3)`/`3.` → `3. `, `(ii)`/`a)` → `- (ii) `; işaretsiz satırlar önceki maddenin devamı; ardışık liste blokları boş satırsız
- [x] `algorithm` → ` ```text ` kod bloğu
- [x] **Kaçış:** satır başında Markdown sözdizimi (`#`, `>`, `- `, `1. `, `---`, ` ``` `) → `\#`, `1\.`; HTML etiketi gibi yorumlanabilecek `<` (`<script`, `</`, `<!--`) → `&lt;` (PDF içeriği Markdown görüntüleyicide HTML olarak çalışmasın). `p<0.05` gibi ifadelere dokunulmaz

### 3. Batch işlemcisi — `src/batch_processor.py`

- [x] `BatchProcessor(config, state, cache, output_dir, run_id, logger, prompt, force, events, cancel_token, now)`; `run(discovery, summary)`
- [x] Belge başına: `processing` + `attempts+1` → önbellek/ayrıştırma → uyarılar → Markdown → atomik yazım → `completed` / `completed_with_warnings` + `warnings`, `output_path`, `prompt_sha256`, `processed_at`, `processing_time_sec`, `models: {}`
- [x] Çıktı yolları çalıştırma başında `resolve_output_paths` ile; state'te kayıtlı yollar (filtre dışı belgelerinki dahil) önce ayrılır
- [x] **Olay arayüzü** (`BatchEvents`, Faz 13 GUI için): `on_run_start`, `on_document_start`, `on_stage` (`parse`, `write`), `on_document_end`, `on_run_end`. CLI `tqdm` ilerleme çubuğuna bağlar (TTY değilse gizlenir)
- [x] **İptal/duraklatma** (`CancelToken`): `cancel`, `pause`, `resume`, `checkpoint`; belge başında, ayrıştırmadan sonra ve yazımdan önce kontrol edilir. İptal edilen belge `pending`'e döner (yarım dosya yok)
- [x] CLI'da ilk Ctrl+C güvenli iptal, ikinci Ctrl+C hemen çıkış (`KeyboardInterrupt`; yarıda kalan kayıt sonraki çalıştırmada `recover_interrupted` ile kurtarılır); işleyici çalıştırma sonunda eski haline döner
- [x] Atlama kuralı (Faz 04 hali, `decide`): durum tamamlanmış + aynı `prompt_sha256` + çıktı dosyası mevcut ve boş değil → atla; `failed` → `--retry-failed` yoksa denenmez; `--force` → her şey yeniden (önbellek de okunmaz)
- [x] Prompt değişince önceki çıktı bilgisi `history`'ye eklenir (§9.3)
- [x] Hatalar: `DocumentError` → aşamasıyla `failed`; `OSError` → `failed(write)`; beklenmeyen istisna traceback ile loglanır ve bulunduğu aşamayla `failed`; batch devam eder
- [x] Çalıştırma özeti (§29) konsol + log + `runs[run_id]`: `toplam, completed, completed_with_warnings, failed, skipped, önceki hata nedeniyle denenmeyen, süre` ve ayrıştırma/önbellek sayıları

**Kararlar:**

- **`skipped` state'e yazılmaz.** Yazılsaydı §9.3'teki "durum `completed`/`completed_with_warnings` ise atla" koşulu bir sonraki çalıştırmada sağlanmaz ve belge gereksiz yeniden işlenirdi. `skipped` çalıştırma özetinde ve olaylarda raporlanır; kalıcı durum son gerçek işlem sonucudur (CSV'deki "son işlem durumu" ile de tutarlı)
- **Uyarılı durum:** belgedeki her uyarı (`low_text_page`, `vector_text_suspected`, `unreadable_page`, `garbled_text`, `pdf_repaired`, `empty_prompt`…) `completed_with_warnings` yapar
- **Çıkış kodları:** bu çalıştırmada başarısız olan belge varsa 1; önceki çalıştırmadan kalan ve denenmeyen `failed` kayıtları çıkış kodunu etkilemez (Faz 10'da yeniden değerlendirilecek); **iptal → 130** (§24'te tanımlı değil; kabuk geleneği 128 + SIGINT; gereksinim belgesine eklenmeli)
- **Mod ve ayrıştırıcı sürümü atlama kuralına henüz girmez;** `parse_config_hash`/`parser_version` değişince önbellek yenilenir ama tamamlanmış belgeler `--force` olmadan yeniden yazılmaz. Plan hash'i Faz 08–10'da eklenecek

### 4. `assets/`

- [x] Görsel referans yok → `assets/` oluşturulmaz (§6.2); belge klasöründe yalnızca `.md` bulunur

### Faz 03'e geri dönük iyileştirmeler (gerçek çıktı incelemesinden)

- **Damga satırlı vektör metin sayfası:** Shilaskar s.1'de sayfaya özgü IEEE damgası gövde metnini 115 karaktere çıkarıp sayfayı `text` gösteriyor ve makalenin ilk sayfası sessizce kayboluyordu. ≥1000 çizim ve <500 karakter gövde de `vector_text_suspected` sayılır (logo yoğun Vekkot s.1: 3867 çizim, 3457 karakter → etkilenmez)
- **IEEE alt başlıkları** (`A. EARLY STUDIES`, 9 pt, gövde 10 pt): harf numarası tamamı büyük harf başlıkla da kabul edilir; numaralı başlıklarda küçük font cezası uygulanmaz. Diğer 8 makalede başlık listesi değişmedi

## Bilinen Sınırlamalar

- Tablolar satır satır paragraf olarak yazılır (Faz 05)
- Formüller, şekiller yok (Faz 05, 07)
- Taranmış/vektör metin sayfaları `[unreadable_page]` (Faz 06–07)
- Blok sınırını aşan tireleme (`times-` / `tamp`, liste maddesi ile sonraki paragraf arasında) birleştirilmez
- Elsevier ilk sayfasındaki "Article info / Abstract" kutusunun sırası karışabilir (Faz 03 bilinen durum)

## Testler

- [x] `test_markdown_builder.py` — **golden file** (`tests/golden/synthetic_single_column.md`; `UPDATE_GOLDEN=1` ile güncellenir), determinizm, front matter alanları (YAML olarak) ve kapatma, sayfa işaretleri ve `[parse_error]`, okunamayan sayfa, blok türleri (başlık seviyeleri, harf aralıklı başlık, tireleme, liste türleri, sıkı liste, caption, algoritma, kaynakça, `header_footer`/`figure` atlanması), paragraf kaçışı ve HTML etiketi, `reflow` tablosu, belge içi tireli kelime dağarcığı
- [x] `test_default_prompt.py` — varsayılan, boş prompt uyarısı ve farklı hash, öncelik sırası, özel prompt, okunamayan dosya
- [x] `test_batch_processor.py` — `decide` tablosu, boş çıktı dosyası atlanmaz, `CancelToken` (duraklat/devam/iptal), olay sırası ve durum alanları, **belge ortasında iptal → `pending` ve devam eden çalıştırmada tamamlanma**, prompt değişiminde `history` ve önbellek kullanımı, silinen çıktının yeniden üretilmesi, yazım hatası → `failed(write)` ve batch devamı, `front_matter`/`page_markers` kapatma
- [x] `test_cli_batch.py` — uçtan uca: her geçerli PDF için `.md`, **belge klasöründe yalnızca `.md`** (§38 kriter 2), **aynı adlı PDF'ler çakışmaz** (kriter 3), **metin LLM'i yok** (`models: {}`, kriter 4), **boş prompt → uyarılı** (kriter 6), açılamayanlar `failed(parse)` (kriter 11), `document.json` şema (kriter 23), giriş klasörü değişmez (kriter 17), ikinci çalıştırma atlar ve çıkış 0, özel prompt → çıkış 2 ve çıktı klasörü oluşmaz, `--force`, `--retry-failed`, içeriği değişen PDF yeniden üretilir, **iptal → çıkış 130, kilit bırakılır, devam eden çalıştırma kalanı işler**
- [x] Faz 00/02 CLI testleri yeni davranışa göre güncellendi

## Tamamlanma Kriterleri

- [x] `.venv\Scripts\python.exe process_papers.py tests\fixtures --recursive` ile her geçerli PDF için okunabilir bir `A.md` üretilir (17 dosya, ~4 sn)
- [x] Gerçek makalelerden en az ikisinin çıktısı elle incelendi (Pokorny, Rahman, Vekkot, Berardi); kritik hatalar (IEEE alt başlıkları, vektör metinli ilk sayfa, sayı aralığı tirelemesi) düzeltildi, kalanlar "Bilinen Sınırlamalar"da
- [x] §38 kriterleri 1, 2, 3, 4, 6, 11, 17 otomatik testlerle karşılanıyor
- [x] `pytest` yeşil (288 geçti, 1 atlandı — Tesseract kurulu değil)

> **Kilometre taşı:** Aşama 1 tamamlandı. Commit + etiket (`v0.1-asama1`) önerilir.
