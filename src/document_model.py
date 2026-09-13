"""`document.json` şeması (§16.1). Şema sürümü değişirse önbellekteki tüm belgeler geçersiz sayılır;
bu yüzden Faz 05–07'de doldurulacak alanlar (tablo, formül, şekil) şimdiden tanımlıdır."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

DOCUMENT_SCHEMA_VERSION = "1.0"

BBox = tuple[float, float, float, float]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceMethod(str, Enum):
    text = "text"
    ocr = "ocr"
    vision = "vision"


class BlockType(str, Enum):
    heading = "heading"
    paragraph = "paragraph"
    list = "list"
    table = "table"
    equation = "equation"
    figure = "figure"
    algorithm = "algorithm"
    caption = "caption"
    footnote = "footnote"
    reference = "reference"
    header_footer = "header_footer"


class PageClass(str, Enum):
    text = "text"
    mixed = "mixed"
    scanned = "scanned"


class Line(StrictModel):
    text: str
    bbox: BBox
    font: str
    size: float
    bold: bool = False
    italic: bool = False


class Block(StrictModel):
    id: str = Field(description="p{sayfa}-b{sayfa içi okuma sırası}")
    type: BlockType
    page: int = Field(ge=1)
    bbox: BBox
    text: str
    lines: list[Line] = []
    source_method: SourceMethod = SourceMethod.text
    font: str | None = None
    size: float | None = None
    bold: bool = False
    italic: bool = False
    heading_level: int | None = Field(None, ge=1, le=6)
    order: int = Field(ge=0, description="Belge genelinde okuma sırası")
    column: int | None = Field(None, description="0: sol/tek sütun, 1: sağ sütun, None: tam genişlik")
    ref_id: str | None = None


class Page(StrictModel):
    number: int = Field(ge=1)
    width: float
    height: float
    page_class: PageClass = PageClass.text
    char_count: int = 0
    body_char_count: int = Field(0, description="Üst/alt bilgi ve kenar damgaları hariç karakter sayısı")
    text_block_count: int = 0
    image_area_ratio: float = Field(0.0, ge=0, le=1)
    drawing_count: int | None = None
    columns: int = 1
    gutter_x: float | None = None
    reading_order_uncertain: bool = False
    vector_text_suspected: bool = False
    ocr_applied: bool = False
    parse_error: str | None = None


class Section(StrictModel):
    id: str
    title: str
    level: int = Field(ge=1, le=6)
    number: str | None = None
    heading_block_id: str
    start_order: int
    end_order: int
    parent_id: str | None = None


class TableCellSpan(StrictModel):
    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1


class Table(StrictModel):
    id: str
    number: str | None = None
    caption: str | None = None
    page: int
    bbox: BBox
    cells: list[list[str | None]] = []
    merged_cells: list[TableCellSpan] = []
    markdown: str | None = None
    html: str | None = None
    source_method: SourceMethod = SourceMethod.text
    consistent: bool | None = None


class Equation(StrictModel):
    id: str
    number: str | None = None
    latex: str | None = None
    raw_text: str | None = None
    description: str | None = None
    page: int
    section: str | None = None
    bbox: BBox
    source_method: SourceMethod = SourceMethod.text
    latex_valid: bool | None = None


class Figure(StrictModel):
    id: str
    number: str | None = None
    caption: str | None = None
    page: int
    bbox: BBox
    cache_path: str | None = None
    referenced_by: list[str] = []
    source_method: SourceMethod = SourceMethod.text


class DocumentWarning(StrictModel):
    code: str
    page: int | None = None
    message: str | None = None

    def __str__(self):
        detail = f"page {self.page}" if self.page is not None else (self.message or "")
        return f"{self.code}: {detail}" if detail else self.code


class DocumentSource(StrictModel):
    relative_path: str = Field(description="İlk ayrıştırıldığı göreli yol; aynı içerikli kopyalar önbelleği paylaşır")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_count: int = Field(ge=1)


class DocumentStats(StrictModel):
    pages: int = 0
    text_pages: int = 0
    mixed_pages: int = 0
    scanned_pages: int = 0
    ocr_pages: int = 0
    vision_calls: int = 0
    text_llm_calls: int = 0


class DocumentModel(StrictModel):
    schema_version: str = DOCUMENT_SCHEMA_VERSION
    parser_version: str
    parse_config_hash: str = Field(description="Ayrıştırma sonucunu etkileyen config alanlarının hash'i")
    source: DocumentSource
    pdf_metadata: dict[str, str] = {}
    title: str | None = None
    pages: list[Page] = []
    blocks: list[Block] = []
    sections: list[Section] = []
    tables: list[Table] = []
    equations: list[Equation] = []
    figures: list[Figure] = []
    warnings: list[DocumentWarning] = []
    stats: DocumentStats = DocumentStats()

    def blocks_on_page(self, number):
        return [block for block in self.blocks if block.page == number]

    def headings(self):
        return [block for block in self.blocks if block.type == BlockType.heading]
