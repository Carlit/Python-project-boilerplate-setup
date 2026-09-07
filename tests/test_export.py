"""Tests de src/export.py.

Aucun test ne dépend d'une base : uniquement des DataFrames construits en
mémoire et des fichiers écrits sous tmp_path.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src import export as export_module
from src.export import (
    ExportError,
    ExportFormat,
    export_batches,
    export_dataframe,
    resolve_output_path,
)


def _frame(rows: int = 3) -> pd.DataFrame:
    return pd.DataFrame(
        {"id": range(rows), "libelle": [f"item {i}" for i in range(rows)]}
    )


def test_resolve_output_path_adds_missing_extension() -> None:
    assert resolve_output_path(Path("export"), ExportFormat.CSV) == Path("export.csv")


def test_resolve_output_path_corrects_wrong_extension() -> None:
    result = resolve_output_path(Path("export.txt"), ExportFormat.EXCEL)
    assert result == Path("export.xlsx")


def test_resolve_output_path_keeps_matching_extension() -> None:
    path = Path("export.parquet")
    assert resolve_output_path(path, ExportFormat.PARQUET) == path


def test_export_dataframe_csv_round_trip(tmp_path: Path) -> None:
    frame = _frame()
    output = tmp_path / "sortie"

    written = export_dataframe(frame, output, ExportFormat.CSV)

    assert written == tmp_path / "sortie.csv"
    reread = pd.read_csv(written, sep=";", encoding="utf-8-sig")
    pd.testing.assert_frame_equal(reread, frame)


def test_export_dataframe_csv_has_bom(tmp_path: Path) -> None:
    output = export_dataframe(_frame(1), tmp_path / "sortie", ExportFormat.CSV)
    assert output.read_bytes().startswith(b"\xef\xbb\xbf")


def test_export_dataframe_creates_missing_parent_dirs(tmp_path: Path) -> None:
    output = tmp_path / "un" / "deux" / "trois" / "sortie.csv"
    written = export_dataframe(_frame(1), output, ExportFormat.CSV)
    assert written.is_file()


def test_export_dataframe_excel_round_trip(tmp_path: Path) -> None:
    frame = _frame()
    written = export_dataframe(frame, tmp_path / "sortie", ExportFormat.EXCEL)

    assert written == tmp_path / "sortie.xlsx"
    reread = pd.read_excel(written)
    pd.testing.assert_frame_equal(reread, frame)


def test_export_dataframe_excel_refuses_at_or_above_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(export_module, "EXCEL_MAX_ROWS", 3)
    with pytest.raises(ExportError, match="Excel"):
        export_dataframe(_frame(3), tmp_path / "sortie", ExportFormat.EXCEL)


def test_export_dataframe_excel_allows_below_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(export_module, "EXCEL_MAX_ROWS", 4)
    written = export_dataframe(_frame(3), tmp_path / "sortie", ExportFormat.EXCEL)
    assert written.is_file()


def test_export_batches_csv_writes_header_once(tmp_path: Path) -> None:
    batches = [_frame(2), _frame(2), _frame(1)]
    output, total_rows = export_batches(batches, tmp_path / "sortie", ExportFormat.CSV)

    assert total_rows == 5
    content = output.read_text(encoding="utf-8-sig")
    assert content.count("id;libelle") == 1


def test_export_batches_excel_concatenates(tmp_path: Path) -> None:
    batches = [_frame(2), _frame(3)]
    output, total_rows = export_batches(batches, tmp_path / "sortie", ExportFormat.EXCEL)

    assert total_rows == 5
    reread = pd.read_excel(output)
    assert len(reread) == 5


def test_export_batches_refuses_empty_iterable_csv(tmp_path: Path) -> None:
    with pytest.raises(ExportError, match="vide"):
        export_batches([], tmp_path / "sortie", ExportFormat.CSV)


def test_export_batches_refuses_empty_iterable_excel(tmp_path: Path) -> None:
    with pytest.raises(ExportError, match="vide"):
        export_batches([], tmp_path / "sortie", ExportFormat.EXCEL)
