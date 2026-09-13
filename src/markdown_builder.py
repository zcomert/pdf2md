"""`document.json`'dan Markdown üretimi. Faz 04: varsayılan prompt için deterministik tam dönüşüm (§16.3)."""
import re
from dataclasses import dataclass, field

import yaml

from .document_model import BlockType, PageClass
from .layout_analyzer import normalize_heading_text

UNREADABLE_PAGE = "[unreadable_page]"
BULLET_RE = re.compile(r"^[•▪◦·*–—-]\s+")
ORDERED_RE = re.compile(r"^(\d{1,3})[.)]\s+")
MARKED_RE = re.compile(r"^(\([a-zA-Z0-9]{1,4}\)|[a-zA-Z][.)])\s+")
WORD_RE = re.compile(r"[\w'-]+", re.UNICODE)
# Satır başında Markdown sözdizimi olarak yorumlanabilecek metinler
LINE_START_ESCAPE_RE = re.compile(r"^(#{1,6}\s|>|[-+*]\s|\d{1,9}[.)]\s|={3,}|-{3,}|```|~~~)")
# Metinde HTML etiketi gibi yorumlanabilecek "<" (ör. "<script", "</p", "<!--"); "p<0.05" dokunulmaz
HTML_TAG_RE = re.compile(r"<(?=[A-Za-z/!?])")


@dataclass(frozen=True)
class RenderContext:
    source_path: str
    sha256: str
    generated: str
    mode: str
    status: str
    prompt_sha256: str | None = None
    models: dict = field(default_factory=dict)
    front_matter: bool = True
    page_markers: bool = True


def build_full_conversion(document, ctx):
    """Aynı `document` ve `ctx` için bayt bayt aynı çıktı üretir (üretim zamanı `ctx.generated` ile verilir)."""
    vocabulary = _hyphenated_vocabulary(document)
    parts = []
    if ctx.front_matter:
        parts.append(_front_matter(ctx))

    blocks_by_page = {}
    for block in document.blocks:
        blocks_by_page.setdefault(block.page, []).append(block)

    body = []
    for page in document.pages:
        body.extend(_page_opening(page, ctx))
        previous_type = None
        for block in blocks_by_page.get(page.number, []):
            rendered = _render_block(block, vocabulary)
            if rendered is None:
                continue
            if block.type == BlockType.list and previous_type == BlockType.list and body:
                body[-1] = body[-1] + "\n" + rendered
            else:
                body.append(rendered)
            previous_type = block.type
    parts.append("\n\n".join(body))
    return "\n".join(part for part in parts if part).rstrip() + "\n"


def unreadable_pages(document):
    """OCR veya görsel model ile metni çıkarılmamış taranmış sayfalar (§11.4)."""
    return [page.number for page in document.pages if page.page_class == PageClass.scanned and not page.ocr_applied]


def _front_matter(ctx):
    data = {"source": ctx.source_path, "sha256": ctx.sha256, "generated": ctx.generated, "mode": ctx.mode,
            "prompt_sha256": ctx.prompt_sha256, "models": dict(sorted(ctx.models.items())), "status": ctx.status}
    dumped = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=None, width=1000)
    return f"---\n{dumped}---\n"


def _page_opening(page, ctx):
    lines = []
    if ctx.page_markers:
        suffix = " [parse_error]" if page.parse_error else ""
        lines.append(f"<!-- page: {page.number}{suffix} -->")
    if page.page_class == PageClass.scanned and not page.ocr_applied:
        lines.append(UNREADABLE_PAGE)
    return lines


def _render_block(block, vocabulary):
    if block.type in (BlockType.header_footer, BlockType.figure):
        # Şekil görselleri ve referansları Faz 05'te `assets/` ile eklenir.
        return None
    text = block.text.strip()
    if not text:
        return None
    if block.type == BlockType.heading:
        level = min(6, max(1, block.heading_level or 1))
        return f"{'#' * level} {_escape_inline(normalize_heading_text(reflow(block.text, vocabulary)))}"
    if block.type == BlockType.list:
        return _render_list(block, vocabulary)
    if block.type == BlockType.algorithm:
        return "```text\n" + block.text.strip("\n") + "\n```"
    return _escape_paragraph(reflow(block.text, vocabulary))


def _render_list(block, vocabulary):
    items = []
    for line in block.text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if items and not (BULLET_RE.match(stripped) or ORDERED_RE.match(stripped) or MARKED_RE.match(stripped)):
            items[-1] = items[-1] + "\n" + stripped  # önceki maddenin devam satırı
        else:
            items.append(stripped)
    rendered = []
    for item in items:
        content = reflow(item, vocabulary)
        if match := BULLET_RE.match(content):
            rendered.append("- " + _escape_inline(content[match.end():]))
        elif match := ORDERED_RE.match(content):
            rendered.append(f"{match.group(1)}. " + _escape_inline(content[match.end():]))
        elif match := MARKED_RE.match(content):
            rendered.append(f"- {match.group(1)} " + _escape_inline(content[match.end():]))
        else:
            rendered.append("- " + _escape_inline(content))
    return "\n".join(rendered)


def reflow(text, vocabulary=frozenset()):
    """PDF satırlarını tek paragraf satırında birleştirir; satır sonu tirelemesini çözer.

    Satır tire ile bitiyor ve sonraki satır küçük harfle başlıyorsa: tireli biçim belgede başka yerde
    geçiyorsa tire korunur ("pre-trained"), aksi halde kelime birleştirilir ("classifi-cation"). Sonraki
    satır büyük harf veya rakamla başlıyorsa tire korunur ("Speaker-Dependent").
    """
    lines = [line.strip() for line in text.replace("­\n", "").split("\n")]
    result = ""
    for line in lines:
        if not line:
            continue
        if not result:
            result = line
            continue
        if result.endswith("-") and len(result) >= 2 and not result[-2].isspace():
            left_words, right_words = WORD_RE.findall(result[:-1]), WORD_RE.findall(line)
            left = left_words[-1] if left_words else ""
            right = right_words[0] if right_words else ""
            if result[-2].isalpha() and line[:1].islower() and f"{left}-{right}".casefold() not in vocabulary:
                result = result[:-1] + line
            else:
                result = result + line  # "Speaker-Dependent", "1990-2000": tire korunur, boşluk eklenmez
        else:
            result = result + " " + line
    return re.sub(r"[ \t]{2,}", " ", result).strip()


def _hyphenated_vocabulary(document):
    words = set()
    for block in document.blocks:
        for line in block.text.split("\n"):
            # Satır sonundaki tire hariç, satır içinde geçen tireli kelimeler
            for word in WORD_RE.findall(line.rstrip("-")):
                if "-" in word.strip("-"):
                    words.add(word.strip("-").casefold())
    return frozenset(words)


def _escape_inline(text):
    return HTML_TAG_RE.sub("&lt;", text)


def _escape_paragraph(text):
    text = _escape_inline(text)
    if not LINE_START_ESCAPE_RE.match(text):
        return text
    if ordered := re.match(r"^(\d{1,9})([.)])", text):
        return f"{ordered.group(1)}\\{ordered.group(2)}{text[ordered.end():]}"
    return "\\" + text
