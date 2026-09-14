# Performans Raporu — 2026-09-14

Girdi: `D:\programs\pdf2md\tests\fixtures\real`. Donanım: GPU: NVIDIA RTX 4500 Ada Generation, VRAM 24570 MiB (8108 MiB boş). OCR: Tesseract v5.4.0.20240606 (C:\Program Files\Tesseract-OCR\tessdata), diller: eng.
Modeller: {'gemma4:latest': 'gemma4:latest@sha256:c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb', 'minicpm-v4.5:8b': 'minicpm-v4.5:8b@sha256:0c40168f46d1cbf5cec399d8ced34b6d3347a79f69306866efa44203c08eeda3'}.

Soğuk: önbelleksiz, varsayılan prompt (tam dönüşüm). Sıcak: aynı klasörde prompt değişikliği ("Başlık, veri seti ve en iyi sonuçları çıkar."); ayrıştırma ve görsel sonuçlar önbellekten.

| Ölçüt | fast soğuk | fast sıcak | balanced soğuk | balanced sıcak | full soğuk | full sıcak |
|---|---:|---:|---:|---:|---:|---:|
| Toplam süre (sn) | 110.5 | 513.6 | 625.6 | 574.4 | 890.2 | 567.8 |
| İşlenen sayfa | 132 | 132 | 132 | 132 | 132 | 132 |
| Sayfa başına süre (sn) | 0.83 | 3.82 | 4.73 | 4.29 | 6.74 | 4.24 |
| Tamamlanan belge | 9 | 9 | 9 | 9 | 9 | 9 |
| Başarısız belge | 0 | 0 | 0 | 0 | 0 | 0 |
| Görsel çağrı | 0 | 0 | 64 | 10 | 129 | 14 |
| Belge başına görsel çağrı | 0.0 | 0.0 | 7.1 | 1.1 | 14.3 | 1.6 |
| Metin çağrısı | 9 | 19 | 9 | 19 | 9 | 19 |
| Belge başına metin çağrısı | 1.0 | 2.1 | 1.0 | 2.1 | 1.0 | 2.1 |
| OCR sayfası | 6 | 6 | 6 | 6 | 6 | 6 |
| Ayrıştırılan | 9 | 0 | 9 | 0 | 9 | 0 |
| Önbellekten ayrıştırma | 0 | 9 | 0 | 9 | 0 | 9 |
