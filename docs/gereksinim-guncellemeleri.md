# Gereksinim Belgesine İşlenecek Kararlar ve Sapmalar

`gereksinim-analizi.md` uygulama sırasında değiştirilmedi (Faz 11'deki kullanıcı kararı: kararlar faz dosyalarında kalır). Bu belge, gereksinim belgesinin bir sonraki sürümüne işlenmesi gereken tüm karar, sapma ve eklemeleri bölüm sırasıyla toplar. Her maddenin gerekçesi ilgili faz dosyasındadır.

Durum: **v1.0.0 öncesi — kullanıcı onayı bekliyor.**

## §6.2 / §32.2 Çıktı klasörü

- Tek PDF girişinde varsayılan çıktı, PDF'in bulunduğu klasörün kardeşidir: `D:\papers\a.pdf` → `D:\papers_output` (Faz 02). Sürücü kökündeki girişte `--output` zorunludur.
- Çıktı klasöründe `collections/` ve `logs/` gibi ayrılmış adlarla çakışan belge klasörlerine `_` eki verilir (Faz 04).

## §9 İşlem durumu

- **§9.1 `skipped` kalıcı duruma yazılmaz**; çalıştırma özetinde ve olaylarda raporlanır. Yazılsaydı §9.3 atlama koşulu bir sonraki çalıştırmada sağlanmazdı (Faz 04).
- **§9.3 plan hash tanımı** (Faz 08, 11): plan içeriği (kapsam, alanlar, özel alanlar, `needs`, karşılaştırma boyutları, dil, başlıklar) + `prompt_sha256` + mod + görsel model adı ve digest'i + ayrıştırıcı ve şema sürümleri + **envanter imzası** (künye sürümü, `summary.bibliographic_llm`, `summary.extra_fields`). Metin modeli yalnızca plan veya envanter onu kullanıyorsa girer. Hedef filtresi (`targets.include`) girmez.
- Prompt çıkarımının önbellek anahtarı envanter imzasız "içerik hash'idir"; envanter ayarı değişince çıkarım tekrarlanmaz (Faz 11).
- Aynı saniyede başlayan çalıştırmalar için `run_id` sonuna `-2`, `-3` eklenir (Faz 02).
- Eşzamanlılık kilidi PID kontrolü yerine işletim sistemi dosya kilidiyle yapılır (Faz 02).

## §10 Prompt ve plan

- **§10.2** Planlayıcıya keşfedilen PDF sayısı verilmez (tek tek çıkarım isteklerini koleksiyon sanmasına yol açtı) (Faz 08).
- Plan önbelleği: `_cache/plans/<prompt + metin modeli digest'i + planlayıcı sürümü>.json`; CLI geçersiz kılmaları sonradan uygulanır (Faz 08).
- Varsayılan prompt + `--scope collection` başlangıçta reddedilir (çıkış 2) (Faz 12).

## §11 PDF işleme

- **§11.2** Metni vektör yol olarak çizilmiş sayfalar (ör. "Microsoft Print To PDF") `scanned` gibi ele alınır ve OCR'lanır; `vector_text_suspected` uyarısı (Faz 03, 06).
- Az metinli ve düşük görsel oranlı sayfalar `text` sınıfı + `low_text_page` uyarısı (Faz 03).

## §12–13 Görsel işleme ve tablolar

- **§12.3 BALANCED:** başlıklı şekiller görsel modele gönderilmez (tam dönüşüm şekil türünü kullanmaz); metin katmanından tutarlı yapılandırılmış tablolar hiçbir modda gönderilmez (Faz 07).
- Görsel görevlerde çıktı token sınırı: sayfa düzeni 32, şekil 256, formül 512, tablo 3072 (Faz 07).
- **§13** Görselden gelen tablo sayısı aynı bölgenin metin katmanında yoksa tahmin edilmez, `[unclear]` yazılır (Faz 07).
- `[table_structure_unavailable]` ve `[latex_unavailable]` işaretleri belgeyi `completed_with_warnings` yapmaz (Faz 05).
- **Formül LaTeX'i önce metin katmanından kurulur** (`src/equation_latex.py`): karakter konumu/puntosu/fontu ve kesir çizgilerinden kesir, büyük operatör sınırları, üs/alt simge, aksan, `\mathbf`/`\mathbb`, `\text{}` ve operatör adları. Kurulan formül tablolardaki kural gibi hiçbir modda görsel modele gönderilmez; FAST modda da LaTeX üretilir. Tanınmayan glif, çok satırlı yapı (cases, matris) veya kök işaretinde kurulum yapılmaz, formül görsel modele kalır.
- Görsel modele giden formül kırpımı numarayı içermez; dolgu payındaki komşu metin beyazla örtülür. İsteme bölgenin metin katmanı karakterleri ipucu olarak eklenir. Kaçışsız LaTeX JSON'u (`\frac` → form-feed) onarılır; geçersiz LaTeX bir kez geri bildirimle yeniden istenir.
- Formül numarası Markdown'da `\tag{n}` ile yazılır. Numaranın önündeki görünmez glif (`\x08 (1)`) numara tespitini engellemez; numara satırına yalnızca bitişik olan düzyazı satırları formüle alınmaz (metin kaybı giderildi).

## §17–19 Çıkarım ve doğrulama

- **§18 `llm.max_retries`** §25 yapılandırmasında yok. Anahtar eklenmedi: planlayıcı 1 kez (§10.2), çıkarım ve künye `ollama.max_retries` kadar yeniden dener (Faz 08).
- **§17.2** Parça bütçesi `text_num_ctx − max_output_tokens − 2500`; token tahmini Gemma'ya karşı kalibre edildi (rakamlar ağır). Bağlam dolup yanıt kesilirse (`done_reason: length`) aynı istem tekrarlanmaz, parça ikiye bölünür (Faz 12).
- **§18** Çıkarım dosyası adı `extractions/<plan_hash[:32]>.json` (Windows 260 karakter yol sınırı); tam hash dosya içinde doğrulanır. Dosyada `verifier_version` bulunur; doğrulama kuralları değişince önbellek kullanılmaz (Faz 09, 12).
- **§19.1 ek kurallar** (Faz 09, 12):
  - Değerdeki **tüm** sayılar kanıtta geçmelidir; sonuçlarda iddia cümlesindeki sayılar da doğrulanır.
  - Tablo kanıtında değer, sonucun model adının geçtiği satır(lar)da aranır.
  - **Sütun kuralı (Faz 14):** metriğin sütunu çok düzeyli başlıklar düzleştirilerek (boş başlık hücresi soldakini sürdürür, alt başlık satırları eklenir) tek anlamlı belirlenebiliyorsa değer yalnızca model satır(lar)ının o sütunundaki hücrede aranır; "F1-Score", "F score", "F-measure" eşdeğerdir. Sütun belirlenemezse satır kuralı geçerlidir ve `verified` doğru sütunu garanti etmez. Faz 09–13'te gerçek sette 7 doğrulanmış sonuçtan 1'i yanlış sütundandı; bu kuralla doğruluk ölçümünde çelişen `verified` 0'a indi.
  - Belgede olmayan `block_id` → `source_not_found`; bu durumda sayfa bilgisi de güvenilmez sayılır.
  - Sayısal olmayan değerler için doğrulama etiketi yoktur; değer metninin kanıtta geçmesi (`in_evidence`) kontrol edilir, liste maddeleri kanıtların birleşiminde aranır.
- **§19.4 / §20** Yazmadan önce güvenlik ağı: işaretsiz ve doğrulanmamış bağımsız sayı içeren satıra `[unverified]` eklenir.
- §17.2.4 isteğe bağlı yazım çağrısı uygulanmadı (yeni sayı üretme riski) (Faz 09).

## §21 Koleksiyon

- Koleksiyon kapsamında atlama kuralındaki "çıktı dosyası mevcut" koşulu **çıkarım dosyası mevcut** olarak uygulanır; belgenin önceki `A.md` yolu korunur (Faz 12).
- Koleksiyon anahtarı `sha256(plan_hash + sıralı belge hash'leri)`; yalnızca sentezlenen (başarılı) belgeler girer (Faz 12).
- Sentez girdisi bağlama sığmazsa değerler kısaltılır, yine sığmazsa makaleler gruplara bölünür (plan boyut bazlı map-reduce öneriyordu) (Faz 12).
- İddiada makale kimliği (`P1…`) zorunlu; iddiadaki sayı atıf yapılan makalelerin doğrulanmış değerlerinde yoksa `[unverified]` (Faz 12).

## §22 Envanter

- **§22.3 / §38 kriter 4 çelişkisi — kullanıcı kararı:** künye çıkarımı tam dönüşüm içeriğinin parçası değildir; ayrı envanter adımıdır ve eksik alan varsa ilk 2 sayfa üzerinde kısa bir LLM çağrısı yapılır. Kriter 4 "`A.md` içeriği üretilirken metin LLM'i çağrılmaz" olarak okunur. **§25'e yeni anahtar:** `summary.bibliographic_llm: true` (Faz 11).
- Künye kaynak sırasına ek adımlar: yayıncı `subject` metadata kalıpları (Elsevier, IEEE), ayrıştırıcının başlık tespiti, plan çıkarımındaki doğrulanmış künye değerleri. `creationDate` yıl kaynağı değildir. LLM'in verdiği yıl ve DOI ilk sayfalarda birebir geçmelidir (Faz 11).
- **§22.2** CSV sayfa/çağrı sayıları ve künye `_cache` yerine state'ten üretilir (önbellek silinse de CSV eksiksiz) (Faz 11).
- **§22.4** Sayısal olmayan analitik alanlarda "doğrulanmış" = değer metni kanıtta geçiyor ve güven `low` değil (Faz 11).
- `results.best_<metrik>` türetilmiş alanları (`accuracy`, `f1`, `precision`, `recall`, `auc`) (Faz 11).
- Envanter (künye, analitik sütun) uyarıları belge durumunu değiştirmez, loglanır (Faz 11).

## §24 Komut satırı

- **Çıkış kodu 130:** Ctrl+C / Ctrl+Break ile güvenli iptal (§24'te tanımlı değil; kabuk geleneği 128 + SIGINT) (Faz 04, 10).
- **Çıkış 1 kapsamı:** bu çalıştırmada en az bir belge başarısız (keşifte okunamayan dahil), batch sistem hatasıyla durdu veya koleksiyon çıktısı üretilemedi. Önceki çalıştırmadan kalan ve denenmeyen `failed` kayıtlar çıkış kodunu etkilemez (Faz 10, 12).
- `--collection-output` var olan dosya veya giriş klasörü içi → başlangıçta çıkış 2 (Faz 12).

## §26 Başlangıç kontrolleri

- Metin modeli, varsayılan prompt kullanılsa da koşulsuz zorunludur (künye adımı) (Faz 07, 11).
- `output.save_xlsx` açık ve `openpyxl` yoksa uyarı (Faz 11).

## §27 Paralellik

- CPU aşaması (`parse_pdf` + OCR) süreç havuzunda; model aşaması belge sırasıyla ana süreçte, belgeler arası paralel model çağrısı yok (Faz 10).

## §28 Hata yönetimi

- **Model servisi kapanırsa ve disk dolarsa belge `failed` değil `pending` bırakılır** (§28 `failed` der). `failed` belgeler `--retry-failed` olmadan denenmediği için sorun giderilince belge sessizce atlanırdı (Faz 07, 10).
- Hata kaydına `error_type` eklendi (`corrupt_pdf`, `model_timeout`, `write_error`, …) (Faz 10).
- Art arda ikinci yazma hatasında batch durur (Faz 10).

## §38 Kabul kriterleri

- **Kriter 22 eşik değerleri:** `reports/accuracy_<tarih>.md` ilk ölçümüne göre önerilen eşikler README'nin "Doğruluk" bölümündedir; kullanıcı onayından sonra belgeye eklenmelidir.
- **§38.1 test seti eksikleri:** 4 tek sütunlu gerçek makale yerine 1 (Berardi); 2 taranmış gerçek PDF yerine 0 (sentetik taranmış PDF ve metni vektör çizilmiş Shilaskar makalesi var). Referans veri 3 makale için hazırlandı (`tests/fixtures/reference/*.yaml`); PDF metni ve sayfa görüntülerinden Claude tarafından çıkarıldı, **kullanıcı onayı bekliyor**.

## §41 GUI

- Teknoloji: tkinter + ttk (ek bağımlılık yok) (Faz 13).
- Kapsam seçenekleri: Otomatik, Her PDF ayrı, Tek PDF, Seçili grup, Tüm koleksiyon (§41.1'deki üç seçeneğe §21.1 ile uyum için iki ek) (Faz 13).
