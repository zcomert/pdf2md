"""Okuma sırası (§11.3), üst/alt bilgi (§16.3), başlık ve blok türü tespiti (§16.2), bölüm ağacı."""
import math
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .document_model import BlockType

# --- Ham yapılar ----------------------------------------------------------------------------------


@dataclass
class RawLine:
    text: str
    bbox: tuple
    font: str
    size: float
    bold: bool
    italic: bool
    chars: int
    bold_chars: int
    vertical: bool = False
    math_chars: int = 0


@dataclass
class RawBlock:
    page: int
    bbox: tuple
    lines: list = field(default_factory=list)
    is_image: bool = False
    type: BlockType = BlockType.paragraph
    column: int | None = None
    heading_level: int | None = None
    heading_number: str | None = None
    ref_id: str | None = None
    source: str = "text"  # text | ocr | vision

    @property
    def text(self):
        return "\n".join(line.text for line in self.lines)

    @property
    def chars(self):
        return sum(line.chars for line in self.lines)

    @property
    def size(self):
        return _dominant(self.lines, "size")

    @property
    def font(self):
        return _dominant(self.lines, "font")

    @property
    def bold(self):
        total = self.chars
        return total > 0 and sum(line.bold_chars for line in self.lines) / total >= 0.8

    @property
    def italic(self):
        total = self.chars
        return total > 0 and sum(line.chars for line in self.lines if line.italic) / total >= 0.8

    @property
    def width(self):
        return self.bbox[2] - self.bbox[0]


# Görsel tespitinde (Faz 05) okuma sırasından önce türü belirlenen bloklar
VISUAL_TYPES = (BlockType.table, BlockType.equation, BlockType.figure, BlockType.algorithm)


def is_flow_text(block):
    """Okuma akışındaki metin bloğu: görsel, üst/alt bilgi, tablo, formül veya şekil değil."""
    return not block.is_image and block.type not in (BlockType.header_footer, *VISUAL_TYPES)


def _dominant(lines, attribute):
    weights = Counter()
    for line in lines:
        weights[getattr(line, attribute)] += max(line.chars, 1)
    return weights.most_common(1)[0][0] if weights else None


def bbox_union(boxes):
    boxes = list(boxes)
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def split_by_style(block):
    """MuPDF bir başlığı ve ardından gelen paragrafı tek blokta birleştirebilir. Ardışık satırlar
    font boyutu (±0.5 pt), kalınlık veya italiklik (satırın en az %80'i) değiştiğinde ayrı bloklara bölünür."""
    if block.is_image or len(block.lines) < 2:
        return [block]
    groups = [[block.lines[0]]]
    for line in block.lines[1:]:
        previous = groups[-1][-1]
        if abs(line.size - previous.size) > 0.5 or line.bold != previous.bold or line.italic != previous.italic:
            groups.append([line])
        else:
            groups[-1].append(line)
    if len(groups) == 1:
        return [block]
    return [RawBlock(block.page, bbox_union(line.bbox for line in group), group, source=block.source) for group in groups]


# --- Okuma sırası ---------------------------------------------------------------------------------

GUTTER_SEARCH = (0.30, 0.70)
MIN_COLUMN_LINES = 4
COLUMN_LINE_WIDTH = (0.25, 0.48)
ALIGNED_SHARE = 0.5
FULL_WIDTH_RATIO = 0.6
EDGE_TOLERANCE = 2.0


def column_lines(blocks, page_width):
    """Sütun tespitinde kullanılan satırlar: sayfa genişliğinin %25–48'i. Daha kısa satırlar (tablo
    hücreleri, paragraf son satırları, şekil etiketleri) sütun boşluğunu yanıltıcı biçimde keser."""
    low, high = COLUMN_LINE_WIDTH[0] * page_width, COLUMN_LINE_WIDTH[1] * page_width
    return [line for block in blocks if is_flow_text(block)
            for line in block.lines
            if not line.vertical and len(line.text.strip()) >= 3 and low <= line.bbox[2] - line.bbox[0] < high]


def _split(lines, x):
    left, right, crossing = [], [], []
    for line in lines:
        if line.bbox[2] <= x + EDGE_TOLERANCE:
            left.append(line)
        elif line.bbox[0] >= x - EDGE_TOLERANCE:
            right.append(line)
        else:
            crossing.append(line)
    return left, right, crossing


def _aligned(lines):
    """Gerçek sütunda satırların çoğu aynı x noktasından başlar (4 pt tolerans)."""
    starts = Counter(round(line.bbox[0] / 4) for line in lines)
    best = max(starts, key=starts.get)
    return sum(starts[key] for key in (best - 1, best, best + 1)) >= ALIGNED_SHARE * len(lines)


def detect_gutter(blocks, page_width):
    """İki sütunlu düzende sütunlar arası boşluğun x koordinatı; bulunamazsa None.

    Aday x değerini sütun satırlarının en fazla %5'inin kesmesi, her iki tarafta satırların en az %20'sinin
    bulunması ve her iki taraftaki satırların ortak bir sol kenara hizalanması gerekir. Geçerli adayların en
    uzun kesintisiz aralığının ortası seçilir.
    """
    lines = column_lines(blocks, page_width)
    if len(lines) < 2 * MIN_COLUMN_LINES:
        return None
    allowed_crossings = max(1, int(0.05 * len(lines)))
    minimum_side = max(MIN_COLUMN_LINES, int(0.2 * len(lines)))
    first_x = int(GUTTER_SEARCH[0] * page_width)
    valid = []
    for x in range(first_x, int(GUTTER_SEARCH[1] * page_width) + 1):
        left, right, crossing = _split(lines, x)
        valid.append(len(crossing) <= allowed_crossings and len(left) >= minimum_side and len(right) >= minimum_side)
    best_start = best_length = 0
    start = None
    for i, ok in enumerate(valid + [False]):
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            if i - start > best_length:
                best_start, best_length = start, i - start
            start = None
    if best_length == 0:
        return None
    gutter = first_x + best_start + best_length / 2
    left, right, _ = _split(lines, gutter)
    return gutter if _aligned(left) and _aligned(right) else None


def gutter_fits(blocks, page_width, gutter):
    """Az metinli sayfada belge genelindeki sütun boşluğunun geçerli olup olmadığı: sütun satırlarından
    hiçbiri boşluğu kesmemeli ve her iki tarafta en az bir satır bulunmalı."""
    left, right, crossing = _split(column_lines(blocks, page_width), gutter)
    return not crossing and bool(left) and bool(right)


def document_gutter(page_gutters, page_width):
    """Sayfaların en az yarısında birbirine yakın (sayfa genişliğinin %5'i içinde) sütun boşluğu bulunduysa medyanı."""
    found = [g for g in page_gutters if g is not None]
    if len(found) < max(2, len(page_gutters) / 2):
        return None
    if max(found) - min(found) > 0.05 * page_width:
        return None
    return statistics.median(found)


def order_page(blocks, page_width, page_height, gutter=None):
    """Döner: (sıralı bloklar, sütun sayısı, gutter_x, okuma_sırası_belirsiz). `gutter` None ise tek sütun."""
    header_footer = [b for b in blocks if b.type == BlockType.header_footer]
    body = [b for b in blocks if b.type != BlockType.header_footer]
    top_margin = sorted((b for b in header_footer if b.bbox[1] < page_height / 2), key=_position_key)
    bottom_margin = sorted((b for b in header_footer if b.bbox[1] >= page_height / 2), key=_position_key)

    uncertain = False
    if gutter is None:
        for block in body:
            block.column = 0
        ordered = merge_indented_first_lines(sorted(body, key=_position_key))
        return top_margin + ordered + bottom_margin, 1, None, False

    text_blocks = [b for b in body if not b.is_image]
    content_width = (max(b.bbox[2] for b in text_blocks) - min(b.bbox[0] for b in text_blocks)) if text_blocks else page_width
    separators, left, right = [], [], []
    for block in body:
        if block.bbox[2] <= gutter + EDGE_TOLERANCE:
            block.column = 0
            left.append(block)
        elif block.bbox[0] >= gutter - EDGE_TOLERANCE:
            block.column = 1
            right.append(block)
        else:
            block.column = None
            separators.append(block)
            # Ortalanmış tek satırlık başlık/şekil başlığı sütun boşluğunu doğal olarak keser; belirsizlik
            # yalnızca dar ama çok satırlı bir metin bloğu iki sütuna taştığında vardır.
            if is_flow_text(block) and len(block.lines) >= 2 and block.width < FULL_WIDTH_RATIO * content_width:
                uncertain = True
    separators.sort(key=_position_key)
    bands = defaultdict(lambda: ([], []))
    for column_blocks, column in ((left, 0), (right, 1)):
        for block in column_blocks:
            center = (block.bbox[1] + block.bbox[3]) / 2
            band = sum(1 for sep in separators if sep.bbox[1] < center)
            bands[band][column].append(block)
    ordered = []
    for band in range(len(separators) + 1):
        if band > 0:
            ordered.append(separators[band - 1])
        left_blocks, right_blocks = bands[band]
        ordered.extend(sorted(left_blocks, key=_position_key))
        ordered.extend(sorted(right_blocks, key=_position_key))
    return top_margin + merge_indented_first_lines(ordered) + bottom_margin, 2, gutter, uncertain


def merge_indented_first_lines(ordered):
    """Bazı yayıncı PDF'lerinde (ör. Elsevier) paragrafın girintili ilk satırı ayrı blok olarak gelir.
    Tek satırlık girintili blok, hemen ardından aynı sütunda boşluksuz başlayan, sola dayalı ve aynı
    biçimdeki blokla birleştirilir."""
    result = []
    for block in ordered:
        previous = result[-1] if result else None
        if (previous is not None and _is_body_text(previous) and _is_body_text(block)
                and len(previous.lines) == 1 and previous.column == block.column and previous.page == block.page
                and previous.bbox[0] > block.bbox[0] + 3 and previous.bbox[2] >= block.bbox[2] - 6
                and block.bbox[1] - previous.bbox[3] <= 2
                and abs(previous.size - block.size) <= 0.3 and previous.bold == block.bold
                and previous.source == block.source
                and previous.lines[0].italic == block.lines[0].italic is False):
            result[-1] = RawBlock(block.page, bbox_union([previous.bbox, block.bbox]), previous.lines + block.lines,
                                  column=block.column, source=block.source)
        else:
            result.append(block)
    return result


def _is_body_text(block):
    return is_flow_text(block) and bool(block.lines)


def _position_key(block):
    # Aynı satır hizasındaki yan yana bloklar (±3 pt) soldan sağa sıralanır.
    return (round(block.bbox[1] / 3), block.bbox[0])


# --- Üst/alt bilgi ve kenar damgaları -------------------------------------------------------------

MARGIN_BAND = 0.08
SIDE_BAND = 0.06
REPEAT_RATIO = 0.4


def repeat_key(text):
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", text)).strip().casefold()


def mark_header_footer(pages):
    """`pages`: [(sayfa_no, genişlik, yükseklik, bloklar)]. Sayfa kenar şeritlerinde bulunan ve rakamlar
    normalize edildiğinde sayfaların en az %40'ında tekrarlanan metinler `header_footer` olur.
    Tek/çift sayfada dönüşümlü başlıklar (%50) ve tek sayılı sayfa sayıları için eşik %40 seçildi."""
    if len(pages) < 3:
        return
    occurrences = defaultdict(set)
    candidates = []
    for number, width, height, blocks in pages:
        for block in blocks:
            if block.is_image or not block.text.strip():
                continue
            x0, y0, x1, y1 = block.bbox
            in_band = (y1 <= MARGIN_BAND * height or y0 >= (1 - MARGIN_BAND) * height
                       or x1 <= SIDE_BAND * width or x0 >= (1 - SIDE_BAND) * width
                       or all(line.vertical for line in block.lines))
            if in_band:
                key = repeat_key(block.text)
                occurrences[key].add(number)
                candidates.append((key, block))
    threshold = max(2, math.ceil(REPEAT_RATIO * len(pages)))
    for key, block in candidates:
        if len(occurrences[key]) >= threshold:
            block.type = BlockType.header_footer


# --- Blok türleri ve başlıklar --------------------------------------------------------------------

# Etiketten sonra noktalama ("Table 1." / "TABLE I:") ya da büyük harfle başlayan başlık ("Table 1 Results")
# gelmeli; "Table 1 summarizes the results" gibi metin içi atıflar başlık değildir.
CAPTION_RE = re.compile(r"^(?:Table|TABLE|Tablo|Figure|FIGURE|Fig\.|FIG\.|Şekil|Algorithm|ALGORITHM|Algoritma)"
                        r"\s*[\dIVX]+[a-z]?(?:\s*[.:|–—-]|\s+(?=[A-ZÇĞİÖŞÜ(])|\s*$)")
LIST_RE = re.compile(r"^(?:[•\-–—▪◦·*]|\(?[a-zA-Z]\)|\((?:i|ii|iii|iv|v|vi|vii|viii|ix|x)\)|\(?\d{1,2}\)|\d{1,2}\.)\s+\S")
NUMBERING_RE = re.compile(r"^(?P<num>\d{1,2}(?:\.\d{1,2}){0,3}\.?|[IVX]{1,5}\.|[A-Z]\.)\s+(?P<title>\S.*)$", re.S)
LETTER_SPACED_RE = re.compile(r"^(?:\S ){3,}\S$")
KNOWN_SECTIONS = {
    "abstract", "introduction", "background", "related work", "related works", "literature review",
    "method", "methods", "methodology", "materials and methods", "proposed method", "experiments",
    "experimental setup", "experimental results", "results", "results and discussion", "discussion",
    "conclusion", "conclusions", "conclusion and future work", "conclusions and future work", "future work",
    "limitations", "references", "bibliography", "acknowledgment", "acknowledgments", "acknowledgement",
    "acknowledgements", "appendix", "data availability", "funding", "declarations", "author contributions",
    "özet", "öz", "giriş", "yöntem", "yöntemler", "materyal ve yöntem", "gereç ve yöntem", "bulgular",
    "sonuçlar", "tartışma", "sonuç", "sonuç ve öneriler", "kaynaklar", "kaynakça", "teşekkür", "ekler",
}
REFERENCE_SECTIONS = {"references", "bibliography", "kaynaklar", "kaynakça", "literature cited"}
HEADING_MAX_WORDS = 18
HEADING_MAX_CHARS = 160
HEADING_MIN_SCORE = 3
# Yayıncıların ilk sayfaya koyduğu makale türü etiketleri başlık değildir.
PUBLISHER_LABELS = {
    "open", "open access", "research", "research open access", "research article", "original article",
    "original manuscript", "original research", "original paper", "review", "review article", "review paper",
    "article info", "article information", "short communication", "letter", "editorial",
}


def normalize_heading_text(text):
    text = " ".join(text.split())
    if LETTER_SPACED_RE.match(text):
        text = re.sub(r"(?<=\S) (?=\S)", "", text)
    return text


def section_name(text):
    """Numarası ve sondaki iki nokta atılmış, küçük harfli bölüm adı."""
    text = normalize_heading_text(text)
    match = NUMBERING_RE.match(text)
    if match:
        text = match.group("title")
    return text.rstrip(":. ").casefold()


def comparable(text):
    """Başlık eşleştirmesi için yalnızca harf ve rakamlar (tireleme, boşluk, noktalama farkları yok sayılır)."""
    return re.sub(r"[\W_]+", "", text.casefold())


def body_font_size(blocks):
    weights = Counter()
    for block in blocks:
        if not is_flow_text(block):
            continue
        for line in block.lines:
            weights[round(line.size * 2) / 2] += line.chars
    return weights.most_common(1)[0][0] if weights else 10.0


def heading_score(block, body_size):
    text = normalize_heading_text(block.text)
    words = text.split()
    if not words or len(text) > HEADING_MAX_CHARS or len(block.lines) > 3:
        return 0, None
    if " ".join(text.casefold().split()) in PUBLISHER_LABELS:
        return 0, None
    letters = [c for c in text if c.isalpha()]
    digits = sum(c.isdigit() for c in text)
    if not letters or digits > 0.3 * len(text.replace(" ", "")):
        return 0, None
    score = 0
    delta = (block.size or body_size) - body_size
    if delta >= 1.0:
        score += 2
    elif delta >= 0.4:
        score += 1
    elif delta <= -1.0 and not NUMBERING_RE.match(text):
        # Numaralı başlıklar gövdeden küçük olabilir (IEEE alt başlıkları: 9 pt, gövde 10 pt).
        score -= 2
    if block.bold:
        score += 2
    number = None
    match = NUMBERING_RE.match(text)
    if match and match.group("title")[:1].isupper():
        number = match.group("num").rstrip(".")
        # Harf/roma rakamı numaraları yazar baş harfleriyle karışabilir; biçim desteği (kalın, italik, büyük font
        # veya IEEE'deki gibi tamamı büyük harf başlık: "A. EARLY STUDIES") olmadan sayılmaz.
        title_letters = [c for c in match.group("title") if c.isalpha()]
        all_caps_title = len(title_letters) >= 4 and all(c.isupper() for c in title_letters)
        if number[0].isdigit() or block.bold or block.italic or delta >= 0.4 or all_caps_title:
            score += 2
            # Elsevier/IEEE alt başlıkları kalın değil italiktir ("2.1. Data collection", "A. Dataset").
            if block.italic and not block.bold:
                score += 1
        else:
            number = None
    known = section_name(text) in KNOWN_SECTIONS
    if known:
        score += 3
    if len(letters) >= 4 and all(c.isupper() for c in letters):
        score += 1
    if text.endswith(".") and not (number or known):
        score -= 2
    if len(words) > HEADING_MAX_WORDS:
        score -= 3
    if len(block.lines) > 2:
        score -= 2
    return score, number


def classify_blocks(pages_blocks, first_page_height, metadata=None):
    """Blok türlerini, başlık seviyelerini ve belge başlığını belirler. Döner: belge başlığı veya None.
    `pages_blocks`: okuma sırasına dizilmiş [(sayfa_no, [RawBlock])]."""
    ordered = [block for _, blocks in pages_blocks for block in blocks]
    body_size = body_font_size(ordered)
    candidates = []
    for block in ordered:
        if block.type in VISUAL_TYPES:
            continue
        if block.is_image:
            block.type = BlockType.figure
            continue
        if block.type == BlockType.header_footer or not block.text.strip():
            continue
        if CAPTION_RE.match(block.text.strip()):
            block.type = BlockType.caption
            continue
        score, number = heading_score(block, body_size)
        if score >= HEADING_MIN_SCORE:
            block.type = BlockType.heading
            block.heading_number = number
            candidates.append(block)
        elif LIST_RE.match(block.text.strip()):
            block.type = BlockType.list

    title_blocks = _detect_title(ordered, body_size, first_page_height, metadata or {})
    title = None
    if title_blocks:
        title = " ".join(normalize_heading_text(b.text) for b in title_blocks)
        for block in title_blocks:
            block.type = BlockType.heading
            block.heading_number = None
        candidates = [b for b in candidates if b not in title_blocks]
        candidates = _drop_front_matter(candidates)
    _assign_levels(candidates, shift=1 if title_blocks else 0)
    for block in title_blocks:
        block.heading_level = 1
    _mark_footnotes(ordered, body_size, pages_blocks)
    _mark_references(ordered)
    return title


def _is_anchor(block):
    return bool(block.heading_number) or section_name(block.text) in KNOWN_SECTIONS


def _drop_front_matter(candidates):
    """İlk sayfada, numaralı veya bilinen ilk bölüm başlığından (Abstract, 1. Introduction) önce gelen
    numarasız başlık adayları yazar satırı, kurum veya yayıncı etiketidir; paragrafa döndürülür."""
    kept, anchor_seen = [], False
    for block in candidates:
        anchor_seen = anchor_seen or block.page > 1 or _is_anchor(block)
        if anchor_seen:
            kept.append(block)
        else:
            block.type = BlockType.paragraph
            block.heading_number = None
    return kept


def _detect_title(ordered, body_size, page_height, metadata):
    first_page = [b for b in ordered if b.page == 1 and not b.is_image
                  and b.type not in (BlockType.header_footer, BlockType.caption, *VISUAL_TYPES)
                  and b.text.strip() and b.bbox[1] < 0.5 * page_height]
    if not first_page:
        return []

    # 1) PDF metadata başlığıyla eşleşen ardışık bloklar
    meta_title = comparable(metadata.get("title", ""))
    if len(meta_title) >= 10:
        matched = [b for b in first_page if len(comparable(b.text)) >= 5 and comparable(b.text) in meta_title]
        if matched and sum(len(comparable(b.text)) for b in matched) >= 0.6 * len(meta_title):
            return _consecutive(first_page, matched)

    # 2) Dergi adı: sayfanın üst şeridindeki künye satırının ("Digital Engineering 1 (2024) 100004")
    #    başında veya metadata `subject` alanının başında geçen metin başlık adayı değildir.
    top_lines = [comparable(b.text) for b in ordered if b.page == 1 and b.bbox[3] <= 0.08 * page_height]
    subject = comparable(metadata.get("subject", ""))

    def journal_like(block):
        text = comparable(block.text)
        return bool(text) and (any(line != text and line.startswith(text) for line in top_lines)
                               or (len(text) >= 8 and subject.startswith(text)))

    # Bölüm başlıkları ("Introduction", "1. Methods") belge başlığı olamaz; başlıksız belgede en büyük metin bunlar olabilir.
    pool = [b for b in first_page if not journal_like(b) and len(comparable(b.text)) >= 3
            and section_name(b.text) not in KNOWN_SECTIONS and not NUMBERING_RE.match(normalize_heading_text(b.text))]
    if not pool:
        return []
    max_size = max(b.size for b in pool)
    if max_size < body_size + 1.5:
        return []
    # Sonraki sayfalarda aynı boyutta metin varsa (ör. her sayfadaki bölüm başlıkları) bu bir belge başlığı değildir.
    later = [b.size for b in ordered if b.page > 1 and is_flow_text(b)
             and b.text.strip() and len(b.lines) <= 3]
    if later and max_size < max(later) + 0.5:
        return []
    return _consecutive(first_page, [b for b in pool if abs(b.size - max_size) <= 0.3])


def _consecutive(sequence, selected):
    """`selected` içinden, `sequence` sırasındaki ilk kesintisiz grubu döndürür."""
    result = []
    for block in sequence:
        if block in selected:
            result.append(block)
        elif result:
            break
    return result


def _assign_levels(headings, shift):
    """Numaralı başlıklarda seviye numara derinliğidir. Numarasız başlıklarda seviye-1 font boyutu, bilinen
    bölüm adlarının ve tek düzeyli numaralı başlıkların en yaygın boyutudur; daha küçük boyutlar sırasıyla
    2, 3, ... seviyelerine eşlenir (numaralı alt başlıklarla aynı boyuttaysa onların seviyesini alır)."""
    def rounded(block):
        return round((block.size or 0) * 2) / 2

    def numeric_depth(block):
        number = block.heading_number
        return number.count(".") + 1 if number and number[0].isdigit() else None

    def roman(block):
        return bool(block.heading_number and re.fullmatch(r"[IVX]+", block.heading_number))

    anchors = Counter(rounded(b) for b in headings
                      if numeric_depth(b) == 1 or roman(b)
                      or (not b.heading_number and section_name(b.text) in KNOWN_SECTIONS))
    unnumbered = [b for b in headings if not b.heading_number]
    if anchors:
        level1_size = max(anchors.items(), key=lambda item: (item[1], item[0]))[0]
    elif unnumbered:
        level1_size = max(rounded(b) for b in unnumbered)
    else:
        level1_size = 0
    depth_sizes = defaultdict(list)
    for block in headings:
        depth = numeric_depth(block)
        if depth and depth > 1:
            depth_sizes[depth].append(rounded(block))
    depth_size = {depth: statistics.median(sizes) for depth, sizes in depth_sizes.items()}
    lower_sizes = sorted({rounded(b) for b in unnumbered if rounded(b) < level1_size - 0.3}, reverse=True)

    for block in headings:
        if numeric_depth(block):
            level = numeric_depth(block)
        elif roman(block):
            level = 1
        elif block.heading_number:
            level = 2
        elif section_name(block.text) in KNOWN_SECTIONS or rounded(block) >= level1_size - 0.3:
            level = 1
        else:
            same_as_numbered = [depth for depth, size in depth_size.items() if abs(size - rounded(block)) <= 0.3]
            level = min(same_as_numbered) if same_as_numbered else 2 + lower_sizes.index(rounded(block))
        block.heading_level = min(6, level + shift)


def _mark_footnotes(ordered, body_size, pages_blocks):
    heights = {}
    for number, blocks in pages_blocks:
        if blocks:
            heights[number] = max(b.bbox[3] for b in blocks)
    for block in ordered:
        if block.type != BlockType.paragraph or block.is_image:
            continue
        page_bottom = heights.get(block.page, block.bbox[3])
        if (block.size or body_size) <= body_size - 1 and block.bbox[1] >= 0.8 * page_bottom:
            block.type = BlockType.footnote


def _mark_references(ordered):
    reference_level = None
    for block in ordered:
        if block.type == BlockType.heading:
            if section_name(block.text) in REFERENCE_SECTIONS:
                reference_level = block.heading_level
            elif reference_level is not None and block.heading_level <= reference_level:
                reference_level = None
            continue
        if reference_level is not None and block.type in (BlockType.paragraph, BlockType.list):
            block.type = BlockType.reference
