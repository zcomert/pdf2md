"""Metin modeline verilecek belge bağlamı (§17.2): blok kimlikleri, sayfa işaretleri, tablolar Markdown, formüller
LaTeX. Belge bağlama sığmıyorsa plan alanlarıyla ilgili bölümler seçilir ve blok sınırında parçalara bölünür."""
import re
from dataclasses import dataclass, field

from .document_model import BlockType
from .field_catalog import FIELDS, FULL_CONVERSION
from .llm_client import estimate_tokens
from .markdown_builder import reflow

SKIPPED_TYPES = {BlockType.header_footer, BlockType.reference}
# Sistem promptu, alan listesi ve yanıt şeması için ayrılan pay
PROMPT_OVERHEAD_TOKENS = 2500
FRONT_BLOCKS = 12  # künye için belgenin başındaki bloklar her zaman seçilir


@dataclass
class Item:
    order: int
    page: int
    text: str
    block_ids: tuple
    section_id: str | None = None

    @property
    def tokens(self):
        return estimate_tokens(self.text)


@dataclass
class Chunk:
    text: str
    pages: list = field(default_factory=list)
    block_ids: set = field(default_factory=set)

    @property
    def tokens(self):
        return estimate_tokens(self.text)


def context_budget(num_ctx, max_output_tokens):
    return max(1000, num_ctx - max_output_tokens - PROMPT_OVERHEAD_TOKENS)


def _data_safe(text):
    """PDF metni `<document>` sınırını kapatamaz (prompt injection, §10.4)."""
    return re.sub(r"</?\s*document\s*>", lambda m: m.group(0).replace("document", "document_"), text,
                  flags=re.IGNORECASE)


def build_items(document):
    """Okuma sırasında model girdisi öğeleri. Tablo/formül/şekil blokları kendi içerikleriyle yazılır."""
    tables = {t.id: t for t in document.tables}
    equations = {e.id: e for e in document.equations}
    figures = {f.id: f for f in document.figures}
    section_of = _section_lookup(document)
    items = []
    for block in sorted(document.blocks, key=lambda b: b.order):
        if block.type in SKIPPED_TYPES:
            continue
        text = _render(block, tables, equations, figures)
        if text:
            items.append(Item(block.order, block.page, _data_safe(text), (block.id,), section_of(block.order)))
    return items


def _render(block, tables, equations, figures):
    tag = f"[{block.id}]"
    if block.type == BlockType.table and block.ref_id in tables:
        table = tables[block.ref_id]
        label = f"Table {table.number}" if table.number else "table"
        if table.markdown:
            content = table.markdown
        elif table.raw_text:
            content = f"(cells not structured; raw text)\n{table.raw_text}"
        else:
            content = "[table_structure_unavailable]"
        return f"{tag} [table id={table.id} label=\"{label}\"]\n{content}"
    if block.type == BlockType.equation and block.ref_id in equations:
        equation = equations[block.ref_id]
        number = f" number=({equation.number})" if equation.number else ""
        body = f"$${equation.latex}$$" if equation.latex else (equation.raw_text or "[latex_unavailable]")
        return f"{tag} [equation id={equation.id}{number}] {body}"
    if block.type == BlockType.figure:
        figure = figures.get(block.ref_id)
        if figure is None:
            return None
        return f"{tag} [figure id={figure.id}] {figure.caption or ''}".rstrip()
    text = block.text.strip()
    if not text:
        return None
    if block.type == BlockType.heading:
        return f"{tag} {'#' * (block.heading_level or 1)} {reflow(text)}"
    if block.type == BlockType.list:
        return f"{tag} {text}"
    return f"{tag} {reflow(text)}"


def _section_lookup(document):
    sections = sorted(document.sections, key=lambda s: (s.start_order, -s.level))

    def find(order):
        match = None
        for section in sections:
            if section.start_order <= order <= section.end_order:
                match = section  # en derin (en son başlayan) bölüm
        return match.id if match else None
    return find


def join_items(items):
    lines, page = [], None
    for item in items:
        if item.page != page:
            lines.append(f"<!-- page: {item.page} -->")
            page = item.page
        lines.append(item.text)
    return "\n".join(lines)


def build_chunks(document, plan, num_ctx, max_output_tokens):
    """Döner: (parçalar, seçim açıklaması). Belge sığıyorsa tek parça; sığmıyorsa ilgili bölümler, yine sığmıyorsa
    blok sınırında bölünmüş parçalar."""
    budget = context_budget(num_ctx, max_output_tokens)
    items = build_items(document)
    whole = join_items(items)
    if estimate_tokens(whole) <= budget:
        return [_chunk(items)], "tüm belge tek parça"
    note = "tüm belge (bölüm seçimi yok)"
    if not plan.needs.full_text and FULL_CONVERSION not in plan.requested_fields:
        selected = select_items(document, plan, items)
        if selected and len(selected) < len(items):
            note = f"{len(selected)}/{len(items)} blok seçildi (ilgili bölümler)"
            items = selected
    return split_items(items, budget), note


def select_items(document, plan, items):
    """§17.2.1: istenen alanların ipucu bölümleri ve anahtar kelimeleri eşleşen bölümler; belgenin başı (künye)
    her zaman; sonuç/tablo isteniyorsa tüm tablolar, formül isteniyorsa tüm formüller."""
    hints, keywords = set(), set()
    for key in plan.requested_fields:
        spec = FIELDS.get(key)
        if spec:
            hints |= {_norm(name) for name in spec.hint_sections}
            keywords |= _words(spec.label_en) | _words(spec.label_tr)
    for custom in plan.custom_fields:
        keywords |= _words(custom.description) | _words(custom.key.split(".", 1)[1].replace("_", " "))
    selected_sections = set()
    for section in document.sections:
        title = _norm(section.title)
        if any(hint and (hint in title or title in hint) for hint in hints) or _words(section.title) & keywords:
            selected_sections.add(section.id)
    # Alt bölümler üst bölümün seçimini miras alır
    changed = True
    while changed:
        changed = False
        for section in document.sections:
            if section.parent_id in selected_sections and section.id not in selected_sections:
                selected_sections.add(section.id)
                changed = True
    want_tables = plan.needs.tables
    want_equations = plan.needs.equations
    chosen = []
    for index, item in enumerate(items):
        text = item.text
        if (index < FRONT_BLOCKS or item.section_id in selected_sections
                or (want_tables and "[table id=" in text) or (want_equations and "[equation id=" in text)
                or (want_tables and re.match(r"\[p\d+-b\d+\] (Table|Tablo)\s+\d", text))):
            chosen.append(item)
    return chosen


def split_items(items, budget):
    chunks, current = [], []
    for item in items:
        if current and estimate_tokens(join_items(current + [item])) > budget:
            chunks.append(_chunk(current))
            current = []
        current.append(item)
    if current:
        chunks.append(_chunk(current))
    return chunks


def _chunk(items):
    return Chunk(join_items(items), sorted({item.page for item in items}),
                 {block_id for item in items for block_id in item.block_ids})


def _norm(text):
    text = re.sub(r"^[\dIVXivx.\s)]+", "", text or "")
    return re.sub(r"\s+", " ", text).strip().casefold()


def _words(text):
    return {word for word in re.findall(r"\w{4,}", (text or "").casefold())}
