# Aşama 6'ya Giriş: Embedding ve RAG (§39)

Bu belge kod içermez. İlk sürümün ürettiği ara dosyaların, makale koleksiyonu üzerinde anlamsal arama ve soru-cevap (RAG) için nasıl kullanılabileceğini ve teknoloji seçimi için değerlendirme ölçütlerini tanımlar.

## Hazır Girdiler

| Kaynak | İçerik | RAG için kullanımı |
|---|---|---|
| `_cache/<sha>/document.json` | Blok kimlikli (`p5-b12`), sayfa, bbox, bölüm ağacı, tablolar (hücreler/Markdown), formüller (LaTeX), şekil başlıkları, `source_method` | Parça (chunk) üretiminin ana kaynağı; her parça kanıt konumunu taşır |
| `_cache/<sha>/vision/<digest>.json` | Görsel modelle yapılandırılan tablolar, formüller, taranmış sayfa metni | `document.json`'a uygulanmış hali parçalanmalı (çıkarım hattıyla aynı) |
| `_cache/<sha>/extractions/*.json` | Doğrulanmış alanlar ve sonuçlar (`verification`, `confidence`, kanıt) | Yapılandırılmış filtreler ve kısa "gerçek" kayıtları; yalnızca `verified` değerler |
| `processing_state.json` → `bibliographic` | Başlık, yazarlar, yıl, dergi, DOI | Meta veri filtreleri (yıl, dergi), kaynak gösterimi |

## Parça Stratejisi (öneri)

- **Birim: blok.** Paragraflar, liste blokları, tablo (başlık + Markdown) ve formül (numara + LaTeX + çevresindeki açıklama cümlesi) ayrı parçalar.
- Kısa ardışık bloklar aynı bölüm içinde ~300–500 token'a kadar birleştirilir. Bölüm sınırı aşılmaz; başlık yolu (`2. Method > 2.1 Dataset`) parçanın başına eklenir.
- Her parçanın meta verisi: `sha256`, göreli yol, `block_ids`, sayfa aralığı, bölüm, `source_method`, künye (yıl, dergi), belge dili.
- Üst/alt bilgi ve kaynakça blokları varsayılan olarak dışarıda; kaynakça ayrı bir koleksiyonda tutulabilir.
- Tablolar hem Markdown hem "satır cümlesi" (`Model=Bi-LSTM, Accuracy=0.99`) olarak iki temsil ile denenmeli; sayısal sorgularda ikincisi daha iyi eşleşebilir.

## Embedding Modeli

- Yerel `nomic-embed-text` (Ollama'da kurulu, 768 boyut, 8K bağlam). Arama sorgusu ve belge parçası için model belgelerindeki görev önekleri (`search_query:` / `search_document:`) kullanılmalı.
- Embedding'ler `_cache/<sha>/embeddings/<model_digest12>.npy` + parça kimliği listesi olarak önbelleğe alınabilir; `document.json` değişmedikçe yeniden hesaplanmaz (mevcut önbellek anahtarlarıyla uyumlu).
- Model digest'i, §17.1'deki gibi yeniden üretilebilirlik için kayda girmeli.

## Vektör Deposu Seçimi

| Ölçüt | `faiss-cpu` | `qdrant-client` (yerel mod) |
|---|---|---|
| Kurulum | Tek pip paketi, sunucu yok | Yerel/gömülü mod pip paketi; ayrı sunucu isteğe bağlı |
| Meta veri filtresi (yıl, dergi, sha) | Yok; filtre uygulama katmanında | Yerleşik yük (payload) filtreleri |
| Artımlı güncelleme / silme | Sınırlı (yeniden kurulum veya ID eşlemesi) | Doğal |
| Ölçek (binlerce makale, yüz binlerce parça) | Çok hızlı | Yeterli |
| Kalıcılık | Dosyaya yazma elle | Yerleşik |
| Windows uyumluluğu | İyi (cpu tekerleği) | İyi |

Değerlendirme için önerilen ölçütler: 100 ve 1.000 makalelik koleksiyonda indeksleme süresi, sorgu gecikmesi (p50/p95), meta veri filtreli sorgu desteği, belge değiştiğinde güncelleme maliyeti, disk kullanımı. Artımlı güncelleme (SHA değişince yalnızca o belgenin parçaları) ve filtre ihtiyacı nedeniyle başlangıç önerisi **qdrant yerel mod**; filtre gerekmezse ve koleksiyon statikse `faiss-cpu`.

## Güvenilirlik Kuralları (RAG'e taşınmalı)

- Cevap üretiminde §10.4 ve §31 aynen geçerli: getirilen parçalar veri sınırı içinde verilir, parçada olmayan bilgi üretilmez.
- Her iddia parça kimliği ve sayfayla kaynak göstermeli; sayısal değerler Faz 09 doğrulayıcısıyla (`numbers_in_source`) getirilen blok metnine karşı denetlenmeli.
- Koleksiyon sentezindeki (Faz 12) makale kimliği zorunluluğu RAG cevaplarında da uygulanmalı.

## Açık Sorular

- Türkçe ve İngilizce karışık koleksiyonlarda tek çok dilli embedding modeli mi, dil başına model mi?
- Formül araması için LaTeX metni mi, formülün çevresindeki açıklama mı gömülmeli?
- GUI'de arama ekranı mı, yoksa mevcut prompt akışına "koleksiyonda ara" kapsamı mı?
