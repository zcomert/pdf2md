"""Tablo, formül ve şekil adaylarının tespiti (§12.2) ve ilgili blokların tek bloğa dönüştürülmesi.

Okuma sırasından önce, tek bir sayfanın ham blokları üzerinde çalışır. Bölgeye düşen metin blokları tek bir
`table`/`equation`/`figure` bloğunda toplanır; böylece Markdown'da aynı metin iki kez yazılmaz ve bu bölgeler
okuma sırasında bütün olarak yer alır. Metin göstergeleri (başlık, numara) tek başına aday oluşturmaz; her
adayın geometrik bir karşılığı (çizgili tablo, yatay çizgiler, görsel, çizim kümesi, numara satırı) vardır.
"""
import re
from dataclasses import dataclass, field

from .document_model import BlockType
from .equation_latex import (equation_glyphs, fraction_rules, glyph_region, page_lines, strip_number,
                             text_layer_latex)
from .layout_analyzer import CAPTION_RE, RawBlock, bbox_union, heading_score
from .table_extractor import assess_cells, clean_cell, merged_cells_from_bboxes, rows_from_words, to_html, to_markdown

TABLE_CAPTION_RE = re.compile(r"^(?:Table|TABLE|Tablo)\s*([\dIVX]+[a-z]?)")
FIGURE_CAPTION_RE = re.compile(r"^(?:Figure|FIGURE|Fig\.|FIG\.|Şekil|ŞEKİL)\s*(\d+[a-z]?)")
EQUATION_NUMBER_RE = re.compile(r"\((\d{1,3}(?:\.\d{1,2})?[a-z]?)\)")
MATH_SYMBOLS = set("=∑∫∂√≤≥±×÷∞≈≠∈∉∀∃∇∏λμσαβγδθπωεφψΣΠΔΩ→←⇒⇔∧∨⊂⊆∪∩")
# Numara satırının önündeki kontrol/özel kullanım glifleri (LaTeX'in görünmez kutuları, ör. "\x08 (1)")
NUMBER_NOISE_RE = re.compile("[\x00-\x1f\x7f\ue000-\uf8ff]")
# Formül gövdesinde geçen ve düzyazı sayılmayan kelimeler (cases, operatör adları)
MATH_WORDS = {"if", "otherwise", "else", "and", "with", "log", "exp", "max", "min", "arg", "argmax",
              "argmin", "sin", "cos", "tan", "lim", "sup", "inf", "det", "mod", "subject", "all", "then"}
# Formülün hemen altındaki açıklama cümlesinin ilk sözcükleri ("where S is ...")
PROSE_LEADS = {"where", "here", "which", "whereas"}
# Gövde satırının numara satırıyla dikeyde örtüşmesi gereken en küçük oran (komşu düzyazı satırları alınmasın)
EQUATION_BODY_MIN_OVERLAP = 0.3

TABLE_REGION_MAX_GAP = 30.0
FIGURE_CAPTION_MAX_GAP = 60.0
CAPTION_LABEL_MAX_CHARS = 14
MIN_IMAGE_AREA_RATIO = 0.002
MIN_DRAWING_CLUSTER_AREA_RATIO = 0.01
UNCAPTIONED_FIGURE_AREA_RATIO = 0.05
EQUATION_NUMBER_MAX_WIDTH = 45.0
EQUATION_MAX_BODY_DISTANCE = 300.0
# Paneli ızgara şeklinde dizilmiş şekiller (2×2) arasındaki boşluk (Vekkot: 23 pt)
FIGURE_GROUP_GAP = 30.0


@dataclass
class TableElement:
    page: int
    bbox: tuple
    number: str | None
    caption: RawBlock | None
    reasons: list
    rows: list = field(default_factory=list)
    merged: list = field(default_factory=list)
    consistent: bool = False
    raw_text: str | None = None
    block: RawBlock | None = None


@dataclass
class EquationElement:
    page: int
    bbox: tuple
    number: str | None
    raw_text: str
    reasons: list
    block: RawBlock | None = None
    line_bboxes: list = field(default_factory=list)
    latex: str | None = None


@dataclass
class FigureElement:
    page: int
    bbox: tuple
    number: str | None
    caption: RawBlock | None
    reasons: list
    xref: int | None = None
    block: RawBlock | None = None


@dataclass
class PageVisuals:
    tables: list = field(default_factory=list)
    equations: list = field(default_factory=list)
    figures: list = field(default_factory=list)


# --- geometri ---------------------------------------------------------------------------------------

def area(bbox):
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def intersection(a, b):
    return (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))


def overlap_ratio(inner, outer):
    """`inner` alanının `outer` içinde kalan oranı."""
    return area(intersection(inner, outer)) / area(inner) if area(inner) > 0 else 0.0


def center_inside(bbox, region, tolerance=2.0):
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return region[0] - tolerance <= cx <= region[2] + tolerance and region[1] - tolerance <= cy <= region[3] + tolerance


def horizontal_overlap(bbox, span):
    width = bbox[2] - bbox[0]
    return max(0.0, min(bbox[2], span[1]) - max(bbox[0], span[0])) / width if width > 0 else 0.0


def column_span(bbox, page_width, gutter):
    """Başlığın ait olduğu sütunun yatay aralığı; sütun yoksa veya başlık boşluğu kesiyorsa tam sayfa."""
    if gutter is None:
        return (0.0, page_width)
    if bbox[2] <= gutter + 2:
        return (0.0, gutter)
    if bbox[0] >= gutter - 2:
        return (gutter, page_width)
    return (0.0, page_width)


# --- yardımcılar ------------------------------------------------------------------------------------

def merge_caption_labels(blocks):
    """Kalın "Table 1" etiketi ile başlık metni stil farkı yüzünden ayrı bloklara bölünebilir (Elsevier).
    Yalnızca etiketten oluşan bloğu hemen altındaki blokla birleştirir."""
    result = []
    for block in sorted(blocks, key=lambda b: (b.bbox[1], b.bbox[0])):
        previous = result[-1] if result else None
        if (previous is not None and not previous.is_image and not block.is_image and block.lines
                and previous.type == BlockType.paragraph and block.type == BlockType.paragraph
                and CAPTION_RE.match(previous.text.strip() + " X")
                and len(previous.text.strip()) <= CAPTION_LABEL_MAX_CHARS
                and -4 <= block.bbox[1] - previous.bbox[3] <= 6 and abs(block.bbox[0] - previous.bbox[0]) <= 6):
            result[-1] = RawBlock(block.page, bbox_union([previous.bbox, block.bbox]), previous.lines + block.lines)
        else:
            result.append(block)
    return result


def is_prose(block, span_width):
    """Tablo bölgesini sonlandıran düzyazı: en az iki geniş satır, yeterli kelime, düşük rakam oranı."""
    if block.is_image or len(block.lines) < 2:
        return False
    wide = sum(1 for line in block.lines if line.bbox[2] - line.bbox[0] >= 0.75 * span_width)
    text = block.text
    words = re.findall(r"[^\W\d_]{2,}", text)
    digits = sum(c.isdigit() for c in text)
    return wide >= 2 and len(words) >= 20 and digits < 0.15 * max(1, len(text.replace(" ", "")))


def line_has_math(line):
    text = line.text
    return (line.math_chars >= max(1, 0.2 * line.chars)) or any(symbol in MATH_SYMBOLS for symbol in text)


def line_is_prose(line):
    """Formüle ait olmayan düzyazı satırı: eşittir yok, matematik fontu az ve en az üç sözcük (cases içindeki "if",
    "otherwise" ve operatör adları sayılmaz), "where ..." ile başlayan açıklama ya da iki noktayla biten giriş cümlesi
    ("we predict:")."""
    text = line.text.strip()
    if text.split(" ", 1)[0].casefold() in PROSE_LEADS:
        return True
    if "=" in text or line.math_chars >= 0.2 * max(1, line.chars):
        return False
    words = [w for w in re.findall(r"[^\W\d_]{3,}", text) if w.casefold() not in MATH_WORDS]
    return len(words) >= 3 or (text.endswith(":") and bool(words))


def horizontal_rules(drawings, span, min_width_ratio=0.4):
    """Tablo bölgesini sınırlandıran yatay çizgilerin y değerleri (booktabs tabloları)."""
    width = span[1] - span[0]
    ys = []
    for drawing in drawings:
        rect = drawing["rect"]
        if rect.height <= 1.5 and rect.width >= min_width_ratio * width and horizontal_overlap(tuple(rect), span) > 0.5:
            ys.append(round((rect.y0 + rect.y1) / 2, 1))
            continue
        for item in drawing.get("items", []):
            if item[0] == "l" and abs(item[1].y - item[2].y) < 1 and abs(item[2].x - item[1].x) >= min_width_ratio * width:
                ys.append(round(item[1].y, 1))
    return sorted(set(ys))


def ruled_table_clip(drawings):
    """Çizgili tablo ızgarası varsa `find_tables()` için kırpma bölgesi, yoksa None.

    `find_tables()` ayrıştırma süresinin çoğunu alır (sayfanın tüm metnini analiz eder; gerçek sette 9 makalede
    13 sn). Izgara şartı: bir yatay çizgiyi kesen en az 3 ayrı dikey çizgi (en az iki sütun). Özet kutusu gibi
    çerçeveler (2 dikey kenar) ve yalnızca yatay çizgili booktabs tabloları bu şartı sağlamaz; onlar başlık
    tabanlı bölge tespitiyle bulunur. Kırpma bölgesi ızgaraya katılan çizgilerin birleşimidir."""
    horizontal, vertical = [], []
    for drawing in drawings:
        for item in drawing.get("items", []):
            if item[0] == "l":
                (x0, y0), (x1, y1) = (item[1].x, item[1].y), (item[2].x, item[2].y)
                if abs(y1 - y0) < 1 and abs(x1 - x0) >= 10:
                    horizontal.append((min(x0, x1), y0, max(x0, x1)))
                elif abs(x1 - x0) < 1 and abs(y1 - y0) >= 10:
                    vertical.append((x0, min(y0, y1), max(y0, y1)))
            elif item[0] == "re":
                box = item[1]
                if box.height <= 1.5 and box.width >= 10:
                    horizontal.append((box.x0, (box.y0 + box.y1) / 2, box.x1))
                elif box.width <= 1.5 and box.height >= 10:
                    vertical.append(((box.x0 + box.x1) / 2, box.y0, box.y1))
                elif box.width >= 10 and box.height >= 10:
                    horizontal += [(box.x0, box.y0, box.x1), (box.x0, box.y1, box.x1)]
                    vertical += [(box.x0, box.y0, box.y1), (box.x1, box.y0, box.y1)]
    members = []
    for hx0, hy, hx1 in _merge_collinear(horizontal):
        crossing = [v for v in vertical if v[1] - 1 <= hy <= v[2] + 1 and hx0 - 1 <= v[0] <= hx1 + 1]
        if len({round(v[0] / 2) for v in crossing}) >= 3:
            members.append((hx0, hy, hx1, hy))
            members.extend((v[0], v[1], v[0], v[2]) for v in crossing)
    if not members:
        return None
    return bbox_union(members)


def _merge_collinear(segments, gap=2.0):
    """Aynı y hizasında (±0,5 pt) uç uca veya üst üste gelen yatay segmentleri birleştirir. Bazı PDF'lerde
    (Berardi) satır çizgisi her hücre için ayrı segment olarak çizilir."""
    merged = []
    for x0, y, x1 in sorted(segments, key=lambda s: (round(s[1] * 2), s[0])):
        if merged and abs(merged[-1][1] - y) <= 0.5 and x0 <= merged[-1][2] + gap:
            last = merged[-1]
            merged[-1] = (last[0], last[1], max(last[2], x1))
        else:
            merged.append((x0, y, x1))
    return merged


# --- ana giriş --------------------------------------------------------------------------------------

def detect_page_visuals(page, number, blocks, body_size, gutter, images=None, drawings=None):
    """Döner: (güncellenmiş bloklar, PageVisuals). `page` PyMuPDF sayfasıdır; `images` ve `drawings`
    test veya önbellek için dışarıdan verilebilir."""
    width, height = page.rect.width, page.rect.height
    images = images if images is not None else page.get_image_info(xrefs=True)
    if drawings is None:
        try:
            drawings = page.get_drawings()
        except Exception:
            drawings = []
    try:
        clusters = page.cluster_drawings(drawings=drawings) if drawings else []
    except Exception:
        clusters = []
    visuals = PageVisuals()
    blocks = merge_caption_labels(blocks)

    blocks = _detect_tables(page, number, blocks, body_size, gutter, width, drawings, clusters, visuals)
    blocks = _detect_equations(number, blocks, gutter, width, visuals)
    _equation_text_layer(page, drawings, visuals)
    blocks = _detect_figures(number, blocks, gutter, width, height, images, clusters, visuals)
    return blocks, visuals


# --- tablolar ---------------------------------------------------------------------------------------

def _detect_tables(page, number, blocks, body_size, gutter, width, drawings, clusters, visuals):
    captions = [b for b in blocks if not b.is_image and TABLE_CAPTION_RE.match(b.text.strip())]
    used_captions = set()

    clip = ruled_table_clip(drawings)
    try:
        ruled = page.find_tables(clip=(clip[0] - 2, clip[1] - 2, clip[2] + 2, clip[3] + 2)).tables if clip else []
    except Exception:
        ruled = []
    for table in ruled:
        bbox = tuple(table.bbox)
        rows = [[clean_cell(cell) for cell in row] for row in table.extract()]
        caption = _nearest_caption(captions, bbox, used_captions)
        if caption is None and (table.row_count < 3 or table.col_count < 2):
            continue  # başlıksız küçük çerçeveler (özet kutusu vb.) tablo sayılmaz
        merged = merged_cells_from_bboxes([row.cells for row in table.rows])
        consistent = assess_cells(rows)
        element = TableElement(number, bbox, _caption_number(caption, TABLE_CAPTION_RE), caption,
                               ["find_tables:lines"] + (["caption"] if caption else []), rows=rows,
                               merged=merged, consistent=consistent)
        if not consistent:
            element.raw_text = rows_from_words(page.get_text("words", clip=bbox))
        if caption is not None:
            used_captions.add(id(caption))
        visuals.tables.append(element)

    for caption in captions:
        if id(caption) in used_captions:
            continue
        span = _table_span(caption, blocks, width, gutter)
        region, reasons = _table_region_below(caption, blocks, span, body_size, drawings, clusters, page.rect.height)
        if region is None or any(overlap_ratio(region, t.bbox) > 0.5 for t in visuals.tables):
            continue
        visuals.tables.append(TableElement(number, region, _caption_number(caption, TABLE_CAPTION_RE), caption,
                                           ["caption"] + reasons, consistent=False,
                                           raw_text=rows_from_words(page.get_text("words", clip=region)) or None))
        used_captions.add(id(caption))

    for element in visuals.tables:
        blocks = _absorb(blocks, element, BlockType.table, keep={id(element.caption)} if element.caption else set())
    return blocks


def _nearest_caption(captions, bbox, used, max_gap=40.0):
    best, best_gap = None, None
    for caption in captions:
        if id(caption) in used or horizontal_overlap(caption.bbox, (bbox[0], bbox[2])) < 0.3:
            continue
        gap = bbox[1] - caption.bbox[3] if caption.bbox[3] <= bbox[1] + 2 else caption.bbox[1] - bbox[3]
        if -2 <= gap <= max_gap and (best_gap is None or gap < best_gap):
            best, best_gap = caption, gap
    return best


def _caption_number(caption, pattern):
    if caption is None:
        return None
    match = pattern.match(caption.text.strip())
    return match.group(1) if match else None


def _table_span(caption, blocks, width, gutter):
    """Başlığın sütunu; ancak başlığın hemen altındaki içerik sütun boşluğunu kesiyorsa (sola dayalı başlıklı
    tam genişlik tablo, Elsevier) tam sayfa."""
    span = column_span(caption.bbox, width, gutter)
    if gutter is None or span == (0.0, width):
        return span
    near = [b for b in blocks if b is not caption and b.type != BlockType.header_footer
            and 0 <= b.bbox[1] - caption.bbox[3] + 4 <= TABLE_REGION_MAX_GAP + 4
            and b.bbox[0] < caption.bbox[2] and b.bbox[2] > caption.bbox[0]]
    if near and min(near, key=lambda b: b.bbox[1]).bbox[2] > gutter + 2 and min(near, key=lambda b: b.bbox[1]).bbox[0] < gutter - 2:
        return (0.0, width)
    return span


def _table_region_below(caption, blocks, span, body_size, drawings, clusters, page_height):
    """Başlığın altındaki tablo bölgesi. Döner: (bölge, gerekçeler) veya (None, []).

    1. Yatay çizgiler (booktabs): başlıktan en fazla 30 pt aşağıda başlayan en az iki çizgi; aralarında düzyazı
       bulunmayan son çizgiye kadar. Tablo satırları uzun cümleler olsa da bölge doğru bulunur.
    2. Metin akışı: aynı sütunda düzyazı, başlık, başka bir başlık veya büyük dikey boşluk gelene kadar.
    3. Görsel/çizim: başlığın altında metin yoksa hemen altındaki görsel ya da çizim kümesi (görsel olarak
       gömülmüş tablolar, IEEE).
    Bir sonraki tablo/şekil başlığı veya bölüm başlığı hiçbir durumda aşılmaz.
    """
    span_width = span[1] - span[0]
    below = sorted((b for b in blocks if b is not caption and b.type != BlockType.header_footer
                    and b.bbox[1] >= caption.bbox[3] - 2 and horizontal_overlap(b.bbox, span) >= 0.6),
                   key=lambda b: (b.bbox[1], b.bbox[0]))
    stop_y = page_height
    for block in below:
        if not block.is_image and (CAPTION_RE.match(block.text.strip()) or heading_score(block, body_size)[0] >= 3):
            stop_y = block.bbox[1]
            break
    candidates = [b for b in below if b.bbox[3] <= stop_y + 1]

    rules = [y for y in horizontal_rules(drawings, span) if caption.bbox[3] - 2 <= y <= stop_y]
    if len(rules) >= 2 and rules[0] - caption.bbox[3] <= 30:
        kept = [rules[0]]
        for y in rules[1:]:
            if any(is_prose(b, span_width) and kept[-1] < (b.bbox[1] + b.bbox[3]) / 2 < y for b in candidates):
                break
            kept.append(y)
        if len(kept) >= 2:
            inside = [b for b in candidates if kept[0] - 2 <= (b.bbox[1] + b.bbox[3]) / 2 <= kept[-1] + 2]
            x0 = min([b.bbox[0] for b in inside], default=span[0])
            x1 = max([b.bbox[2] for b in inside], default=span[1])
            region = (x0, min(caption.bbox[3], kept[0]), x1, kept[-1] + 1)
            if inside:
                return region, ["hrules"]

    region, bottom = None, caption.bbox[3]
    for block in candidates:
        if block.bbox[1] - bottom > TABLE_REGION_MAX_GAP:
            break
        if not block.is_image and is_prose(block, span_width):
            break
        region = block.bbox if region is None else bbox_union([region, block.bbox])
        bottom = max(bottom, block.bbox[3])
    if region is not None:
        text_lines = sum(len(b.lines) for b in blocks if not b.is_image and center_inside(b.bbox, region))
        has_image = any(b.is_image and center_inside(b.bbox, region) for b in blocks)
        if region[3] - region[1] >= 10 and (text_lines >= 2 or has_image):
            return region, ["text_region"] + (["image"] if has_image else [])

    visuals_below = [tuple(rect) for rect in clusters] + [b.bbox for b in blocks if b.is_image]
    visuals_below = [v for v in visuals_below if 0 <= v[1] - caption.bbox[3] + 4 <= 30 and v[3] <= stop_y + 1
                     and horizontal_overlap(v, span) >= 0.6 and v[3] - v[1] >= 15]
    if visuals_below:
        return bbox_union(visuals_below), ["drawings_or_image"]
    return None, []


# --- formüller --------------------------------------------------------------------------------------

def _detect_equations(number, blocks, gutter, width, visuals):
    """Numaralı formüller: sağda tek başına duran "(n)" satırı ve aynı yükseklikte solundaki matematiksel satırlar,
    ya da sonu "(n)" ile biten ve matematik içeren satır. Numarasız formüller Faz 07 (FULL mod) konusudur."""
    flow = [(block, line) for block in blocks if block.type == BlockType.paragraph and not block.is_image
            for line in block.lines if not line.vertical]
    claimed = set()
    for block, line in flow:
        text = NUMBER_NOISE_RE.sub("", line.text).strip()
        standalone = _is_number_line(line)
        inline = None if standalone else re.match(r"^(.*\S)\s+" + EQUATION_NUMBER_RE.pattern + r"$", text)
        if standalone:
            span = column_span(line.bbox, width, gutter)
            body = [(b, l) for b, l in flow if id(l) not in claimed and l is not line
                    and _vertical_overlap(l.bbox, line.bbox) and l.bbox[2] <= line.bbox[0] + 2
                    and l.bbox[0] >= span[0] - 2 and line.bbox[0] - l.bbox[2] <= EQUATION_MAX_BODY_DISTANCE
                    and not line_is_prose(l) and not _is_number_line(l)]
            # Kaynakça gibi dar satırlı metinlerdeki "(4)" numara sayılmaz: gövdede matematik olmalı.
            if not body or not any(line_has_math(l) for _, l in body):
                continue
            body = _grow_equation(flow, body, line, claimed, span)
            eq_number = standalone.group(1)
            members = body + [(block, line)]
            raw = _raw_text(l for _, l in sorted(body, key=lambda item: item[1].bbox[1]))
        elif inline and line_has_math(line) and not line_is_prose(line):
            eq_number = inline.group(2)
            members = [(block, line)]
            raw = inline.group(1)
        else:
            continue
        reasons = [f"number:({eq_number})"]
        if any(line_has_math(l) for _, l in members):
            reasons.append("math")
        bbox = bbox_union(l.bbox for _, l in members)
        visuals.equations.append(EquationElement(number, bbox, eq_number, raw + f"  ({eq_number})", reasons,
                                                 line_bboxes=[l.bbox for _, l in members]))
        claimed.update(id(l) for _, l in members)
        visuals.equations[-1].block = RawBlock(number, bbox, [l for _, l in sorted(members, key=lambda m: m[1].bbox[1])],
                                               type=BlockType.equation)
    if not claimed:
        return blocks
    result = []
    for block in blocks:
        if block.is_image or not any(id(l) in claimed for l in block.lines):
            result.append(block)
            continue
        run = []
        for line in block.lines + [None]:
            if line is None or id(line) in claimed:
                if run:
                    result.append(RawBlock(block.page, bbox_union(l.bbox for l in run), run, type=block.type))
                run = []
            else:
                run.append(line)
    result.extend(element.block for element in visuals.equations)
    return result


def _equation_text_layer(page, drawings, visuals):
    """Formül kutusu numara hariç gövde karakterlerine daraltılır (görsel model kırpımı numarayı içermesin) ve metin
    katmanından LaTeX kurulur. Kurulamayan formülde `latex` boş kalır."""
    if not visuals.equations:
        return
    lines = page_lines(page)
    for element in visuals.equations:
        try:
            glyphs = strip_number(equation_glyphs(lines, element.line_bboxes), element.number)
            if glyphs:
                element.bbox = glyph_region(glyphs)
                element.latex = text_layer_latex(glyphs, fraction_rules(drawings, element.bbox))
        except Exception:  # yeniden kurma hatası formül tespitini ve sayfanın geri kalanını etkilememeli
            element.latex = None


def _vertical_overlap(a, b):
    """Satırlar dikeyde gerçekten örtüşüyor mu: kısa satırın yüksekliğinin en az `EQUATION_BODY_MIN_OVERLAP` oranı.
    Bitişik satır aralığı (üstteki/alttaki düzyazı) gövdeye alınmaz."""
    overlap = min(a[3], b[3]) - max(a[1], b[1])
    return overlap > 0 and overlap >= EQUATION_BODY_MIN_OVERLAP * min(a[3] - a[1], b[3] - b[1])


def _is_number_line(line):
    """Tek başına duran dar "(n)" satırı; eşleşme nesnesi döner."""
    match = EQUATION_NUMBER_RE.fullmatch(NUMBER_NOISE_RE.sub("", line.text).strip())
    return match if match and line.bbox[2] - line.bbox[0] <= EQUATION_NUMBER_MAX_WIDTH else None


def _raw_text(lines):
    """Ham formül metni: satırlardaki kontrol ve özel kullanım glifleri (büyük parantez parçaları) atılır."""
    texts = (NUMBER_NOISE_RE.sub("", l.text).strip() for l in lines)
    return "\n".join(t for t in texts if t)


def _grow_equation(flow, body, number_line, claimed, span):
    """Çok satırlı formüller: gövdeyle dikeyde örtüşen ya da hemen üstünde/altında (≤4 pt) aynı yatay aralıkta
    matematik içeren satırlar (alt/üst sınırlar, kesir pay/paydaları, cases satırları). Gövde kutusunun tamamen
    içinde kalan satırlar (ör. "1", "700") matematik fontu olmasa da alınır."""
    members = list(body)
    changed = True
    while changed:
        changed = False
        union = bbox_union(l.bbox for _, l in members)
        for block, line in flow:
            if id(line) in claimed or line is number_line or any(line is l for _, l in members):
                continue
            near = union[1] - line.bbox[3] <= 4 and line.bbox[1] - union[3] <= 4
            inside = overlap_ratio(line.bbox, union) >= 0.9
            if near and line.bbox[2] <= number_line.bbox[0] + 2 and line.bbox[0] >= max(union[0] - 60, span[0] - 2) \
                    and (inside or line_has_math(line)) and not line_is_prose(line):
                members.append((block, line))
                changed = True
    return members


# --- şekiller ---------------------------------------------------------------------------------------

@dataclass
class _Visual:
    bbox: tuple
    xref: int | None
    kind: str
    axis_aligned: bool = True


def _page_visuals(images, clusters, tables, width, height):
    page_area = width * height
    result = []
    for info in images:
        bbox = tuple(info["bbox"])
        if area(bbox) < MIN_IMAGE_AREA_RATIO * page_area:
            continue
        transform = info.get("transform", (1, 0, 0, 1, 0, 0))
        aligned = abs(transform[1]) < 1e-3 and abs(transform[2]) < 1e-3 and transform[0] > 0 and transform[3] > 0
        result.append(_Visual(bbox, info.get("xref") or None, "image", aligned))
    for rect in clusters:
        bbox = tuple(rect)
        if area(bbox) < MIN_DRAWING_CLUSTER_AREA_RATIO * page_area or rect.height < 15 or rect.width < 30:
            continue
        if any(overlap_ratio(bbox, table.bbox) > 0.5 for table in tables):
            continue
        result.append(_Visual(bbox, None, "drawings"))
    return result


def _detect_figures(number, blocks, gutter, width, height, images, clusters, visuals):
    candidates = _page_visuals(images, clusters, visuals.tables, width, height)
    candidates = [v for v in candidates if not any(overlap_ratio(v.bbox, t.bbox) > 0.5 for t in visuals.tables)]
    assigned = set()
    captions = sorted((b for b in blocks if not b.is_image and b.type == BlockType.paragraph
                       and FIGURE_CAPTION_RE.match(b.text.strip())), key=lambda b: b.bbox[1])
    all_captions = [b for b in blocks if not b.is_image and CAPTION_RE.match(b.text.strip())]
    for caption in captions:
        span = column_span(caption.bbox, width, gutter)
        pool = [v for v in candidates if id(v) not in assigned and horizontal_overlap(v.bbox, span) >= 0.5]
        above = [v for v in pool if v.bbox[3] <= caption.bbox[1] + 4 and caption.bbox[1] - v.bbox[3] <= FIGURE_CAPTION_MAX_GAP]
        below = [v for v in pool if v.bbox[1] >= caption.bbox[3] - 4 and v.bbox[1] - caption.bbox[3] <= 40]
        seeds = above or below
        if not seeds:
            continue
        seed = max(seeds, key=lambda v: v.bbox[3]) if above else min(seeds, key=lambda v: v.bbox[1])
        group = [seed]
        region = seed.bbox
        grew = True
        while grew:
            grew = False
            expanded = (region[0] - FIGURE_GROUP_GAP, region[1] - FIGURE_GROUP_GAP,
                        region[2] + FIGURE_GROUP_GAP, region[3] + FIGURE_GROUP_GAP)
            for visual in pool:
                if visual in group or area(intersection(visual.bbox, expanded)) <= 0:
                    continue
                if _caption_between(all_captions, caption, visual.bbox, region):
                    continue
                if (above and visual.bbox[3] > caption.bbox[1] + 4) or (not above and visual.bbox[1] < caption.bbox[3] - 4):
                    continue
                group.append(visual)
                region = bbox_union([region, visual.bbox])
                grew = True
        assigned.update(id(v) for v in group)
        images_in = [v for v in group if v.kind == "image"]
        xref = images_in[0].xref if (len(group) == 1 and images_in and images_in[0].axis_aligned) else None
        reasons = ["caption"] + sorted({v.kind for v in group})
        visuals.figures.append(FigureElement(number, region, _caption_number(caption, FIGURE_CAPTION_RE), caption, reasons, xref))

    for visual in candidates:
        if id(visual) in assigned or visual.kind != "image" or area(visual.bbox) < UNCAPTIONED_FIGURE_AREA_RATIO * width * height:
            continue
        visuals.figures.append(FigureElement(number, visual.bbox, None, None, ["image", "uncaptioned"],
                                             visual.xref if visual.axis_aligned else None))

    for element in visuals.figures:
        blocks = _absorb(blocks, element, BlockType.figure, keep={id(element.caption)} if element.caption else set(),
                         text_min_inside=0.8, keep_prose=True)
    return blocks


def _caption_between(captions, own_caption, bbox, region):
    """Başka bir tablo/şekil başlığı aday görsel ile mevcut bölge arasında dikeyde duruyorsa görsel eklenmez."""
    top, bottom = sorted([(bbox[1] + bbox[3]) / 2, (region[1] + region[3]) / 2])
    return any(c is not own_caption and top < (c.bbox[1] + c.bbox[3]) / 2 < bottom
               and horizontal_overlap(c.bbox, (min(bbox[0], region[0]), max(bbox[2], region[2]))) > 0.3 for c in captions)


# --- blok birleştirme -------------------------------------------------------------------------------

def _absorb(blocks, element, block_type, keep, text_min_inside=None, keep_prose=False):
    """Bölgeye düşen blokları tek bir `block_type` bloğunda toplar. Tablo/formül bölgesinde merkezi içeride olan
    bloklar, şekillerde alanının en az `text_min_inside` kadarı içeride olan (etiket) bloklar alınır."""
    region = element.bbox
    absorbed, remaining = [], []
    for block in blocks:
        if id(block) in keep or block.type in (BlockType.header_footer, BlockType.table, BlockType.equation, BlockType.figure):
            remaining.append(block)
            continue
        if block.is_image:
            inside = overlap_ratio(block.bbox, region) >= 0.8
        elif text_min_inside is not None:
            inside = overlap_ratio(block.bbox, region) >= text_min_inside and not (keep_prose and len(block.lines) >= 3)
        else:
            inside = center_inside(block.bbox, region)
        (absorbed if inside else remaining).append(block)
    lines = sorted((line for block in absorbed for line in block.lines), key=lambda l: (l.bbox[1], l.bbox[0]))
    merged = RawBlock(element.page, region, lines if block_type != BlockType.figure else [], type=block_type)
    element.block = merged
    remaining.append(merged)
    return remaining
