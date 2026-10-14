"""Built-in office suite re-exports."""

from ossys.office.documents import (
    OfficeError,
    SheetSummary,
    append_note,
    append_sheet_row,
    build_deck,
    read_docx,
    read_sheet,
    read_text,
    summarize_sheet,
    write_sheet,
    write_text,
)

__all__ = [
    "OfficeError",
    "SheetSummary",
    "append_note",
    "append_sheet_row",
    "build_deck",
    "read_docx",
    "read_sheet",
    "read_text",
    "summarize_sheet",
    "write_sheet",
    "write_text",
]
