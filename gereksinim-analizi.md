# Gereksinim Analizi

## 1. Proje Adı

**Yerel Akademik PDF İşleme, Markdown Dönüştürme ve Bilimsel Bilgi Çıkarım Sistemi**

## 2. Amaç

Bu sistem, kullanıcının belirttiği bir klasördeki bilimsel PDF dosyalarını tamamen yerel ortamda işler. Kullanıcı bir prompt ile ne istediğini söyler, sistem de bu isteğin cevabını her PDF için bir Markdown dosyası olarak üretir.

Sistemin yapabilmesi gerekenler:

1. PDF metin katmanını güvenilir şekilde çıkarmak
2. Tablo, formül, şekil, diyagram ve algoritma gibi karmaşık içerikleri gerektiğinde görsel model ile işlemek
3. Taranmış sayfalarda OCR uygulamak
4. Kullanıcı promptunda istenen bilgileri (özet, veri seti, yöntem, sonuçlar, formüller vb.) PDF içeriğine dayanarak üretmek
5. Sayısal sonuçları ve formülleri kaynak sayfa, tablo ve bölüm bilgileriyle izlenebilir kılmak
6. Her PDF için tek bir `<pdf_adı>.md` içerik dosyası üretmek
7. Birden fazla makaleyi birlikte analiz eden koleksiyon çıktıları üretmek
8. Çok sayıda PDF'yi toplu işlemek ve yarıda kalan işlemi kaldığı yerden sürdürmek
9. İşlenen belgelerin durumunu ve temel künye bilgilerini bir özet tablosunda toplamak

Sistem tamamen yerel çalışır. Model altyapısı olarak Ollama kullanılır.

---

## 3. Temel Tasarım Kararları

Bu bölüm belgenin geri kalanını bağlar. Başka bir bölüm bu kararlarla çelişirse bu bölüm geçerlidir.

### 3.1. `A.md` yalnızca prompt cevabını içerir

- `A.pdf` için üretilen `A.md`, kullanıcı promptunun cevabıdır.
- PDF'nin tam Markdown dönüşümü, `A.md`'ye ancak kullanıcı bunu isterse girer. Prompt verilmediğinde kullanılan **varsayılan prompt** tam dönüşüm ister (bkz. §10.3).
- Belge başına kullanıcıya yönelik başka bir içerik dosyası (`summary.md`, `results.md`, `equations.md`, `analysis.json` vb.) üretilmez.

### 3.2. Yapılandırılmış JSON, kullanıcı çıktısı değil iç ara katmandır

Sistem her PDF için şemalı JSON ara dosyaları üretir ve bunları çıktı klasöründeki `_cache/` altında saklar. Bu dosyalar kullanıcıya teslim edilen içerik çıktısı sayılmaz.

Gerekçe:

- **Tekrar kullanım:** PDF ayrıştırma ve görsel model çağrıları pahalıdır. Prompt değiştiğinde PDF yeniden ayrıştırılmaz.
- **Koleksiyon analizi:** Makaleler arası karşılaştırma, belge bazında çıkarılmış yapılandırılmış veriye dayanır.
- **Doğrulama:** Sayısal değerlerin kaynağa karşı kontrol edilmesi yapısal veri gerektirir.
- **Gelecek:** Embedding, semantik arama ve RAG aşamaları aynı veriyi kullanır.
- **Hata ayıklama:** Model çıktılarının nereden geldiği incelenebilir.

### 3.3. CSV sabit sütunlu bir envanter tablosudur

`papers_summary.csv` promptun içeriğine bağlı değildir. Her belge için işlem durumu ve temel künye bilgilerini içerir. Analitik sütunlar (veri seti, en iyi model, accuracy vb.) yalnızca yapılandırmada açıkça istenirse eklenir (bkz. §22).

Gerekçe: Sütunları prompta bağlamak, farklı promptlarla yapılan çalıştırmalarda tablonun tutarsız olmasına yol açar.

---

## 4. Kapsam

### 4.1. Kapsama Dahil Olan İşlevler

- Belirtilen klasördeki PDF dosyalarını otomatik bulma, isteğe bağlı olarak alt klasörleri de tarama
- Tek PDF dosyasının doğrudan işlenmesi
- PyMuPDF ile metin, blok, satır, span, font ve koordinat bilgisi çıkarımı
- Sayfa türü sınıflandırması (metin tabanlı, karma, taranmış)
- Taranmış sayfalarda Tesseract tabanlı yerel OCR
- Tablo, formül, şekil, grafik ve algoritma adaylarının tespiti
- Görsel bölgelerin kırpılması ve `minicpm-v4.5:8b` ile analizi
- Tabloların Markdown veya gerektiğinde HTML tablo olarak çıkarılması
- Formüllerin LaTeX olarak çıkarılması
- Şekillerin orijinal görselleriyle `assets/` altına kaydedilmesi
- Kullanıcı promptunun yorumlanıp işleme planına dönüştürülmesi
- Yerel metin LLM'i ile promptun cevaplanması (ilk sürümde `gemma4:latest`, yapılandırmadan değiştirilebilir)
- Belge başına tek `<pdf_adı>.md` üretimi
- Grup veya koleksiyon düzeyinde karşılaştırmalı analiz
- Hash tabanlı durum yönetimi, önbellek ve resume
- Hatalı belgelerin işaretlenmesi ve batch'in devam etmesi
- Toplu envanter tablosu (`papers_summary.csv`)

### 4.2. Kapsam Dışı İşlevler (İlk Sürüm)

- Bulut tabanlı LLM kullanımı
- Uzak Ollama sunucusu
- İnternet tabanlı makale doğrulama ve DOI üzerinden metadata zenginleştirme
- Referans ağı ve atıf sayısı analizi
- Embedding, semantik arama ve RAG (bkz. §39)
- Web arayüzü
- Çok kullanıcılı kullanım
- PDF dosyalarının düzenlenmesi veya değiştirilmesi

---

## 5. Terimler

| Terim | Anlamı |
|---|---|
| **Prompt** | Kullanıcının çıktıda ne istediğini doğal dille belirttiği metin |
| **Varsayılan prompt** | Prompt verilmediğinde kullanılan, tam yapısal Markdown dönüşümü isteyen yerleşik prompt |
| **İşleme planı** | Promptun yorumlanmasıyla oluşan yapı: kapsam, hedef dosyalar, istenen alanlar, gereken işlemler, çıktı biçimi |
| **İçerik çıktısı** | Kullanıcıya teslim edilen Markdown dosyası (`A.md` veya koleksiyon Markdown'ı) ve bu dosyanın referansladığı `assets/` görselleri |
| **Ara önbellek** | `_cache/` altındaki JSON, ham model yanıtı ve render dosyaları. İçerik çıktısı sayılmaz |
| **Kanıt (evidence)** | Bir bilginin PDF'deki kaynağı: dosya, sayfa, bölüm, tablo/şekil, bounding box, çıkarım yöntemi |

---

## 6. Kullanım Senaryosu ve Çıktı Yapısı

### 6.1. Giriş

```text
D:\papers\
├── article_001.pdf
├── article_002.pdf
└── fatigue\
    └── article_003.pdf
```

### 6.2. Çıktı

`--output` belirtilmezse çıktı klasörü, giriş klasörünün yanında `<giriş_klasörü_adı>_output` olarak oluşturulur. Örnek: `D:\papers` → `D:\papers_output`.

```text
D:\papers_output\
│
├── article_001\
│   ├── article_001.md              ← prompt cevabı (tek içerik dosyası)
│   └── assets\                     ← yalnızca .md tarafından referanslanan görseller
│       ├── figures\
│       ├── tables\
│       └── equations\
│
├── article_002\
│   └── article_002.md
│
├── fatigue\                        ← --recursive ile alt klasör yapısı korunur
│   └── article_003\
│       └── article_003.md
│
├── collections\
│   └── dataset_comparison_20260913-143012.md
│
├── _cache\                         ← iç ara katman, içerik çıktısı değil
│   └── <sha256>\
│       ├── document.json           ← yapısal ayrıştırma + kanıtlar
│       ├── extractions\
│       │   └── <plan_hash>.json    ← şemalı çıkarım sonucu
│       ├── renders\                ← kırpılmış sayfa bölgeleri
│       ├── model_raw\              ← ham görsel/metin model yanıtları
│       └── errors\                 ← parse edilemeyen yanıtlar
│
├── logs\
│   └── process_2026-09-13_143012.log
│
├── processing_state.json
├── papers_summary.csv
└── .lock                           ← aynı anda ikinci bir çalıştırmayı engeller
```

Kurallar:

- Alt klasör yapısı çıktıda korunur. Böylece farklı alt klasörlerdeki aynı adlı PDF'ler çakışmaz.
- `assets/` klasörü yalnızca `A.md` görsel referansı içeriyorsa oluşturulur.
- `_cache/` silinirse sistem doğru çalışmaya devam eder, yalnızca işlemleri yeniden yapar.

---

## 7. Sistem Mimarisi

```text
                     INPUT (klasör veya tek PDF)          PROMPT
                              │                              │
                              ▼                              ▼
                   PDF keşfi / kimlik (SHA-256)      Prompt planlayıcı
                              │                   (kapsam, alanlar, gereken
                              │                    işlemler, çıktı biçimi)
                              ▼                              │
                     State Manager  ◄────────────────────────┤
              pending/processing/completed/...               │
                              │                              │
                         her PDF için                        │
                              │                              │
                   ┌──────────┴──────────┐                   │
                   │  document.json      │ önbellekte varsa  │
                   │  önbellekte mi?     │── atla ──┐        │
                   └──────────┬──────────┘          │        │
                              │ yok                 │        │
                              ▼                     │        │
                           PyMuPDF                  │        │
               ┌──────────────┼──────────────┐      │        │
               ▼              ▼              ▼      │        │
          metin katmanı   görsel tespit    OCR      │        │
               │              │         (taranmış)  │        │
               │         MiniCPM-V 4.5       │      │        │
               │      tablo/formül/şekil     │      │        │
               └──────────────┼──────────────┘      │        │
                              ▼                     │        │
                     _cache/<sha>/document.json ◄───┘        │
                              │                              │
                              ▼                              │
                Gemma 4: plana göre çıkarım  ◄───────────────┘
                              │
                              ▼
                  Kanıt doğrulama (sayı, kaynak, LaTeX)
                              │
               ┌──────────────┴───────────────┐
               ▼                              ▼
     document kapsamı: A.md        collection kapsamı: collections/<ad>.md
               │                              │
               └──────────────┬───────────────┘
                              ▼
                     papers_summary.csv
```

Varsayılan prompt kullanıldığında (tam dönüşüm) Markdown, `document.json`'dan deterministik olarak üretilir ve metin LLM'i çağrılmaz (bkz. §16.3).

---

## 8. PDF Keşfi ve Dosya Kimliği

### 8.1. Keşif

- `--input` bir klasör veya tek bir `.pdf` dosyası olabilir.
- `.pdf` uzantısı büyük/küçük harfe duyarsız eşleştirilir.
- `--recursive` verilirse alt klasörler taranır.
- `--include` ile glob filtreleri verilebilir (örn. `--include "fatigue/*.pdf"`).
- Dosyalar göreli yola göre alfabetik (deterministik) sırayla işlenir.

### 8.2. Kimlik ve Değişiklik Tespiti

- Dosyanın kimliği içeriğinin **SHA-256** değeridir.
- Dosya boyutu ve son değiştirilme zamanı (mtime) yalnızca hızlı ön kontrol için kullanılır:
  - Boyut ve mtime state'teki kayıtla aynıysa kayıtlı hash kullanılır, dosya yeniden hash'lenmez.
  - Biri farklıysa dosya yeniden hash'lenir.
  - Yeni hash eskisiyle aynıysa (örneğin sadece dosya kopyalanıp mtime değiştiyse) belge **yeniden işlenmez**, yalnızca boyut/mtime kaydı güncellenir.
- Aynı içeriğe sahip farklı adlı iki PDF, `_cache/<sha256>` önbelleğini paylaşır. Her birinin kendi çıktı dosyası ayrıca üretilir.

---

## 9. İşlem Durumu, Resume ve Eşzamanlılık

### 9.1. Durumlar

| Durum | Anlamı |
|---|---|
| `pending` | İşlenmeyi bekliyor |
| `processing` | Şu anda işleniyor |
| `completed` | Uyarısız tamamlandı |
| `completed_with_warnings` | Çıktı üretildi ama eksiklik var (OCR yok, görsel model yok, `[unclear]` içerik, boş prompt sonucu vb.) |
| `failed` | Çıktı üretilemedi |
| `skipped` | Değişmediği için veya filtre dışında kaldığı için atlandı |

### 9.2. `processing_state.json` Örneği

```json
{
  "schema_version": "1.0",
  "documents": {
    "fatigue/article_003.pdf": {
      "sha256": "abc123...",
      "size_bytes": 1843022,
      "mtime": "2026-09-01T10:22:31",
      "status": "completed_with_warnings",
      "warnings": ["ocr_unavailable: page 4"],
      "plan_hash": "9f1e...",
      "prompt_sha256": "71ab...",
      "models": {
        "text": {"name": "gemma4:latest", "digest": "sha256:..."},
        "vision": {"name": "minicpm-v4.5:8b", "digest": "sha256:..."}
      },
      "output_path": "fatigue/article_003/article_003.md",
      "processing_time_sec": 42.7,
      "attempts": 1,
      "last_run_id": "20260913-143012"
    },
    "article_002.pdf": {
      "sha256": "def456...",
      "status": "failed",
      "error_stage": "vision",
      "error": "MiniCPM timeout after 3 attempts",
      "attempts": 3
    }
  },
  "collections": {}
}
```

### 9.3. Atlama Kuralı

Bir belge ancak aşağıdaki koşulların **hepsi** sağlanırsa `skipped` olur:

- Durumu `completed` veya `completed_with_warnings`
- SHA-256 değişmemiş
- İşleme planı hash'i (prompt + mod + model adları + model digest'leri + ayrıştırıcı sürümü) değişmemiş
- Çıktı dosyası mevcut ve boş değil

Koşullardan biri sağlanmazsa belge yeniden işlenir. Önbellekteki geçerli ara dosyalar tekrar kullanılır. Prompt değiştiyse `A.md` atomik olarak yeniden yazılır. Önceki prompt ve plan bilgisi state kaydında `history` altında korunur.

### 9.4. Yeniden Başlatma

- `processing` durumunda kalmış kayıtlar başlangıçta `pending` durumuna alınır ve deneme sayısı korunur.
- `failed` kayıtlar varsayılan olarak yeniden denenmez. `--retry-failed` bayrağı veya `processing.retry_failed: true` ile denenir.
- `--force` tüm koşulları yok sayar ve ara önbelleği kullanmadan yeniden işler.

### 9.5. Eşzamanlılık ve Atomiklik

- Çıktı klasöründeki `.lock` dosyası, aynı çıktı klasörü üzerinde ikinci bir çalıştırmayı engeller. Kilidi tutan süreç artık yaşamıyorsa kilit bayat kabul edilir, uyarıyla kaldırılır.
- State dosyası geçici dosyaya yazılıp atomik yeniden adlandırma ile güncellenir.
- Tüm çıktı dosyaları (`.md`, `.json`, `.csv`) aynı atomik yöntemle yazılır. Yarım dosya tamamlanmış kabul edilmez.
- Bir belge aynı anda yalnızca bir worker tarafından işlenir.

---

## 10. Prompt ve İşleme Planı

### 10.1. Prompt Kaynakları

Öncelik sırası (yüksekten düşüğe):

1. `--prompt "..."`
2. `--prompt-file prompt.md`
3. `config.yaml` içindeki `prompt` veya `prompt_file`
4. Yerleşik varsayılan prompt

### 10.2. İşleme Planı

Prompt önce metin LLM'i ile yapılandırılmış bir işleme planına dönüştürülür. Plan Pydantic şemasıyla doğrulanır:

```json
{
  "schema_version": "1.0",
  "scope": "document",
  "targets": {"include": ["*.pdf"]},
  "requested_fields": ["title", "dataset.name", "methodology.models", "results.best"],
  "needs": {"tables": true, "equations": false, "figures": false, "full_text": false},
  "comparison_dimensions": [],
  "output_language": "tr",
  "output_outline": ["Başlık", "Veri Seti", "Yöntem", "En İyi Sonuçlar", "Tablolar"]
}
```

Kurallar:

- CLI'da `--scope` veya `--include` açıkça verilmişse, plandaki karşılık gelen alanlar bu değerlerle **değiştirilir**. Planlayıcı yalnızca açık belirtilmeyen alanları doldurur.
- `--plan-only` verilirse plan ekrana yazdırılır ve PDF işlenmez.
- Plan, `plan_hash` ile birlikte log'a ve state kaydına yazılır.
- Plan şemaya uymuyorsa bir kez yeniden denenir. Yine başarısız olursa varsayılan prompt planı kullanılır ve uyarı verilir.
- `needs` alanı gereksiz model çağrılarını önler. Örneğin prompt formül istemiyorsa formül çıkarımı için görsel model çağrılmaz. Ancak metnin doğru okunması için gereken görsel işlemler (taranmış sayfa, bozuk metin) `needs` değerinden bağımsız olarak yapılır.

### 10.3. Varsayılan ve Boş Prompt

- **Prompt hiç verilmezse:** Varsayılan prompt kullanılır. Bu prompt belgenin tam yapısal Markdown dönüşümünü ister. Durum bilgi seviyesinde loglanır, uyarı sayılmaz.
- **Prompt boş string veya yalnızca boşluk ise:** Varsayılan prompt kullanılır ve belge `completed_with_warnings` olarak işaretlenir.
- **Prompt sonucu boşsa** (örneğin istenen bilgi hiçbir yerde yok): `A.md` yine oluşturulur, istenen her başlık altına `not_found` yazılır ve belge `completed_with_warnings` olur.

### 10.4. Promptun Sınırları

- Prompt, "PDF'de olmayan bilgiyi üretmeme" ve "okunamayan değeri tahmin etmeme" kurallarını geçersiz kılamaz.
- PDF metni modele **veri** olarak verilir. PDF içinde geçen talimat benzeri ifadeler (prompt injection) sistem promptunda açıkça yok sayılır.

### 10.5. Çıktı Dili

- Promptta dil belirtilmişse o dil kullanılır.
- Belirtilmemişse promptun yazıldığı dil kullanılır.
- Varsayılan prompt (tam dönüşüm) belgenin kendi dilini korur ve çeviri yapmaz.

---

## 11. PDF İşleme

### 11.1. Metin Katmanı

PDF önce PyMuPDF ile okunur (`page.get_text("dict")`, gerektiğinde `"rawdict"`).

Her sayfa için çıkarılan bilgiler:

- Sayfa numarası (1 tabanlı)
- Metin blokları, satırlar, span'ler
- Font adı, font boyutu, kalın/italik bilgisi
- Bounding box
- Görsel bloklar ve alanları

### 11.2. Sayfa Sınıflandırması

Her sayfa için metin karakter sayısı, metin blok sayısı ve görsel alan oranı (görsel blok alanı / sayfa alanı) hesaplanır.

| Sınıf | Kural (varsayılan eşikler yapılandırılabilir) |
|---|---|
| `text` | Karakter sayısı ≥ `min_text_chars` (100) ve görsel alan oranı < `mixed_image_ratio` (0.3) |
| `mixed` | Karakter sayısı ≥ `min_text_chars` ve görsel alan oranı ≥ `mixed_image_ratio` |
| `scanned` | Karakter sayısı < `min_text_chars` ve görsel alan oranı ≥ `scanned_image_ratio` (0.5) |

`scanned` sınıfındaki sayfalarda mevcut metin katmanı atılmaz. OCR sonucuyla birleştirilir (§11.4).

### 11.3. Okuma Sırası

- Bloklar bounding box'lara göre sütunlara ayrılır. Sütunlar soldan sağa, her sütun içindeki bloklar üstten alta sıralanır.
- Sayfa genişliğini kaplayan bloklar (başlık, tam genişlik şekil/tablo) sütun sıralamasını böler ve kendi dikey konumlarında yer alır.
- Sütun tespiti belirsizse (örneğin bloklar birden fazla sütun sınırını kesiyorsa) sayfa `reading_order_uncertain` olarak işaretlenir. BALANCED ve FULL modlarında görsel analize gönderilir.

### 11.4. OCR

- OCR, PyMuPDF'nin Tesseract entegrasyonu (`page.get_textpage_ocr`) ile yapılır. Ek bir Python OCR paketi gerekmez.
- Tesseract çalıştırılabilir dosyası ve `tessdata` dizini başlangıçta kontrol edilir.
- OCR dilleri yapılandırılabilir. Varsayılan `eng` dilidir. Türkçe belgeler için `tur` dil paketi kurulmalıdır.
- OCR metni ile mevcut metin katmanı bounding box örtüşmesine göre birleştirilir. Örtüşen bölgelerde metin katmanı tercih edilir, tekrarlar kaldırılır.
- OCR uygulanan sayfalar `document.json` içinde `source_method: "ocr"` ile işaretlenir.
- Tesseract yoksa taranmış sayfalar görsel modele gönderilir. Görsel model de yoksa sayfa `[unreadable_page]` olarak işaretlenir ve belge `completed_with_warnings` olur.

---

## 12. Görsel İşleme

### 12.1. Model

İlk sürümde `minicpm-v4.5:8b` kullanılır. Model adı yapılandırılabilir.

Görevleri:

- Tablo okuma
- Formül çıkarma
- Şekil başlığı ve şekil türü tespiti
- Karmaşık sayfa düzenini yorumlama
- Metin katmanında bozulmuş içeriği görselden okuma

### 12.2. Aday Tespiti

Tablo, formül ve şekil adayları iki kaynağın birleşimiyle bulunur. Metin göstergeleri tek başına yeterli sayılmaz.

**Metin göstergeleri:**

- `Table`, `TABLE`, `Tablo`
- `Figure`, `Fig.`, `Şekil`
- `Eq.`, `Equation`, `Eqn.`, satır sonunda `(n)` biçiminde numara
- `Algorithm`, `Algoritma`

**Geometrik ve yapısal göstergeler:**

- PyMuPDF `page.find_tables()` sonucu
- Vektör çizim yoğunluğu (`page.get_drawings()`), yatay/dikey çizgi ızgaraları
- Görsel bloklar
- Matematik fontları (örn. CMMI, CMSY, Cambria Math) veya yoğun sembol karakterleri
- Normal metinden belirgin şekilde ayrışan, ortalanmış kısa satırlar

Her aday için şunlar saklanır: tür, sayfa, bounding box, tespit gerekçesi.

### 12.3. Görsel Model Çağırma Kuralları

Görsel model yalnızca aşağıdaki durumlarda çağrılır. Hangi durumların geçerli olduğu moda göre değişir (bkz. §23).

| Tetikleyici | FAST | BALANCED | FULL |
|---|:---:|:---:|:---:|
| `scanned` sayfa ve OCR yok/başarısız | ✓ | ✓ | ✓ |
| Tablo adayı, metin çıkarımı tablo hücrelerini korumuyorsa | – | ✓ | ✓ |
| Formül adayı ve plan formül istiyorsa | – | ✓ | ✓ |
| Şekil adayı ve plan şekil istiyorsa | – | ✓ | ✓ |
| `reading_order_uncertain` | – | ✓ | ✓ |
| Tüm tablo/formül/şekil adayları (plan istemese de) | – | – | ✓ |
| `mixed` ve `scanned` tüm sayfalar, tam sayfa analizi | – | – | ✓ |

"Metin çıkarımı tablo hücrelerini korumuyor" kararı: `find_tables()` tablo bulamamış veya bulunan tablonun satırlarında hücre sayısı tutarsızsa.

### 12.4. Render ve Kırpma

- Sayfalar `page.get_pixmap(dpi=render_dpi)` ile render edilir. Varsayılan değer 250 DPI, izin verilen aralık 150–400 DPI'dır.
- Mümkün olduğunda tam sayfa yerine yalnızca aday bölge kırpılır. Kırpma, bounding box'a `crop_padding_pt` (varsayılan 8 pt) kenar payı eklenerek yapılır.
- Kırpılmış görseller `_cache/<sha>/renders/` altında saklanır ve tekrar kullanılır.

---

## 13. Tablo Çıkarma

İşlem sırası:

1. `page.find_tables()` ile metin katmanından tablo çıkarımı
2. Sonuç tutarlıysa (§12.3) doğrudan kullanılır, `source_method: "text"`
3. Tutarsızsa bölge kırpılır ve görsel modele gönderilir, `source_method: "vision"`
4. Markdown tablosuna dönüştürülür
5. Birleşik hücreler (rowspan/colspan) varsa HTML tablo kullanılır

Örnek:

```markdown
| Model | Accuracy | F1 |
|---|---:|---:|
| Bi-LSTM | 0.99 | 0.99 |
| Bi-GRU | 0.96 | 0.95 |
```

Kurallar:

- Okunamayan hücre `[unclear]` olarak yazılır. Eksik değer tahmin edilmez.
- Görsel modelden gelen tablodaki sayısal değerler, aynı bölgenin metin katmanında da varsa karşılaştırılır. Uyuşmazlık varsa metin katmanı değeri kullanılır ve uyarı loglanır.
- Tablo başlığı (caption) ve tablo numarası saklanır.

---

## 14. Formül Çıkarma

Formüller LaTeX olarak saklanır.

```markdown
$$
\mathrm{SPL} = 20 \log\left(\frac{p}{p_{\mathrm{ref}}}\right)
$$
```

Her formül için saklanan bilgiler (`document.json` içinde):

```json
{
  "id": "eq-3",
  "number": "3",
  "latex": "\\mathrm{SPL} = 20 \\log\\left(\\frac{p}{p_{\\mathrm{ref}}}\\right)",
  "description": "Sound Pressure Level",
  "page": 10,
  "section": "2.3 Acoustic Features",
  "bbox": [72.0, 410.5, 520.2, 446.8],
  "source_method": "vision",
  "latex_valid": true
}
```

`description` alanı yalnızca PDF'de formülün yakınında açıkça geçen bir açıklamadan alınır. Açıklama yoksa `null` olur.

---

## 15. Şekil İşleme

- Şekiller yeniden üretilmez.
- Önce PDF'deki gömülü görsel çıkarılır. Şekil vektör çizimse veya birden fazla görselden oluşuyorsa sayfa bölgesi render edilip kırpılır.
- Dosya adı biçimi: `figure_<numara iki hane>.png`. Numara yoksa `figure_p<sayfa>_<sıra>.png`.
- Saklanan bilgiler: şekil numarası, başlık, sayfa, bounding box, dosya yolu, metin içindeki referansları (`Fig. 3`) geçen paragrafların kimlikleri.
- Görseller `_cache/` altında tutulur. Yalnızca `A.md` bir şekle referans veriyorsa ilgili görsel `assets/figures/` altına kopyalanır:

```markdown
![Figure 3. Proposed pipeline](assets/figures/figure_03.png)
```

---

## 16. Ara Belge Temsili ve Tam Dönüşüm

### 16.1. `document.json`

Her PDF'nin ayrıştırılmış hali tek bir ara dosyada tutulur:

- `schema_version`, `parser_version`, `source` (göreli yol, sha256, sayfa sayısı)
- `pdf_metadata` (PDF'nin kendi metadata alanları)
- `pages[]`: sınıf, okuma sırası belirsizliği, OCR bilgisi
- `blocks[]`: tür (`heading`, `paragraph`, `list`, `table`, `equation`, `figure`, `algorithm`, `caption`, `footnote`, `reference`), sayfa, bbox, metin, `source_method`, başlık seviyesi
- `sections[]`: başlık hiyerarşisi ve her bölümün blok aralığı
- `tables[]`, `equations[]`, `figures[]`
- `warnings[]`

Bu dosya Pydantic şemasıyla doğrulanır. Şema sürümü değişirse eski önbellek geçersiz sayılır.

### 16.2. Başlık Tespiti

Başlıklar font boyutu, kalınlık, numaralandırma kalıbı (`1.`, `2.3`, `II.`) ve bilinen akademik bölüm adları (`Abstract`, `Introduction`, `Method`, `Results`, `Conclusion`, `References` ve Türkçe karşılıkları) birlikte değerlendirilerek belirlenir.

### 16.3. Tam Dönüşüm (Varsayılan Prompt)

Varsayılan prompt kullanıldığında `A.md`, `document.json`'dan **deterministik** olarak üretilir. Metin LLM'i çağrılmaz.

Korunan unsurlar:

- Başlık hiyerarşisi
- Paragraflar, madde işaretli ve numaralı listeler
- Formüller (LaTeX)
- Tablolar
- Şekil referansları
- Algoritmalar (kod bloğu olarak)
- Sayfa işaretleri: `<!-- page: 5 -->` (varsayılan açık, `output.page_markers` ile kapatılabilir)

Üst bilgi/alt bilgi tekrarları (her sayfada tekrarlanan dergi adı, sayfa numarası) tespit edilip çıkarılır.

---

## 17. LLM ile Bilgi Çıkarımı

### 17.1. Model

- İlk sürüm: `gemma4:latest`
- Alternatifler: `qwen3:8b`, `qwen3:14b`
- Model adı yapılandırmadan ve `--model-text` ile değiştirilebilir.
- `latest` gibi değişken etiketlerin yeniden üretilebilirliği bozmaması için, başlangıçta modelin digest değeri Ollama'dan okunur ve state kaydına yazılır. Digest değişirse plan hash'i de değişir.

### 17.2. Uzun Belgeler

- Bağlam uzunluğu `models.text_num_ctx` ile yapılandırılır (varsayılan 16384 token).
- Belge bağlama sığıyorsa tek çağrıda işlenir.
- Sığmıyorsa **bölüm bazlı map-reduce** uygulanır:
  1. Plan hangi alanları istiyorsa, o alanlarla ilgili bölümler seçilir (örn. veri seti için `Method/Dataset`, sonuçlar için `Results`, `Tables`). Seçim bölüm başlıkları ve anahtar kelimelerle yapılır.
  2. Her bölüm parçası ayrı çağrıyla işlenir. Her çağrı kanıtlı kısmi JSON döndürür.
  3. Kısmi sonuçlar birleştirilir. Çelişen değerler silinmez, kanıtlarıyla birlikte `conflicts` altında tutulur.
  4. `A.md`, birleştirilmiş JSON'dan ve gerekirse son bir yazım çağrısıyla üretilir.
- Modele verilen her parçada sayfa işaretleri (`<!-- page: n -->`) ve blok kimlikleri bulunur. Böylece model kaynak gösterebilir.

### 17.3. Alan Kataloğu

Planlayıcının istek ile eşleyebileceği standart alanlar aşağıdadır. Bu liste **zorunlu bir çıktı listesi değildir.** Yalnızca promptta istenen alanlar çıkarılır. Katalogda olmayan istekler `custom` alanı olarak işlenir.

| Grup | Alanlar |
|---|---|
| Künye | başlık, yazarlar, yıl, dergi/konferans, DOI |
| Araştırma | amaç, problem, temel katkılar |
| Veri seti | ad, örnek sayısı, sınıflar, eğitim/doğrulama/test bölünmesi |
| Yöntem | ön işleme, özellikler, özellik seçimi, modeller, hiperparametreler, değerlendirme protokolü |
| Sonuçlar | performans metrikleri, en iyi model, en iyi sonuçlar, karşılaştırmalı sonuçlar, sınıf bazlı sonuçlar |
| Formüller | önemli formüller |
| Değerlendirme | yazarların temel sonucu, sınırlılıklar, gelecek çalışma önerileri |

---

## 18. Yapılandırılmış Çıkarım Şeması

Çıkarım sonucu `_cache/<sha>/extractions/<plan_hash>.json` dosyasına yazılır ve sürümlü bir Pydantic şemasıyla doğrulanır. Kullanıcıya teslim edilmez.

Her değer, kanıtıyla birlikte tutulur:

```json
{
  "schema_version": "1.0",
  "source": {"path": "article_001.pdf", "sha256": "abc123..."},
  "plan_hash": "9f1e...",
  "fields": {
    "bibliographic.title": {
      "value": "Deep Learning Based Fatigue Detection",
      "status": "found",
      "evidence": [{"page": 1, "block_id": "p1-b2", "source_method": "text"}]
    },
    "dataset.sample_count": {
      "value": null,
      "status": "not_found",
      "evidence": []
    }
  },
  "results": [
    {
      "claim": "Bi-LSTM achieved 0.99 accuracy",
      "model": "Bi-LSTM",
      "metric": "accuracy",
      "value": 0.99,
      "evidence": [{"page": 15, "section": "Results and Discussion", "table": "Table 9", "bbox": [70.1, 300.2, 525.0, 480.9], "source_method": "text"}],
      "verification": "verified",
      "confidence": "high"
    }
  ],
  "conflicts": [],
  "warnings": []
}
```

Kurallar:

- `status` değerleri: `found`, `not_found`, `unclear`.
- Bulunamayan bilgi için boş string kullanılmaz. Alanın türüne göre `null` veya `[]` ile birlikte `status: "not_found"` yazılır.
- JSON parse veya şema doğrulama hatasında ham yanıt `_cache/<sha>/errors/` altına kaydedilir ve `llm.max_retries` kadar yeniden denenir. Her denemede modele doğrulama hatası iletilir.

---

## 19. Kanıt, Doğrulama ve Güven

### 19.1. Sayısal Değer Doğrulaması

LLM'in ürettiği her sayısal değer, kanıtında gösterilen kaynak bloğun metninde (veya tablo hücresinde) aranır. Karşılaştırma yapılırken sayı biçimi normalize edilir: `0.99`, `0,99` ve `99%` aynı değer olarak eşleştirilebilir.

| Sonuç | `verification` | Çıktıdaki gösterim |
|---|---|---|
| Kaynakta birebir bulundu | `verified` | Değer normal yazılır |
| Kanıt var ama değer kaynakta bulunamadı | `unverified` | `0.99 [unverified]` |
| Kanıt (sayfa) yok | `source_not_found` | `0.99 [source_not_found]` |

`unverified` ve `source_not_found` değerler toplu karşılaştırmalarda (koleksiyon tabloları, CSV analitik sütunları) kullanılmaz.

### 19.2. Güven Seviyesi

Güven, modelin kendi beyanına göre **belirlenmez.** Kurala dayalı bir kategoridir:

| Seviye | Koşul |
|---|---|
| `high` | `source_method: text` ve `verified` |
| `medium` | `source_method: ocr` veya `vision` ve `verified` |
| `low` | `unverified`, `unclear` veya çelişkili kanıt |

### 19.3. LaTeX Doğrulaması

- Süslü parantez, `\left`/`\right` ve `\begin`/`\end` eşleşmeleri kontrol edilir.
- `pylatexenc` ile ayrıştırılabilirlik kontrol edilir.
- Geçersiz formül yine yazılır, `latex_valid: false` işaretlenir ve çıktıda yanına `[latex_unverified]` eklenir.

### 19.4. İzlenebilirlik Gösterimi

`A.md` içinde önemli iddialar ve sayısal sonuçlar kaynak etiketiyle yazılır:

```markdown
Bi-LSTM modeli %99 accuracy elde etmiştir. *(s. 15, Table 9)*
```

Kaynak etiketi biçimi `output.citation_style` ile ayarlanabilir. Kaynak etiketleri kapatılamaz.

---

## 20. `A.md` İçerik Çıktısı

### 20.1. Dosya Adı

- `A.pdf` → `A.md`. Temel ad ve büyük/küçük harf korunur.
- Windows'ta geçersiz karakterler (`< > : " / \ | ? *` ve kontrol karakterleri) `_` ile değiştirilir.
- Sondaki nokta ve boşluklar kaldırılır.
- Ayrılmış adlara (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`) `_` öneki eklenir.
- Normalizasyon sonrası aynı klasörde çakışma olursa ada `_<sha256'nın ilk 8 karakteri>` eklenir.

### 20.2. Front Matter

`output.front_matter: true` (varsayılan) ise dosyanın başına yeniden üretilebilirlik bilgisi eklenir. Bu bilgi aynı dosyada durduğu için ek dosya sayılmaz:

```markdown
---
source: fatigue/article_003.pdf
sha256: abc123...
generated: 2026-09-13T14:31:55
mode: balanced
prompt_sha256: 71ab...
models: {text: "gemma4:latest@sha256:...", vision: "minicpm-v4.5:8b@sha256:..."}
status: completed_with_warnings
---
```

### 20.3. Gövde

- Başlık yapısı `plan.output_outline` alanını izler.
- Promptta istenen her bilgi kendi başlığı altında yer alır. Bulunamayan bilgi için başlık korunur ve altına `not_found` yazılır.
- Promptta istenmeyen bölüm eklenmez.

### 20.4. Örnek Şablonlar

Aşağıdaki yapılar, prompt ilgili içeriği istediğinde kullanılabilecek **önerilen** düzenlerdir. Zorunlu değildir.

**Kısa akademik özet:**

```markdown
# Kısa Akademik Özet
## Amaç
## Veri Seti
## Yöntem
## Kullanılan Modeller
## Temel Sonuçlar
## Önemli Formüller
## Sınırlılıklar
```

**Sonuçlar:**

```markdown
# Sonuçlar
## En İyi Sonuç
## Model Karşılaştırmaları
## Sınıf Bazlı Sonuçlar
## Önemli Tablolar
```

**Formüller:**

```markdown
# Formüller

## Denklem 1

$$
z = \frac{x-\mu}{s}
$$

Açıklama: Z-score normalizasyonu.
Kaynak: s. 6
```

---

## 21. Koleksiyon İşleme

### 21.1. Kapsamlar

| Kapsam | Anlamı | Çıktı |
|---|---|---|
| `document` | Her seçilen PDF ayrı işlenir | Her PDF için `A.md` |
| `collection` | Seçilen PDF'ler (tüm klasör veya `--include` ile seçilen grup) birlikte analiz edilir | Tek koleksiyon Markdown dosyası |

"Grup" ayrı bir kapsam değildir. `--include` filtresiyle daraltılmış bir `collection` olarak işlenir.

### 21.2. Kapsamın Belirlenmesi

1. `--scope document|collection` verilmişse o kullanılır.
2. Verilmemişse (`auto`):
   - Giriş tek PDF ise → `document`
   - Giriş klasörse ve plan karşılaştırma, sentez, "bu makaleler", "grup" gibi çoklu belge amacı taşıyorsa → `collection`
   - Diğer durumlarda → `document`
3. Seçilen kapsam ve gerekçesi loglanır ve `--plan-only` çıktısında gösterilir.

### 21.3. Desteklenecek İstek Türleri

- "Bu makale grubunu akademik olarak özetle."
- "İlgili makalelerde kullanılan veri setlerini karşılaştır."
- "Çalışmaların özgün yönlerini ve ortak katkılarını çıkar."
- "Kullanılan yöntemleri, modelleri ve performans metriklerini tablo halinde karşılaştır."
- "Sınırlılıkları ve gelecek çalışma önerilerini sentezle."

İstekler bu örneklerle sınırlı değildir.

### 21.4. Akış

1. Plan oluşturulur, hedef PDF'ler seçilir.
2. Her PDF için `document.json` önbellekten alınır veya üretilir.
3. Her PDF için, planın istediği alanlarla belge bazlı çıkarım yapılır (`extractions/<plan_hash>.json`). Bu adımda belge başına `A.md` **üretilmez.**
4. Belge bazlı çıkarımlar birleştirilir. Karşılaştırma boyutlarına göre ortaklıklar ve farklılıklar LLM ile sentezlenir. Sentez girdisi yalnızca doğrulanmış çıkarımlardır, ham PDF metni değildir.
5. Koleksiyon Markdown'ı yazılır.

### 21.5. Çıktı

- Yol: `<output>/collections/<güvenli_ad>_<YYYYMMDD-HHMMSS>.md`
- `<güvenli_ad>`: `--collection-name` verilmişse o, verilmemişse planlayıcının önerdiği kısa ad (en fazla 50 karakter, §20.1 kurallarıyla normalize edilir).
- `--collection-output <yol>` ile tam yol verilebilir. Dosya varsa üzerine yazılmaz, hata verilir.
- Zaman damgası sayesinde prompt değişince önceki koleksiyon çıktısı korunur.

İçerik:

- Front matter (§20.2'deki alanlar ve incelenen PDF'lerin göreli yol + sha256 listesi)
- Kullanılan prompt metni
- Yöntem notu (mod, modeller, işlenen/başarısız belge sayısı)
- Makale bazlı bulgular (tablo veya alt başlıklar)
- Karşılaştırmalı sentez
- Her bulgu için makale adı ve mümkünse sayfa bilgisi

Eksik bilgi `not_found`, okunamayan bilgi `[unclear]` olarak yazılır. Makaleler arası karşılaştırmada eksik değer tamamlanmaz.

### 21.6. Durum ve Yeniden Çalıştırma

- Koleksiyon kaydı `processing_state.json` → `collections` altında tutulur: seçilen PDF hash'leri, prompt, plan hash'i, model digest'leri, çıktı yolu.
- Aynı plan ve aynı PDF hash'leriyle tekrar çalıştırılırsa sentez atlanır ve mevcut çıktı yolu bildirilir.
- Seçilen PDF'lerden biri değişirse yalnızca o belgenin çıkarımı yenilenir. Sentez yeniden yapılır ve yeni zaman damgalı dosyaya yazılır.
- Başarısız belgeler sentezden çıkarılır ve koleksiyon çıktısında "işlenemeyen belgeler" listesinde gösterilir.

---

## 22. Toplu Envanter Tablosu (`papers_summary.csv`)

### 22.1. Konum ve Güncelleme

- Yol: `<output>/papers_summary.csv`, UTF-8 BOM'lu (Excel uyumu için).
- Her belge tamamlandığında ve çalıştırma sonunda `processing_state.json` ile `_cache` verilerinden atomik olarak yeniden üretilir.
- State dosyasındaki tüm belgeleri içerir. Çıktı klasöründe hiç çalışmamış belgeler de dahil edilir (son durumlarıyla).
- `output.save_xlsx: true` ise aynı içerik `papers_summary.xlsx` olarak da yazılır (`openpyxl` gerekir).

### 22.2. Sabit Sütunlar

| Sütun | Açıklama |
|---|---|
| `relative_path` | Giriş klasörüne göre PDF yolu |
| `filename` | PDF dosya adı |
| `sha256` | İçerik hash'i |
| `status` | Son işlem durumu |
| `pages` | Sayfa sayısı |
| `scanned_pages` | Taranmış sınıfındaki sayfa sayısı |
| `ocr_pages` | OCR uygulanan sayfa sayısı |
| `vision_calls` | Görsel model çağrı sayısı |
| `text_llm_calls` | Metin model çağrı sayısı |
| `warnings_count` | Uyarı sayısı |
| `error_stage` | Hata aşaması (`discovery`, `parse`, `ocr`, `vision`, `llm`, `validation`, `write`) |
| `error_message` | Kısa hata mesajı |
| `output_path` | Son içerik çıktısının göreli yolu |
| `prompt_sha256` | Son kullanılan prompt hash'i |
| `processing_time_sec` | Toplam süre |
| `processed_at` | Son işlem zamanı |
| `title` | Makale başlığı |
| `authors` | Yazarlar (`;` ile ayrılmış) |
| `year` | Yayın yılı |
| `venue` | Dergi veya konferans |
| `doi` | DOI |

### 22.3. Künye Sütunlarının Çıkarımı

Künye bilgileri prompttan bağımsız olarak **her belge için** çıkarılır. Maliyeti düşük tutmak için sıra şöyledir:

1. PDF metadata alanları
2. İlk sayfa metninde düzenli ifade ile DOI araması
3. Eksik kalan alanlar için ilk sayfa (en fazla ilk 2 sayfa) üzerinde tek bir kısa LLM çağrısı

Bulunamayan değer boş bırakılır.

### 22.4. İsteğe Bağlı Analitik Sütunlar

`summary.extra_fields` yapılandırmasında §17.3 kataloğundan alanlar listelenirse, bu alanlar her belge için prompttan bağımsız olarak çıkarılır ve CSV'ye sütun olarak eklenir. Örnek: `dataset.name`, `results.best_model`, `results.best_accuracy`, `results.best_f1`. Varsayılan liste boştur.

Yalnızca `verified` değerler yazılır. Diğer değerler için hücre boş bırakılır.

### 22.5. Özet Sayılar

Başarılı, uyarılı, başarısız ve atlanan belge sayıları CSV satırı olarak **eklenmez.** Bu sayılar:

- Çalıştırma sonunda konsola yazılır,
- Log dosyasının son bölümüne yazılır,
- `processing_state.json` → `runs[<run_id>]` altında saklanır.

---

## 23. Çalışma Modları

| Mod | Amaç | Görsel model kullanımı |
|---|---|---|
| `fast` | Hızlı çıkarım | Yalnızca OCR'nin başarısız olduğu/olmadığı taranmış sayfalarda |
| `balanced` (varsayılan) | Kalite/hız dengesi | §12.3'teki BALANCED tetikleyicileri |
| `full` | Taranmış PDF'ler, yüksek doğruluk | §12.3'teki FULL tetikleyicileri |

Kullanılan mod, plan hash'ine dahil edilir. Her görsel model çağrısı hangi tetikleyiciyle yapıldığını loglar. Böylece modların çağrı kapsamı loglarda ayırt edilebilir.

---

## 24. Komut Satırı Arayüzü

```cmd
.venv\Scripts\python.exe process_papers.py --input "D:\papers" --output "D:\papers_output" --prompt "Başlık, veri seti, yöntem ve en iyi sonuçları çıkar."
```

Kısa kullanım (giriş konumsal argüman olarak verilir, çıktı `D:\papers_output` olur, varsayılan prompt kullanılır):

```cmd
.venv\Scripts\python.exe process_papers.py "D:\papers"
```

| Seçenek | Açıklama | Varsayılan |
|---|---|---|
| `--input`, konumsal | Klasör veya tek PDF | – (zorunlu) |
| `--output` | Çıktı klasörü | `<giriş>_output` |
| `--config` | Yapılandırma dosyası | `./config.yaml` (varsa) |
| `--prompt` | Prompt metni | – |
| `--prompt-file` | Prompt dosyası | – |
| `--scope` | `auto`, `document`, `collection` | `auto` |
| `--include` | Glob filtresi, tekrarlanabilir | tümü |
| `--collection-name` | Koleksiyon çıktı adı | planlayıcı önerisi |
| `--collection-output` | Koleksiyon çıktı tam yolu | – |
| `--mode` | `fast`, `balanced`, `full` | `balanced` |
| `--recursive` | Alt klasörleri tara | kapalı |
| `--retry-failed` | Başarısız belgeleri yeniden dene | kapalı |
| `--force` | Önbelleği ve atlama kuralını yok say | kapalı |
| `--plan-only` | Planı göster, işleme yapma | kapalı |
| `--model-vision` | Görsel model adı | `minicpm-v4.5:8b` |
| `--model-text` | Metin model adı | `gemma4:latest` |
| `--dpi` | Render DPI | 250 |
| `--cpu-workers` | PDF ayrıştırma worker sayısı | 4 |
| `--log-level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |

Öncelik: CLI > `config.yaml` > yerleşik varsayılanlar.

Çıkış kodları:

| Kod | Anlamı |
|---|---|
| 0 | Tüm belgeler `completed`, `completed_with_warnings` veya `skipped` |
| 1 | En az bir belge `failed` |
| 2 | Başlangıç kontrolü başarısız (bağımlılık, Ollama, model, yol, kilit, disk) |

---

## 25. Yapılandırma Dosyası

```yaml
input_dir: "D:/papers"
output_dir: "D:/papers_output"
mode: balanced
recursive: false
include: []

prompt: null
prompt_file: null

ollama:
  endpoint: "http://127.0.0.1:11434"
  timeout_sec: 300
  max_retries: 3
  retry_backoff_sec: 5
  keep_alive: "10m"

models:
  vision: "minicpm-v4.5:8b"
  text: "gemma4:latest"
  text_num_ctx: 16384
  max_output_tokens: 4096
  vision_required: true      # false: görsel model yoksa uyarıyla devam et

pdf:
  render_dpi: 250
  crop_padding_pt: 8
  min_text_chars: 100
  mixed_image_ratio: 0.3
  scanned_image_ratio: 0.5

ocr:
  enabled: true
  languages: ["eng"]
  tesseract_path: null       # null: PATH üzerinden bulunur

processing:
  retry_failed: false
  cpu_workers: 4
  llm_workers: 1
  min_free_disk_mb: 1024

output:
  front_matter: true
  page_markers: true
  citation_style: "(s. {page}{table_or_figure})"
  save_xlsx: false

summary:
  extra_fields: []

logging:
  level: INFO
  log_model_content: false
```

Bilinmeyen anahtarlar ve geçersiz değerler başlangıçta hata olarak bildirilir (Pydantic ile doğrulanır).

---

## 26. Başlangıç Kontrolleri

PDF işleme başlamadan önce aşağıdaki kontroller sırayla yapılır. Kritik bir kontrol başarısız olursa çıkış kodu 2 ile sonlanılır.

| Kontrol | Başarısızlıkta |
|---|---|
| Python ≥ 3.11 | Hata |
| Sanal ortam içinde çalışılıyor mu | Uyarı ve doğru komut önerisi |
| Python bağımlılıkları import edilebiliyor mu | Hata, eksik paket ve `pip install` komutu |
| `config.yaml` geçerli mi | Hata |
| Giriş yolu var ve okunabilir mi | Hata |
| Çıktı yolu giriş klasörünün içinde değil mi | Hata |
| `.lock` kilidi | Hata (aktif başka çalıştırma varsa) |
| Boş disk alanı ≥ `min_free_disk_mb` | Hata |
| Ollama endpoint erişilebilir ve loopback adresi mi | Hata |
| Metin modeli kurulu mu | Hata ve `ollama pull <model>` komutu |
| Görsel modeli kurulu mu | `fast` modunda veya `vision_required: false` ise uyarı. Diğer durumlarda hata ve `ollama pull` komutu |
| Tesseract ve dil paketleri | `ocr.enabled: true` ise uyarı (taranmış sayfalar görsel modele yönlendirilir) |
| GPU erişimi (Ollama `ps`/sistem bilgisi) | Uyarı, bilgi loglanır |

Örnek mesaj:

```text
Required model not found: minicpm-v4.5:8b
Run:
  ollama pull minicpm-v4.5:8b
```

Model adları, digest'leri ve GPU bilgisi log dosyasına yazılır. Kodda sabit tutulmaz.

---

## 27. Paralel İşleme ve Kaynak Yönetimi

- PDF ayrıştırma ve render: `cpu_workers` (varsayılan 4) süreç.
- Model çağrıları: `llm_workers` (varsayılan 1). Görsel ve metin modeli çağrıları tek bir kuyruktan geçer. Varsayılan olarak aynı anda birden fazla model çağrısı yapılmaz.
- Model geçişlerindeki yükleme gecikmesini azaltmak için çağrılar gruplanır. Bir belgenin tüm görsel çağrıları, metin çağrılarından önce tamamlanır.
- `llm_workers > 1` ayarlanırsa başlangıçta boş VRAM okunur. İki modelin toplam boyutu boş VRAM'i aşıyorsa `llm_workers` 1'e düşürülür ve uyarı verilir.

Amaç: VRAM taşmasını önlemek, model yükleme gecikmesini azaltmak, kararlılığı artırmak.

---

## 28. Hata Yönetimi

| Hata | Aşama | Davranış |
|---|---|---|
| Bozuk PDF | `parse` | `failed`, sonraki PDF'ye geç |
| Şifreli PDF | `parse` | Boş parola ile açılmayı dene. Açılmazsa `failed` |
| PyMuPDF okuma hatası (tek sayfa) | `parse` | Sayfa atlanır, `completed_with_warnings` |
| Ollama erişilemiyor (çalışma sırasında) | `vision`/`llm` | `max_retries` kadar backoff ile dene. Yine başarısızsa belge `failed` olur ve batch **durdurulur** (sonraki belgeler de başarısız olacağı için); durum kaydedilir |
| Model timeout | `vision`/`llm` | Yeniden dene. Yine başarısızsa: görsel çağrı için bölge `[unclear]` + uyarı; metin çağrısı için belge `failed` |
| Görsel işleme hatası | `vision` | Bölge `[unclear]`, `completed_with_warnings` |
| JSON parse / şema hatası | `validation` | Ham yanıt kaydedilir, yeniden denenir (§18). Yine başarısızsa `failed` |
| Disk yazma hatası | `write` | `failed`. Aynı hata tekrarlanırsa batch durdurulur |
| Yetersiz disk alanı | `write` | Her belgeden önce kontrol edilir. Yetersizse batch durdurulur, durum kaydedilir |

Tek bir PDF'ye özgü hatalar batch'i durdurmaz. Sistem genelindeki hatalar (Ollama tamamen kapalı, disk dolu) batch'i güvenli şekilde durdurur. Tekrar başlatıldığında §9.4'e göre devam edilir.

Her hata kaydı şunları içerir: kaynak dosya, aşama, hata türü, mesaj, deneme numarası.

---

## 29. Günlükleme

- Yol: `<output>/logs/process_<YYYY-MM-DD_HHMMSS>.log`. Her çalıştırma yeni bir dosya açar.
- Konsolda `tqdm` ile ilerleme gösterilir. Ayrıntılar log dosyasına yazılır.

Belge başına kaydedilenler:

- İşlenen PDF, başlangıç/bitiş zamanı, süre, sayfa sayısı ve sayfa sınıfları
- OCR, görsel model ve metin model çağrı sayıları
- Uyarılar, hatalar, sonuç durumu

Model çağrısı başına kaydedilenler:

- Model adı, tetikleyici (§12.3), sayfa/bölge, giriş boyutu (token veya piksel), süre, deneme numarası, başarısızlık nedeni

PDF içeriği ve model yanıtlarının tamamı varsayılan olarak loglanmaz (`logging.log_model_content: false`).

Çalıştırma sonunda log'a ve konsola şu özet yazılır: toplam, `completed`, `completed_with_warnings`, `failed`, `skipped` sayıları ve toplam süre.

---

## 30. Performans

1. Görsel model tüm sayfalarda çalıştırılmaz. Yalnızca §12.3 tetikleyicilerinde çalışır.
2. Metin katmanı olan sayfalarda PyMuPDF önceliklidir.
3. Görsel modele mümkün olduğunda yalnızca kırpılmış bölge verilir.
4. `document.json`, render'lar ve çıkarımlar hash tabanlı önbellekte tutulur.
5. Prompt değiştiğinde PDF yeniden ayrıştırılmaz. Yalnızca çıkarım ve yazım adımları tekrarlanır.
6. Varsayılan prompt (tam dönüşüm) metin LLM'i çağırmaz.

Süre hedefleri ilk sürümde sabitlenmez. §38'deki test setinde mod bazında sayfa başına ortalama süre ölçülür ve README'de raporlanır.

---

## 31. Güvenilirlik Kuralları

- Sayısal değerler tahmin edilmez.
- Okunamayan içerik `[unclear]`, bulunamayan bilgi `not_found` olarak işaretlenir.
- PDF'de bulunmayan akademik bilgi üretilmez.
- Sayısal değerler kaynağa karşı doğrulanır (§19.1).
- Tüm JSON ara dosyaları şemayla doğrulanır.
- Formüller LaTeX açısından kontrol edilir (§19.3).
- Güven seviyesi kurala dayalıdır, model beyanına dayanmaz (§19.2).

---

## 32. Güvenlik, Gizlilik ve Orijinal Dosya Koruma

### 32.1. Yerel Çalışma

- PDF dosyaları ve içerikleri bilgisayardan dışarı gönderilmez.
- Ollama endpoint'i yalnızca loopback adresi (`127.0.0.1`, `localhost`, `::1`) olabilir. Başka bir adres yapılandırılırsa başlangıçta hata verilir.
- Uygulama çalışma sırasında internete erişmez.

### 32.2. Orijinal Dosyalar

Giriş klasörü hiçbir durumda değiştirilmez. Sistem:

- PDF'yi silmez, adını değiştirmez, üzerine yazmaz
- PDF'ye metadata eklemez
- Giriş klasörüne hiçbir dosya (kilit, önbellek, log dahil) yazmaz

PDF'ler salt okunur modda açılır.

### 32.3. Yol Güvenliği

- Tüm yollar mutlak ve normalize hale getirilir.
- Çıktı klasörü giriş klasörünün içindeyse (veya ikisi aynıysa) başlangıçta hata verilir.
- Üretilen her çıktı yolunun çıktı klasörü altında kaldığı doğrulanır (path traversal engellenir).
- `--collection-output` ile verilen yol da çıktı klasörü dışında olabilir, ancak giriş klasörünün içinde olamaz.

---

## 33. Modüler Yapı

```text
src/
├── cli.py                  # argüman ayrıştırma, çıkış kodları
├── config.py               # config yükleme ve Pydantic doğrulama
├── preflight.py            # başlangıç kontrolleri (§26)
├── pdf_discovery.py        # keşif, filtre, hash
├── state_manager.py        # durum, kilit, atomik yazım
├── cache_manager.py        # _cache yönetimi ve geçersiz kılma
├── pdf_parser.py           # PyMuPDF metin/blok çıkarımı
├── page_classifier.py      # sayfa sınıfları
├── layout_analyzer.py      # okuma sırası, başlık tespiti
├── ocr.py                  # Tesseract entegrasyonu
├── visual_detector.py      # tablo/formül/şekil adayları
├── vision_client.py        # görsel model çağrıları
├── llm_client.py           # metin model çağrıları, kuyruk
├── table_extractor.py
├── equation_extractor.py
├── figure_extractor.py
├── document_model.py       # document.json şeması
├── prompt_planner.py       # prompt → işleme planı
├── llm_extractor.py        # plan bazlı çıkarım, map-reduce
├── schemas.py              # extraction, plan, state şemaları
├── evidence_verifier.py    # sayı ve LaTeX doğrulama, güven
├── markdown_builder.py     # tam dönüşüm ve prompt cevabı yazımı
├── collection_analyzer.py  # koleksiyon sentezi
├── summary_writer.py       # CSV/XLSX
├── batch_processor.py      # iş akışı orkestrasyonu
└── logger.py
```

Model istemcileri (`vision_client`, `llm_client`) arayüz üzerinden kullanılır. Böylece model değişikliği diğer modülleri etkilemez.

---

## 34. Python Sanal Ortam ve Bağımlılık Yönetimi

### 34.1. Sanal Ortam

- Uygulama proje kökündeki `.venv` sanal ortamında çalışır.
- Windows'ta `.venv\Scripts\python.exe`, Linux/macOS'ta `.venv/bin/python` kullanılır.
- Global Python paketlerine bağımlılık bulunmaz.
- Python sürümü 3.11 veya üzeri olmalıdır. Desteklenmeyen sürüm başlangıçta anlaşılır biçimde bildirilir.
- Uygulama sanal ortam dışından çalıştırılırsa bunu algılar ve doğru komutu gösterir.
- `.gitignore` içinde `.venv/`, `__pycache__/`, `.pytest_cache/` ve test çıktı klasörleri bulunur.

### 34.2. Bağımlılıklar

- Çalışma bağımlılıkları `requirements.txt` içinde sabit sürümlerle (`==`) tutulur.
- Geliştirme ve test bağımlılıkları `requirements-dev.txt` içinde tutulur.
- Başlangıçta zorunlu paketlerin import kontrolü yapılır.
- OCR etkinse Tesseract çalıştırılabilir dosyası ve dil paketleri ayrıca kontrol edilir. Tesseract Python paketi değildir, sisteme ayrıca kurulur.
- Ollama modelleri sanal ortama kurulmaz. Ollama servisinde bulunmalı ve başlangıçta kontrol edilmelidir.

Zorunlu paketler:

```text
pymupdf
ollama
pydantic
pyyaml
pandas
tqdm
pillow
pylatexenc
```

İsteğe bağlı paketler:

```text
openpyxl     # papers_summary.xlsx
rich         # gelişmiş konsol çıktısı
```

Geliştirme paketleri:

```text
pytest
```

### 34.3. Kurulum

Windows:

```cmd
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe process_papers.py --input "D:\papers"
```

Linux/macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python process_papers.py --input ~/papers
```

README; Windows ve Linux/macOS kurulumlarını, Tesseract kurulumunu ve `ollama pull` komutlarını ayrı ayrı içerir.

---

## 35. Teknoloji Yığını

| Bileşen | Teknoloji |
|---|---|
| Programlama dili | Python 3.11+ |
| PDF motoru | PyMuPDF |
| OCR | Tesseract (PyMuPDF entegrasyonu ile) |
| Görsel model | MiniCPM-V 4.5 8B |
| Metin modeli | Gemma 4 |
| Model servisi | Ollama (yerel) |
| Ara veri | JSON (Pydantic şemalı) |
| İçerik çıktısı | Markdown |
| Envanter tablosu | CSV (isteğe bağlı XLSX) |
| Yapılandırma | YAML |
| LaTeX doğrulama | pylatexenc |
| Loglama | Python logging |
| Test | pytest |

---

## 36. Geliştirme Ortamı Envanteri

Belge hazırlanırken bilgisayarda aşağıdaki Ollama modelleri kurulu olarak tespit edilmiştir:

| Model | Ollama kimliği | Durum | Kullanım |
|---|---|---|---|
| MiniCPM-V 4.5 | `minicpm-v4.5:8b` | Kurulu | Görsel, tablo, formül ve karmaşık sayfa analizi |
| Gemma 4 | `gemma4:latest` | Kurulu | Prompt planlama, bilgi çıkarımı, sentez |
| Nomic Embed Text | `nomic-embed-text:latest` | Kurulu | Gelecekte embedding ve semantik arama (ilk sürümde kullanılmaz) |

| Özellik | Değer |
|---|---|
| GPU | NVIDIA RTX 4500 Ada Generation |
| Toplam VRAM | 24.570 MiB (yaklaşık 24 GB) |
| NVIDIA sürücüsü | 537.42 |

Bu envanter yalnızca başlangıç ortamını tanımlar. Uygulama bu bilgileri çalışma anında yeniden okur (§26) ve kodda sabit tutmaz.

---

## 37. Geliştirme Aşamaları

### Aşama 1: Temel ayrıştırma ve tam dönüşüm

- `.venv`, `requirements.txt`, `config.py`, `preflight.py` (Ollama hariç)
- Keşif, hash, state, kilit, atomik yazım
- PyMuPDF metin çıkarımı, sayfa sınıflandırma, okuma sırası, başlık tespiti
- `document.json`
- Varsayılan prompt ile deterministik `A.md`

### Aşama 2: Görsel içerik ve OCR

- Tablo, formül, şekil aday tespiti
- Tesseract OCR
- MiniCPM entegrasyonu, render ve kırpma
- `assets/` yönetimi
- Çalışma modları

### Aşama 3: Prompt tabanlı çıkarım

- Ollama başlangıç kontrolleri
- Prompt planlayıcı, `--plan-only`
- Gemma entegrasyonu, map-reduce
- Çıkarım şeması, kanıt ve sayı doğrulaması
- Prompt cevabı olarak `A.md`

### Aşama 4: Sağlamlık

- Retry, backoff, hata aşamaları
- Resume ve plan hash tabanlı atlama
- Ayrıntılı loglama, çıkış kodları

### Aşama 5: Toplu çıktılar

- `papers_summary.csv` ve künye çıkarımı
- `summary.extra_fields`
- Koleksiyon kapsamı ve sentezi

### Aşama 6: Gelecek

- Embedding, semantik arama, RAG (§39)

---

## 38. Kabul Kriterleri

### 38.1. Test Seti

Kabul testleri `tests/fixtures/` altında en az şu 12 PDF ile yapılır:

- 4 metin tabanlı tek sütunlu makale
- 3 çift sütunlu makale (en az biri tablo ve formül yoğun)
- 2 taranmış PDF
- 1 şifreli PDF
- 1 bozuk PDF
- 1 alt klasörde, başka bir PDF ile aynı ada sahip PDF

Bunlardan 3 makale için elle hazırlanmış referans veri (künye, en az 2 tablo, en az 3 formül, en az 5 sayısal sonuç) bulunur.

### 38.2. İşlevsel Kriterler

1. Klasör ve tek PDF girişi çalışır. `--recursive` ile alt klasörlerdeki PDF'ler bulunur.
2. Her tamamlanan PDF için tam olarak bir `<pdf_adı>.md` üretilir. Belge başına başka içerik dosyası üretilmez (`assets/` görselleri hariç).
3. Aynı adlı iki PDF'nin çıktıları çakışmaz.
4. Prompt verilmediğinde `A.md` belgenin tam yapısal dönüşümüdür ve metin LLM'i çağrılmaz.
5. Prompt verildiğinde `A.md` yalnızca promptta istenen başlıkları içerir. Bulunamayan bilgiler `not_found` olarak yazılır.
6. Boş prompt, varsayılan dönüşümle `completed_with_warnings` sonucu üretir.
7. `--plan-only` PDF işlemeden planı gösterir.
8. Tek PDF + `--scope collection` olmayan bir istek `document` kapsamında çalışır. Klasör + karşılaştırma isteği `collections/` altında tek bir Markdown üretir ve belge başına `A.md` üretmez.
9. Koleksiyon çıktısındaki her bulgu en az makale adıyla, sayısal bulgular sayfa bilgisiyle izlenebilir.
10. Taranmış PDF'lerden OCR veya görsel model ile metin elde edilir.

### 38.3. Sağlamlık Kriterleri

11. Bozuk ve şifreli PDF'ler `failed` olur, hata aşamasıyla kaydedilir ve batch diğer PDF'lerle tamamlanır.
12. İkinci çalıştırmada değişmeyen PDF'ler `skipped` olur ve hiç model çağrısı yapılmaz.
13. İçeriği değişen PDF yeniden işlenir. Sadece mtime'ı değişen PDF işlenmez.
14. Prompt değiştiğinde PDF yeniden ayrıştırılmaz (`document.json` önbellekten gelir), `A.md` yeniden üretilir.
15. İşlem ortasında süreç sonlandırılıp yeniden başlatıldığında yarım dosya bulunmaz ve işlem kaldığı yerden devam eder.
16. Aynı çıktı klasörü için ikinci eşzamanlı çalıştırma çıkış kodu 2 ile reddedilir.
17. Giriş klasöründeki tüm dosyaların SHA-256 değerleri ve dosya listesi işlem öncesi ve sonrası aynıdır.
18. Eksik metin modeli, çalıştırılabilir `ollama pull` komutuyla ve çıkış kodu 2 ile bildirilir.
19. Eksik Python bağımlılığı, PDF işleme başlamadan paket adı ve kurulum komutuyla bildirilir.

### 38.4. Doğruluk ve Güvenilirlik Kriterleri

20. `A.md` içindeki tüm sayısal değerler ya `verified` durumundadır ya da `[unverified]`/`[source_not_found]` ile işaretlidir. İşaretsiz doğrulanmamış değer bulunmaz.
21. Referans veride bulunmayan hiçbir sayısal sonuç `verified` olarak raporlanmaz.
22. Referans verideki künye alanları, tablo hücreleri, formüller ve sayısal sonuçlar için doğruluk oranları mod bazında ölçülüp README'de raporlanır. Eşik değerleri ilk ölçümden sonra bu belgeye eklenir.
23. Tüm `document.json`, çıkarım ve state dosyaları şema doğrulamasından geçer.
24. Log dosyasında FAST, BALANCED ve FULL modlarının görsel model çağrıları tetikleyicileriyle ayırt edilebilir.

### 38.5. Envanter ve Ortam Kriterleri

25. `papers_summary.csv` state dosyasındaki tüm belgeleri §22.2 sütunlarıyla içerir ve Excel'de Türkçe karakterler bozulmadan açılır.
26. Çalıştırma sonunda başarılı, uyarılı, başarısız ve atlanan sayıları konsolda ve log'da gösterilir.
27. Temiz bir makinede §34.3 komutlarıyla kurulum yapılabilir ve uygulama global site-packages olmadan çalışır.
28. `.venv` ve Python cache dosyaları çıktı klasörüne ve sürüm kontrolüne girmez.

---

## 39. Gelecek: Embedding ve RAG

`nomic-embed-text:latest` ilk sürümde kullanılmaz ve başlangıçta kontrol edilmez.

`_cache/<sha>/document.json` ve çıkarım dosyaları gelecekte şu amaçlarla kullanılabilir:

- Makale koleksiyonunda semantik arama
- Benzer çalışma bulma
- Belirli yöntemi kullanan makaleleri sorgulama
- Belirli metrik eşiğini geçen çalışmaları bulma
- Literatür sentezi

Örnek sorgu:

```text
Bi-LSTM kullanan ve F1 > 0.95 bildiren makaleleri getir.
```

Bu aşamada `qdrant-client` veya `faiss-cpu` değerlendirilecektir.

---

## 40. Nihai Hedef

```cmd
.venv\Scripts\python.exe process_papers.py --input "D:\Literature\Fatigue" --prompt "Veri setlerini, modelleri ve en iyi sonuçları karşılaştır."
```

Kullanıcı hedef klasörü ve isteğini belirtir. Sistem:

1. Başlangıç kontrollerini yapar
2. Promptu işleme planına dönüştürür
3. PDF'leri bulur ve değişenleri belirler
4. Metni çıkarır, gerekirse OCR uygular
5. Tablo, formül ve şekilleri gerektiğinde görsel model ile işler
6. Planın istediği bilgileri kanıtlarıyla çıkarır ve doğrular
7. İsteğin cevabını belge başına `A.md` veya tek bir koleksiyon Markdown'ı olarak yazar
8. Envanter tablosunu günceller
9. İşlem durumunu kaydeder

Sonuçta kullanıcı, çok sayıda bilimsel makale hakkındaki sorusuna, kaynağı izlenebilir ve yerel olarak üretilmiş bir cevap alır.

---

## 41. Basit Grafik Kullanıcı Arayüzü (GUI)

İlk sürüm, komut satırı kullanımına ek olarak yerel bilgisayarda çalışan basit ve kullanışlı bir masaüstü GUI sunmalıdır. GUI, web arayüzü veya çok kullanıcılı uzak uygulama değildir; tüm işlemler kullanıcının bilgisayarında ve yerel Ollama servisi üzerinden yürütülür.

### 41.1. Ana Ekran

Ana ekranda aşağıdaki alanlar bulunmalıdır:

- Giriş klasörü seçme alanı ve klasör seçme düğmesi
- İsteğe bağlı çıktı klasörü seçme alanı
- Tek PDF, seçili grup veya tüm koleksiyon kapsamı seçimi
- Kullanıcının doğal dilde isteğini yazacağı çok satırlı prompt alanı
- FAST, BALANCED ve FULL çalışma modu seçimi
- Alt klasörleri tara, başarısızları yeniden dene ve tamamlananları atla seçenekleri
- Başlat, duraklat ve iptal düğmeleri

### 41.2. İşlem İzleme

- Toplam PDF sayısı, tamamlanan, devam eden, uyarılı, başarısız ve atlanan dosya sayıları gösterilmelidir.
- Aktif PDF, mevcut aşama, ilerleme yüzdesi, geçen süre ve tahmini kalan süre gösterilmelidir.
- Ollama bağlantısı, gerekli modeller ve GPU durumu başlangıç kontrolünde kullanıcıya bildirilmelidir.
- Hatalar ve uyarılar, PDF adı ve işlem aşamasıyla birlikte okunabilir bir panelde gösterilmelidir.
- Kullanıcı ayrıntılı log dosyasını GUI üzerinden açabilmeli veya log klasörüne erişebilmelidir.

### 41.3. Sonuçlar ve Kullanılabilirlik

- İşlem tamamlandığında üretilen Markdown dosyasını açma ve çıktı klasörünü açma düğmeleri bulunmalıdır.
- Koleksiyon isteğinde oluşturulan tek koleksiyon Markdown dosyası ayrıca gösterilmelidir.
- GUI, uzun işlemlerde donmamalı; işlem arka planda yürütülmelidir.
- Kapatma sırasında devam eden işlem varsa kullanıcı uyarılmalı ve güvenli durdurma seçeneği sunulmalıdır.
- Prompt, klasör ve çalışma seçenekleri işlem başlamadan önce doğrulanmalı; eksik veya geçersiz alanlar açıkça belirtilmelidir.
- Arayüz klavye ile kullanılabilir, okunabilir ve Türkçe karakterleri doğru destekler olmalıdır.
- Kullanıcı ayarları güvenli bir yerel yapılandırma dosyasına kaydedilebilmeli; PDF içeriği veya hassas model çıktıları arayüz telemetrisi olarak dışarı gönderilmemelidir.

### 41.4. GUI Kabul Kriterleri

1. Kullanıcı terminal kullanmadan klasör, prompt ve çalışma modunu seçerek işlem başlatabilmelidir.
2. İşlem sırasında ilerleme ve hata durumu kullanıcı tarafından anlaşılabilmelidir.
3. İşlem tamamlandığında ilgili `A.md` veya koleksiyon Markdown dosyası GUI’den açılabilmelidir.
4. GUI kapatılsa bile güvenli durum kaydı sayesinde işlem yeniden başlatıldığında resume çalışmalıdır.
5. Ollama çalışmıyor veya gerekli model eksikse GUI çözüm önerisini ve ilgili komutu göstermelidir.
