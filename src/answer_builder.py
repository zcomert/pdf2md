"""Prompt cevabı `A.md` (§20.3, §19.1, §19.4): yapı ve değerler doğrulanmış Extraction'dan deterministik yazılır.
Başlıklar `plan.output_outline` sırasını izler; istenmeyen bölüm eklenmez; bulunamayan bilgi `not_found`."""
import re
from dataclasses import dataclass, field

from .evidence_verifier import normalize_numbers
from .field_catalog import FIELDS, GROUP_LABELS, label
from .markdown_builder import LATEX_UNVERIFIED, TABLE_STRUCTURE_UNAVAILABLE, _escape_inline, _fenced, _front_matter

NOT_FOUND = "not_found"
UNCLEAR = "[unclear]"
MARKERS = ("[unverified]", "[source_not_found]", UNCLEAR, LATEX_UNVERIFIED, TABLE_STRUCTURE_UNAVAILABLE)
TABLE_WORDS = {"tablo", "tablolar", "table", "tables"}
EQUATION_WORDS = {"formül", "formüller", "denklem", "denklemler", "equation", "equations", "formula", "formulas"}
STOPWORDS = {"ve", "ile", "için", "bir", "the", "and", "of", "for", "in", "on", "en", "da", "de"}
TEXTS = {
    "tr": {"equation": "Denklem", "description": "Açıklama", "source": "Kaynak", "conflict": "Çelişen değerler",
           "dataset": "veri seti"},
    "en": {"equation": "Equation", "description": "Description", "source": "Source", "conflict": "Conflicting values",
           "dataset": "dataset"},
}
# Satır içindeki bağımsız sayılar (ResNet-50, p5-b12 gibi adların parçaları hariç)
STANDALONE_NUMBER_RE = re.compile(r"(?<![\w\-.,])%?\d+(?:[.,]\d+)*(?:\s?%)?(?![\w\-])")
CITATION_RE = re.compile(r"\*\([^*]*\)\*")


@dataclass
class _Line:
    text: str
    checked: bool = True  # güvenlik ağı taraması (tablolar ve formüller hariç)


@dataclass
class Answer:
    markdown: str
    warnings: list = field(default_factory=list)


def _texts(language):
    return TEXTS["tr" if language == "tr" else "en"]


# --- Başlık–alan eşleme -------------------------------------------------------------------------------------------

def _words(text):
    text = (text or "").replace("İ", "i").replace("I", "ı").casefold()
    return {w for w in re.findall(r"\w{3,}", text) if w not in STOPWORDS}


def _similar(a, b):
    k = min(len(a), len(b), 5)
    common = 0
    for x, y in zip(a, b):
        if x != y:
            break
        common += 1
    return common >= max(3, k - 1)


def _overlap(left, right):
    return sum(1 for a in left if any(_similar(a, b) for b in right))


def _field_words(key, plan):
    spec = FIELDS.get(key)
    if spec is None:
        custom = next((c.description for c in plan.custom_fields if c.key == key), "")
        return _words(custom) | _words(key.split(".", 1)[-1].replace("_", " ")), set()
    return (_words(spec.label_tr) | _words(spec.label_en) | _words(spec.name.replace("_", " ")),
            set().union(*(_words(g) for g in GROUP_LABELS.get(spec.group, ()))))


def assign_fields(plan):
    """Döner: [(başlık, [alan anahtarları])]. Her alan en çok benzeyen başlığa gider (alan etiketi ×2, grup adı ×1).
    Eşleşmeyen alanlar boş başlıklara sırayla, o da yoksa kendi etiketiyle sona eklenir."""
    headings = list(plan.output_outline)
    assigned = {index: [] for index in range(len(headings))}
    unmatched = []
    for key in plan.requested_fields:
        field_words, group_words = _field_words(key, plan)
        best, best_score = None, 0
        for index, heading in enumerate(headings):
            words = _words(heading)
            score = 2 * _overlap(words, field_words) + _overlap(words, group_words)
            if score > best_score:
                best, best_score = index, score
        if best is None:
            unmatched.append(key)
        else:
            assigned[best].append(key)
    empty = [index for index in assigned if not assigned[index] and not _is_table_heading(headings[index])]
    if unmatched and len(unmatched) == len(empty):
        for index, key in zip(empty, unmatched):
            assigned[index].append(key)
        unmatched = []
    sections = [(headings[index], assigned[index]) for index in range(len(headings))]
    sections += [(label(key, plan.output_language), [key]) for key in unmatched]
    return sections


def _is_table_heading(heading):
    return bool(_words(heading) & TABLE_WORDS)


# --- Gösterim -----------------------------------------------------------------------------------------------------

def citation(evidence, style):
    """§19.4 kaynak etiketi; kapatılamaz. Sayfası bilinen her farklı kanıt için bir etiket."""
    tags = []
    for item in evidence:
        if not item.resolved or item.page is None:
            continue
        extra = f", {item.table}" if item.table else f", {item.figure}" if item.figure else ""
        tag = style.format(page=item.page, table_or_figure=extra)
        if tag not in tags:
            tags.append(tag)
    return f" *{' '.join(tags[:4])}*" if tags else ""


def _marker(verification):
    return f" [{verification}]" if verification in ("unverified", "source_not_found") else ""


def _format_scalar(value, value_text):
    if value_text:
        return value_text
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def render_prompt_answer(document, plan, extraction, ctx, citation_style):
    texts = _texts(plan.output_language)
    lines = []
    if ctx.front_matter:
        lines.append(_Line(_front_matter(ctx).rstrip("\n"), checked=False))
    tables = {t.id: t for t in document.tables}
    equations = {e.id: e for e in document.equations}
    sections = assign_fields(plan)
    table_heading = next((i for i, (h, _) in enumerate(sections) if _is_table_heading(h)), None)
    if table_heading is None:
        table_heading = next((i for i, (_, keys) in enumerate(sections)
                              if any(getattr(FIELDS.get(k), "value_type", "") in ("results", "table") for k in keys)),
                             None)
    for index, (heading, keys) in enumerate(sections):
        lines.append(_Line(f"## {_escape_inline(heading)}", checked=False))
        body = []
        for key in keys:
            body += _render_field(key, plan, extraction, equations, citation_style, texts, single=len(keys) == 1)
        if index == table_heading:
            for table_id in extraction.tables_selected:
                body += _render_table(tables[table_id], citation_style, document)
        if not body:
            body = [_Line(NOT_FOUND)]
        lines += body

    warnings = []
    allowed = _allowed_numbers(plan, extraction)
    rendered = []
    for line in lines:
        if not line.checked:
            rendered.append(line.text)
            continue
        physical = []
        for text in line.text.split("\n"):
            if not any(marker in text for marker in MARKERS):
                unverified = [n for n in STANDALONE_NUMBER_RE.findall(CITATION_RE.sub("", text))
                              if not normalize_numbers(n) & allowed]
                if unverified:
                    text += " [unverified]"
                    warnings.append(f"unverified_number_marked: {', '.join(unverified[:3])}")
            physical.append(text)
        rendered.append("\n".join(physical))
    markdown = "\n\n".join(rendered).rstrip() + "\n"
    return Answer(markdown, list(dict.fromkeys(warnings)))


def _render_field(key, plan, extraction, equations, style, texts, single):
    field_value = extraction.fields.get(key)
    spec = FIELDS.get(key)
    value_type = spec.value_type if spec else "str"
    title = label(key, plan.output_language) if spec else next(
        (c.description for c in plan.custom_fields if c.key == key), key)
    prefix = "" if single else f"**{_escape_inline(title)}:** "
    lines = []
    if value_type == "results":
        items = [r for r in extraction.results if r.field == key]
        if items:
            if not single:
                lines.append(_Line(f"**{_escape_inline(title)}:**", checked=False))
            lines.append(_Line("\n".join(_render_result(r, style, texts) for r in items)))
            return lines
    if value_type == "equations":
        if extraction.equations_selected:
            return lines + _render_equations(extraction, equations, style, texts)
    if field_value is None or field_value.status == "not_found":
        return [_Line(f"{prefix}{NOT_FOUND}")]
    if field_value.status == "unclear":
        return [_Line(f"{prefix}{UNCLEAR}")]
    if field_value.value in (None, []):
        return [_Line(f"{prefix}{NOT_FOUND}")]
    cite = citation(field_value.evidence, style)
    marker = _marker(field_value.verification)
    if isinstance(field_value.value, list):
        items = "\n".join(f"- {_escape_inline(str(item))}" for item in field_value.value)
        # Tek alanlı başlıkta işaret ve kaynak son maddeye, çok alanlıda etiket satırına yazılır.
        text = f"{items}{marker}{cite}" if single else f"{prefix.rstrip()}{marker}{cite}\n{items}"
        result = [_Line(text)]
    else:
        result = [_Line(f"{prefix}{_escape_inline(_format_scalar(field_value.value, field_value.value_text))}"
                        f"{marker}{cite}")]
    conflict = next((c for c in extraction.conflicts if c.field == key), None)
    if conflict:
        values = "; ".join(f"{_escape_inline(_format_scalar(v.value, None))}{citation(v.evidence, style)}"
                           for v in conflict.values)
        result.append(_Line(f"{texts['conflict']}: {values}"))
    return result


def _render_result(result, style, texts):
    head = " — ".join(part for part in (result.model, result.metric) if part)
    value = result.value_text or ""
    dataset = f" ({texts['dataset']}: {result.dataset})" if result.dataset else ""
    if head and value:
        text = f"{head}: {value}"
    else:
        text = head or result.claim
        if value and value not in text:
            text = f"{text}: {value}"
    return f"- {_escape_inline(text)}{_marker(result.verification)}{_escape_inline(dataset)}{citation(result.evidence, style)}"


def _render_equations(extraction, equations, style, texts):
    lines = []
    for number, item in enumerate(extraction.equations_selected, start=1):
        equation = equations[item.equation_id]
        lines.append(_Line(f"### {texts['equation']} {equation.number or number}", checked=False))
        if equation.latex:
            marker = f" {LATEX_UNVERIFIED}" if equation.latex_valid is False else ""
            lines.append(_Line(f"$$\n{equation.latex}\n$${marker}", checked=False))
        else:
            lines.append(_Line(_fenced(equation.raw_text or "") + "\n\n[latex_unavailable]", checked=False))
        if item.description:
            lines.append(_Line(f"{texts['description']}: {_escape_inline(item.description)}"))
        tag = citation(item.evidence, style).strip().strip("*")
        if tag:
            lines.append(_Line(f"{texts['source']}: {tag}", checked=False))
    return lines


def _render_table(table, style, document):
    title = f"Table {table.number}" if table.number else "Table"
    caption = table.caption or title
    page_style = style.format(page=table.page, table_or_figure=f", {title}")
    lines = [_Line(f"**{_escape_inline(caption)}** *{page_style}*", checked=False)]
    if table.markdown:
        lines.append(_Line(table.markdown, checked=False))
    else:
        body = _fenced(table.raw_text) + "\n\n" if table.raw_text else ""
        lines.append(_Line(body + TABLE_STRUCTURE_UNAVAILABLE, checked=False))
    return lines


def _allowed_numbers(plan, extraction):
    """Güvenlik ağında işaret gerektirmeyen sayılar: doğrulanmış değerler, başlıklar ve etiketler."""
    allowed = set()
    for heading in plan.output_outline:
        allowed |= normalize_numbers(heading)
    for key, value in extraction.fields.items():
        if value.status == "found" and value.verification == "verified":
            allowed |= normalize_numbers(value.value_text or "")
            items = value.value if isinstance(value.value, list) else [value.value]
            for item in items:
                allowed |= normalize_numbers(str(item))
        elif value.status == "found" and value.verification is None:
            items = value.value if isinstance(value.value, list) else [value.value]
            for item in items:
                allowed |= normalize_numbers(str(item))  # sayı içermeyen değerler (doğrulama gerekmez)
    for result in extraction.results:
        if result.verification == "verified":
            allowed |= normalize_numbers(result.value_text or "") | normalize_numbers(result.claim)
    return allowed
