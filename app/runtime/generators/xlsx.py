import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.utils.cell import coordinate_to_tuple
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.errors import AppError

MAX_SPEC_BYTES = 1024 * 1024


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FormulaSpec(_Strict):
    cell: str
    formula: str


class SheetSpec(_Strict):
    name: str
    columns: list[str]
    rows: list[list[object]] = Field(default_factory=list)
    formulas: list[FormulaSpec] = Field(default_factory=list)


class XlsxSpec(_Strict):
    sheets: list[SheetSpec] = Field(min_length=1, max_length=100)


def generate(path: Path, value: dict) -> None:
    try:
        if len(json.dumps(value, sort_keys=True).encode()) > MAX_SPEC_BYTES:
            raise ValueError("spec exceeds 1 MiB")
        spec = XlsxSpec.model_validate(value)
    except (ValidationError, TypeError, ValueError) as exc:
        raise AppError("VALIDATION_ERROR", 422, "Invalid XLSX specification") from exc
    names: set[str] = set()
    for sheet_spec in spec.sheets:
        if (
            not sheet_spec.name
            or len(sheet_spec.name) > 31
            or any(char in sheet_spec.name for char in "[]:*?/\\")
            or sheet_spec.name in names
        ):
            raise AppError("VALIDATION_ERROR", 422, "Invalid sheet name")
        names.add(sheet_spec.name)
        if any(len(row) != len(sheet_spec.columns) for row in sheet_spec.rows):
            raise AppError("VALIDATION_ERROR", 422, "Row length does not match columns")
        for formula in sheet_spec.formulas:
            if (
                not formula.formula.startswith("=")
                or len(formula.formula) > 200
                or "[" in formula.formula
                or "http" in formula.formula.lower()
            ):
                raise AppError("VALIDATION_ERROR", 422, "Invalid formula")
            try:
                coordinate_to_tuple(formula.cell)
            except (TypeError, ValueError) as exc:
                raise AppError("VALIDATION_ERROR", 422, "Invalid formula cell") from exc
    book = Workbook()
    book.remove(book.active)
    for sheet_spec in spec.sheets:
        sheet = book.create_sheet(sheet_spec.name)
        sheet.append(sheet_spec.columns)
        for row in sheet_spec.rows:
            sheet.append(row)
        for formula in sheet_spec.formulas:
            sheet[formula.cell] = formula.formula
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)
