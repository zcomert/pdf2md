"""Tesseract OCR (§11.4). OCR, PyMuPDF'in Tesseract entegrasyonuyla (`page.get_textpage_ocr`) yapılır; MuPDF motoru
kendi içinde barındırdığı için yalnızca `tessdata` dil dosyaları gerekir. Çalıştırılabilir dosya sürüm bilgisi ve
kurulum konumunu bulmak için kullanılır."""
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# PATH'te yoksa denenecek bilinen Windows kurulum konumları (UB Mannheim yükleyicisi, winget)
WINDOWS_LOCATIONS = [
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Tesseract-OCR",
    Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Programs" / "Tesseract-OCR",
]


@dataclass(frozen=True)
class TesseractInfo:
    tessdata: Path
    languages: tuple
    executable: Path | None = None
    version: str | None = None
    found_via: str = ""  # config | path | known_location | tessdata_prefix


@dataclass(frozen=True)
class OcrSettings:
    """Ayrıştırıcıya aktarılan, seçilmiş OCR ayarları. `parse_pdf` saf kaldığı için keşif burada yapılmaz."""
    languages: str  # "eng+tur"
    tessdata: str
    dpi: int
    version: str | None = None

    @property
    def signature(self):
        """Önbellek geçerlilik anahtarı: dil veya Tesseract sürümü değişince taranmış sayfalar yeniden OCR'lanır."""
        return f"tesseract:{self.version or '?'}:{self.languages}:{self.dpi}"


OCR_UNAVAILABLE_SIGNATURE = "unavailable"


def find_tesseract(tesseract_path=None, environ=None, known_locations=None):
    """Tesseract kurulumunu bulur; bulunamazsa None. Öncelik: config `tesseract_path` (çalıştırılabilir dosya,
    kurulum klasörü veya tessdata klasörü) > PATH > bilinen Windows konumları > `TESSDATA_PREFIX`."""
    environ = os.environ if environ is None else environ
    known_locations = WINDOWS_LOCATIONS if known_locations is None else known_locations
    candidates = []
    if tesseract_path:
        candidates.append((Path(tesseract_path), "config"))
    else:
        on_path = shutil.which("tesseract")
        if on_path:
            candidates.append((Path(on_path), "path"))
        if os.name == "nt":
            candidates.extend((location, "known_location") for location in known_locations)
        if environ.get("TESSDATA_PREFIX"):
            candidates.append((Path(environ["TESSDATA_PREFIX"]), "tessdata_prefix"))
    for candidate, via in candidates:
        info = _inspect(candidate, via)
        if info is not None:
            return info
    return None


def _inspect(candidate, via):
    executable, tessdata = None, None
    if candidate.is_file():
        executable = candidate
        tessdata = candidate.parent / "tessdata"
    elif candidate.is_dir():
        if list(candidate.glob("*.traineddata")):
            tessdata = candidate
            executable = _executable_in(candidate.parent)
        else:
            tessdata = candidate / "tessdata"
            executable = _executable_in(candidate)
    if tessdata is None or not tessdata.is_dir():
        return None
    languages = tuple(sorted(p.stem for p in tessdata.glob("*.traineddata") if p.stem != "osd"))
    if not languages:
        return None
    return TesseractInfo(tessdata=tessdata, languages=languages, executable=executable,
                         version=_version(executable), found_via=via)


def _executable_in(folder):
    for name in ("tesseract.exe", "tesseract"):
        if (folder / name).is_file():
            return folder / name
    return None


def _version(executable):
    if executable is None:
        return None
    try:
        completed = subprocess.run([str(executable), "--version"], capture_output=True, text=True, timeout=15,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    first = (completed.stdout or completed.stderr).strip().splitlines()
    return first[0].replace("tesseract", "").strip() if first else None


def select_languages(requested, available):
    """Döner: (kullanılacak diller, eksik diller). İstenenlerden kurulu olanlar sırasıyla kullanılır."""
    usable = [language for language in requested if language in available]
    missing = [language for language in requested if language not in available]
    return usable, missing


def resolve_ocr_settings(ocr_config, dpi, info=None):
    """Döner: (OcrSettings veya None, bilgi/uyarı mesajları). OCR kapalıysa veya kullanılabilir dil yoksa None."""
    if not ocr_config.enabled:
        return None, ["OCR yapılandırmada kapalı (ocr.enabled: false)"]
    info = info if info is not None else find_tesseract(ocr_config.tesseract_path)
    if info is None:
        return None, ["Tesseract bulunamadı"]
    usable, missing = select_languages(ocr_config.languages, info.languages)
    messages = [f"Kurulu olmayan OCR dilleri: {', '.join(missing)}"] if missing else []
    if not usable:
        return None, messages + ["Kullanılabilir OCR dili yok"]
    return OcrSettings(languages="+".join(usable), tessdata=str(info.tessdata), dpi=dpi, version=info.version), messages


def ocr_page(page, settings, flags):
    """Sayfanın tamamını OCR'lar. Döner: (kelimeler, satır boyutları) — kelimeler PyMuPDF `words` biçiminde
    (x0, y0, x1, y1, metin, ...), satır boyutları [(bbox, font_boyutu)]."""
    textpage = page.get_textpage_ocr(flags=flags, language=settings.languages, dpi=settings.dpi, full=True,
                                     tessdata=settings.tessdata)
    words = page.get_text("words", flags=flags, textpage=textpage)
    data = page.get_text("dict", flags=flags, textpage=textpage)
    sizes = [(tuple(line["bbox"]), max((span["size"] for span in line["spans"]), default=0.0))
             for block in data["blocks"] if block.get("type") == 0 for line in block["lines"]]
    return words, sizes


# --- OCR düzeni ------------------------------------------------------------------------------------
#
# MuPDF, OCR kelimelerini aynı taban çizgisindeyse sütun boşluğunu gözetmeden aynı bloğa, iki yana yaslı metindeki
# kelimeleri ise ayrı bloklara koyabilir (Shilaskar: sütun boşluğu ~5 pt, kelime aralıkları 3–6 pt). Bu yüzden OCR
# sayfalarında satır ve bloklar kelime kutularından yeniden kurulur.

GUTTER_SEARCH = (0.30, 0.70)
ROW_TOLERANCE = 3.0


def whitespace_gutter(words, page_width, min_side_share=0.25, max_cover_rows=0.20):
    """Kelimelerin dikey boşluk profilinden sütun boşluğu. İki yana yaslı metnin kelime aralıkları her satırda
    farklı x'e düşerken gerçek sütun boşluğu sütun satırlarında boştur. Aday x'i satırların en fazla %20'sinde bir
    kelime kesebilir (sütunları kesen başlık, yazar ve özet satırları; Shilaskar s.1) ve her iki tarafta kelimelerin
    en az %25'i bulunmalıdır; en uzun geçerli aralığın ortası seçilir. Tek sütunlu metinde satırların çoğu her x'te
    bir kelimeyle kesilir. Eşik satır sayısına göredir: kelime sayısına göre olsaydı birkaç satırın aralığının
    tesadüfen aynı x'e denk gelmesi sütun sanılabilirdi."""
    boxes = [w for w in words if any(ch.isalnum() for ch in w[4])]
    if len(boxes) < 40:
        return None
    rows = _row_index(boxes)
    row_count = max(rows.values()) + 1
    valid = []
    start_x = int(GUTTER_SEARCH[0] * page_width)
    for x in range(start_x, int(GUTTER_SEARCH[1] * page_width) + 1):
        covered_rows = {rows[id(w)] for w in boxes if w[0] < x < w[2]}
        left = sum(1 for w in boxes if w[2] <= x)
        right = sum(1 for w in boxes if w[0] >= x)
        valid.append(len(covered_rows) <= max(1, max_cover_rows * row_count)
                     and left >= min_side_share * len(boxes) and right >= min_side_share * len(boxes))
    best_start = best_length = 0
    run = None
    for i, ok in enumerate(valid + [False]):
        if ok and run is None:
            run = i
        elif not ok and run is not None:
            if i - run > best_length:
                best_start, best_length = run, i - run
            run = None
    return start_x + best_start + best_length / 2 if best_length else None


def _row_index(words):
    """Kelime nesnesi kimliği → satır sırası (dikey merkezleri `ROW_TOLERANCE` içinde olanlar aynı satır)."""
    index, current, last_center = {}, -1, None
    for word in sorted(words, key=lambda w: (w[1] + w[3]) / 2):
        center = (word[1] + word[3]) / 2
        if last_center is None or center - last_center > ROW_TOLERANCE:
            current += 1
            last_center = center
        index[id(word)] = current
    return index


def build_ocr_blocks(page_number, words, line_sizes, page_width, text_line_boxes=(), min_overlap=0.5):
    """OCR kelimelerinden `RawBlock`'lar. Adımlar: metin katmanında zaten bulunan kelimelerin atılması (§11.4:
    örtüşen bölgede metin katmanı tercih edilir) → sütun boşluğu → kelimeleri sütun ve taban çizgisine göre satırlara
    toplama → satırları dikey yakınlık, girinti ve font boyutuna göre bloklara ayırma. Harf/rakam içermeyen
    satırlar (vektör çizim gürültüsü) atılır.

    Eleme kelime düzeyinde yapılır: kenardaki dikey damga (metin katmanında mevcut) OCR'da tek tek karakterler
    olarak sütun satırlarıyla aynı taban çizgisine düşer ve satır düzeyinde elenemez."""
    from .layout_analyzer import RawBlock, RawLine

    words = [w for w in words if not any(_covered(tuple(w[:4]), box, min_overlap) for box in text_line_boxes)]
    gutter = whitespace_gutter(words, page_width)
    rows = []
    for word in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        center = (word[1] + word[3]) / 2
        if rows and abs(rows[-1]["center"] - center) <= ROW_TOLERANCE:
            rows[-1]["words"].append(word)
        else:
            rows.append({"center": center, "words": [word]})

    lines = []
    for row in rows:
        crosses = gutter is not None and any(w[0] < gutter - 1 and w[2] > gutter + 1 for w in row["words"])
        sides = {}
        for word in sorted(row["words"], key=lambda w: w[0]):
            side = -1 if gutter is None or crosses else (0 if word[2] <= gutter + 1 else 1)
            sides.setdefault(side, []).append(word)
        for side, side_words in sides.items():
            text = " ".join(w[4] for w in side_words)
            if not any(ch.isalnum() for ch in text):
                continue
            bbox = (min(w[0] for w in side_words), min(w[1] for w in side_words),
                    max(w[2] for w in side_words), max(w[3] for w in side_words))
            size = _line_size(bbox, line_sizes)
            chars = len(text.replace(" ", ""))
            lines.append((side, RawLine(text=text, bbox=bbox, font="ocr", size=size, bold=False, italic=False,
                                        chars=chars, bold_chars=0)))

    blocks = []
    for side in sorted({side for side, _ in lines}):
        current = []
        for _, line in sorted(((s, l) for s, l in lines if s == side), key=lambda item: item[1].bbox[1]):
            if current:
                previous = current[-1]
                height = previous.bbox[3] - previous.bbox[1]
                new_block = (line.bbox[1] - previous.bbox[3] > 0.7 * height
                             or line.bbox[0] - current[0].bbox[0] > 6          # girintili satır yeni paragraf başlatır
                             or abs(line.size - previous.size) > 1.0)
                if new_block:
                    blocks.append(_block(RawBlock, page_number, current))
                    current = []
            current.append(line)
        if current:
            blocks.append(_block(RawBlock, page_number, current))
    return blocks


def _block(raw_block_class, page_number, lines):
    bbox = (min(l.bbox[0] for l in lines), min(l.bbox[1] for l in lines),
            max(l.bbox[2] for l in lines), max(l.bbox[3] for l in lines))
    return raw_block_class(page_number, bbox, list(lines), source="ocr")


def _line_size(bbox, line_sizes):
    """Kelime satırının font boyutu: merkezini içeren MuPDF OCR satırının boyutu; yoksa yükseklikten tahmin."""
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    for box, size in line_sizes:
        if box[0] - 1 <= cx <= box[2] + 1 and box[1] - 1 <= cy <= box[3] + 1 and size > 0:
            return round(size, 1)
    return round((bbox[3] - bbox[1]) * 0.8, 1)


def text_line_boxes(blocks):
    return [line.bbox for block in blocks if not block.is_image for line in block.lines]


def merge_ocr_blocks(text_blocks, ocr_blocks, min_overlap=0.5):
    """§11.4: OCR metni mevcut metin katmanıyla birleştirilir. OCR satırının alanının en az `min_overlap` kadarı bir
    metin katmanı satırıyla örtüşüyorsa metin katmanı tercih edilir ve OCR satırı atılır (kelime düzeyi eleme
    `build_ocr_blocks` içinde yapılır; bu ikinci kontrol dışarıdan verilen bloklar içindir). Kalan OCR satırları
    `source="ocr"` bloklar olarak eklenir. Döner: (bloklar, eklenen OCR satırı sayısı)."""
    text_lines = text_line_boxes(text_blocks)
    merged = list(text_blocks)
    added = 0
    for block in ocr_blocks:
        kept = [line for line in block.lines if not any(_covered(line.bbox, other, min_overlap) for other in text_lines)]
        if not kept:
            continue
        added += len(kept)
        block.lines = kept
        block.bbox = (min(l.bbox[0] for l in kept), min(l.bbox[1] for l in kept),
                      max(l.bbox[2] for l in kept), max(l.bbox[3] for l in kept))
        block.source = "ocr"
        merged.append(block)
    return merged, added


def _covered(bbox, other, ratio):
    width = min(bbox[2], other[2]) - max(bbox[0], other[0])
    height = min(bbox[3], other[3]) - max(bbox[1], other[1])
    area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    return width > 0 and height > 0 and area > 0 and width * height / area >= ratio
