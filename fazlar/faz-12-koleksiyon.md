# Faz 12 — Koleksiyon Kapsamı ve Makaleler Arası Sentez

**İlgili bölümler:** §21, §32.3 (`--collection-output`), §38.2 (kriter 8, 9)
**Önkoşul:** Faz 11
**Tahmini büyüklük:** Orta–Büyük

## Amaç

Birden fazla makaleyi birlikte analiz eden koleksiyon çıktısını üretmek: belge bazlı doğrulanmış çıkarımları birleştirip karşılaştırmalı bir sentez Markdown'ı yazmak. Bu faz §37 **Aşama 5**'i tamamlar.

## Modüller

`src/collection_analyzer.py`, `src/markdown_builder.py` (koleksiyon yolu), `src/schemas.py` (`CollectionState`)

## Görevler

### 1. Kapsam akışı (§21.2, §21.4)

- [ ] Plan `scope == collection` ise batch işlemcisi koleksiyon moduna geçer
- [ ] Hedef PDF'ler: keşif + `targets.include` (CLI `--include` önceliği Faz 08'de)
- [ ] Her PDF için: `document.json` (önbellek/üret) → görsel zenginleştirme → `extractions/<plan_hash>.json`
- [ ] **Belge başına `A.md` üretilmez** (§21.4.3, §38 kriter 8)
- [ ] Belge state kayıtları: çıkarım aşaması durumu tutulur; `output_path` boş kalır (belge çıktısı yok). Atlama kuralındaki "çıktı dosyası mevcut" koşulu koleksiyon kapsamında **çıkarım dosyası mevcut** olarak uygulanır (kararı kodda belgele)
- [ ] Başarısız belgeler sentezden çıkarılır, listelenir (§21.6)

### 2. Sentez girdisi

§21.4.4 — girdi **yalnızca doğrulanmış çıkarımlar**, ham PDF metni değil:

- [ ] Her makale için kompakt kayıt: `paper_id` (kısa etiket, ör. künye başlığı veya dosya adı), göreli yol, künye, `status: found` alanlar, `verification: verified` sonuçlar (sayfa/tablo kanıtıyla)
- [ ] `unverified`/`source_not_found` sayısal değerler sentez girdisine **alınmaz** (§19.1)
- [ ] `not_found` alanlar açıkça `not_found` olarak iletilir (modelin tamamlamaması için)
- [ ] Bağlam taşarsa: `comparison_dimensions` başına ayrı sentez çağrıları (map), sonra kısa birleştirme çağrısı (reduce)

### 3. Sentez — `src/collection_analyzer.py`

- [ ] **Deterministik kısım (LLM'siz):**
  - Makale bazlı bulgular tablosu: satır = makale, sütun = `requested_fields` / `comparison_dimensions`; hücre değeri + kaynak etiketi `(s. n)`; eksik → `not_found`, okunamayan → `[unclear]`
  - Sayısal karşılaştırma tabloları (model × metrik × makale) yalnızca `verified` değerlerle
- [ ] **LLM kısmı:** ortaklıklar, farklılıklar, özgün katkılar, sentez paragrafları — şemalı yanıt: her iddia `{text, paper_ids: [...], evidence_refs: [...]}`
- [ ] Doğrulama:
  - Her iddia en az bir geçerli `paper_id` içermeli; içermeyen iddia atılır + uyarı (§38 kriter 9)
  - İddia metnindeki sayılar ilgili makalelerin `verified` değerleri arasında olmalı; değilse iddia `[unverified]` işaretlenir veya atılır (Faz 09 son kontrol mantığı yeniden kullanılır)
  - Makaleler arası eksik değer tamamlanmamalı (§21.5)
- [ ] Sistem promptunda Faz 09'daki güvenilirlik kuralları + "yalnızca verilen kayıtlara dayan"

### 4. Çıktı yolu (§21.5)

- [ ] Varsayılan: `<output>/collections/<güvenli_ad>_<YYYYMMDD-HHMMSS>.md`
- [ ] `<güvenli_ad>`: `--collection-name` > `plan.collection_name_suggestion` > `collection`; en fazla 50 karakter, `safe_filename` ile normalize
- [ ] `--collection-output <yol>`:
  - Dosya varsa **hata** (üzerine yazılmaz)
  - Giriş klasörü içinde olamaz (§32.3); çıktı klasörü dışında olabilir
  - Bu kontroller preflight'ta yapılır (işlem başlamadan)
- [ ] Atomik yazım
- [ ] Şekil referansı varsa `collections/assets/<güvenli_ad>_<ts>/` altına kopyalama (belge kurallarıyla tutarlı; yalnızca referans verilenler)

### 5. İçerik düzeni

- [ ] Front matter: §20.2 alanları + `documents: [{path, sha256}]`
- [ ] `## Prompt` — kullanılan prompt metni (kod bloğu veya alıntı)
- [ ] `## Yöntem Notu` — mod, modeller (digest'leriyle), işlenen/başarısız belge sayısı
- [ ] `plan.output_outline` başlıkları; içinde:
  - Makale bazlı bulgular
  - Karşılaştırmalı sentez
- [ ] `## İşlenemeyen Belgeler` — varsa, dosya ve hata aşamasıyla
- [ ] Başlık dilleri `plan.output_language`'e göre (yöntem notu ve işlenemeyen belgeler başlıkları için TR/EN sabit etiket tablosu)

### 6. Koleksiyon state'i (§21.6)

- [ ] `collections[<koleksiyon_anahtarı>]`: `document_hashes` (sıralı), `prompt_sha256`, `plan_hash`, `models`, `output_path`, `created_at`, `status`
- [ ] Anahtar: `sha256(plan_hash + sıralı belge hash'leri)` 
- [ ] Aynı anahtar ve çıktı dosyası mevcut → sentez atlanır, mevcut yol konsola yazılır
- [ ] Bir belge değişirse: yalnızca o belgenin çıkarımı yenilenir (diğerleri önbellekten), sentez yeniden yapılır, **yeni zaman damgalı** dosya
- [ ] Önceki koleksiyon çıktıları silinmez

### 7. CSV etkisi

- [ ] Koleksiyon çalıştırmasında belge satırları güncellenir (status, çağrı sayıları); `output_path` boş veya önceki belge çıktısı korunur — önerilen: önceki `A.md` yolu korunur, çünkü koleksiyon çalıştırması onu silmez

## Testler

- Klasör + "veri setlerini karşılaştır" (`FakeTextClient` planı `collection`) → `collections/` altında tek dosya, hiçbir belge klasöründe yeni `.md` yok (§38 kriter 8)
- `unverified` değer sentez girdisinde yok
- `paper_ids`'siz iddia atılıyor (§38 kriter 9)
- Aynı plan + aynı PDF'ler ile ikinci çalıştırma → sentez çağrısı 0, mevcut yol bildirimi
- Bir PDF değiştirilince yalnızca onun çıkarımı yeniden yapılır (çağrı sayacı), yeni zaman damgalı dosya oluşur, eski dosya durur
- `--collection-output` var olan dosya → hata, çıkış 2; giriş klasörü içi → hata
- Başarısız belge "İşlenemeyen Belgeler" bölümünde
- `@requires_ollama` gerçek makalelerle §21.3'teki 5 istek türü elle değerlendirilir

## Tamamlanma Kriterleri

- [ ] §38 kriterleri 8 ve 9 karşılanıyor
- [ ] §40'taki nihai hedef komutu gerçek makale klasöründe uçtan uca çalışıyor
- [ ] `pytest` yeşil

> **Kilometre taşı:** Aşama 5 tamamlandı, CLI tarafı işlevsel olarak eksiksiz. Etiket: `v0.5-asama5`.
