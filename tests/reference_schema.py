"""Elle hazırlanan referans verinin şeması (§38.1). Faz 14 doğruluk ölçümü bu dosyaları okur."""
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
REFERENCE_DIR = FIXTURES_DIR / "reference"

# §38.1: gerçek makale referanslarında bulunması gereken en az kayıt sayıları
REAL_MINIMUMS = {"tables": 2, "equations": 3, "results": 5}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BibliographicRef(StrictModel):
    title: str = Field(min_length=1)
    authors: list[str] = Field(min_length=1)
    year: int | None = Field(None, ge=1900, le=2100)
    venue: str | None = None
    doi: str | None = Field(None, pattern=r"^10\.\d{4,9}/\S+$")


class TableRef(StrictModel):
    number: str
    page: int = Field(ge=1)
    caption: str | None = None
    header: list[str] = Field(min_length=1)
    rows: list[list[str]] = Field(min_length=1)

    @model_validator(mode="after")
    def rows_match_header(self):
        for i, row in enumerate(self.rows, start=1):
            if len(row) != len(self.header):
                raise ValueError(f"Tablo {self.number}, satır {i}: {len(row)} hücre var, başlıkta {len(self.header)}")
        return self


class EquationRef(StrictModel):
    number: str | None = None
    page: int = Field(ge=1)
    latex: str = Field(min_length=1)
    description: str | None = None


class ResultRef(StrictModel):
    model: str
    metric: str
    value: float
    page: int = Field(ge=1)
    table: str | None = None
    dataset: str | None = None


class ReferenceData(StrictModel):
    source: str = Field(description="tests/fixtures klasörüne göre PDF yolu")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    kind: Literal["real", "synthetic"]
    bibliographic: BibliographicRef
    tables: list[TableRef] = []
    equations: list[EquationRef] = []
    results: list[ResultRef] = []

    @model_validator(mode="after")
    def real_minimums(self):
        if self.kind == "real":
            for field, minimum in REAL_MINIMUMS.items():
                count = len(getattr(self, field))
                if count < minimum:
                    raise ValueError(f"Gerçek makale referansında en az {minimum} {field} olmalı, {count} var")
        return self

    @property
    def source_path(self):
        return FIXTURES_DIR / self.source


def load_reference(path):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return ReferenceData.model_validate(data)


def reference_files():
    return sorted(REFERENCE_DIR.glob("*.yaml"))
