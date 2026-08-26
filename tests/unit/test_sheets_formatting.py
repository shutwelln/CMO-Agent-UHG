"""Tests for Google Sheets formatting in sheets.py."""

from __future__ import annotations

from cmo_agent.agents.sheets import SheetsAgent


def _make_spreadsheet(sheet_ids: list) -> dict:
    """Build a minimal spreadsheet response dict for testing."""
    return {"sheets": [{"properties": {"sheetId": sid}} for sid in sheet_ids]}


class TestBuildFormatRequests:
    def test_bold_header_and_freeze(self):
        spreadsheet = _make_spreadsheet([0])
        sheets_data = [{"name": "S1", "headers": ["A", "B", "C"], "rows": [["1", "2", "3"]]}]
        reqs = SheetsAgent._build_format_requests(spreadsheet, sheets_data)
        types = [list(r.keys())[0] for r in reqs]
        assert "repeatCell" in types, "Expected bold header repeatCell request"
        assert "updateSheetProperties" in types, "Expected freeze row request"

    def test_borders_present(self):
        spreadsheet = _make_spreadsheet([0])
        sheets_data = [{"name": "S1", "headers": ["A", "B"], "rows": [["x", "y"]]}]
        reqs = SheetsAgent._build_format_requests(spreadsheet, sheets_data)
        border_reqs = [r for r in reqs if "updateBorders" in r]
        assert len(border_reqs) == 1, "Expected one updateBorders request"
        border = border_reqs[0]["updateBorders"]
        assert "innerHorizontal" in border
        assert "innerVertical" in border

    def test_banding_present(self):
        spreadsheet = _make_spreadsheet([0])
        sheets_data = [{"name": "S1", "headers": ["A", "B"], "rows": [["x", "y"], ["a", "b"]]}]
        reqs = SheetsAgent._build_format_requests(spreadsheet, sheets_data)
        banding_reqs = [r for r in reqs if "addBanding" in r]
        assert len(banding_reqs) == 1, "Expected one addBanding request"
        band = banding_reqs[0]["addBanding"]["bandedRange"]["rowProperties"]
        assert "firstBandColor" in band
        assert "secondBandColor" in band

    def test_number_format_currency(self):
        spreadsheet = _make_spreadsheet([0])
        sheets_data = [
            {
                "name": "S1",
                "headers": ["Name", "Amount"],
                "column_types": ["text", "currency"],
                "rows": [["Item", 100.00]],
            }
        ]
        reqs = SheetsAgent._build_format_requests(spreadsheet, sheets_data)
        fmt_reqs = [
            r
            for r in reqs
            if "repeatCell" in r
            and r["repeatCell"].get("cell", {}).get("userEnteredFormat", {}).get("numberFormat")
            is not None
        ]
        assert len(fmt_reqs) == 1
        pattern = fmt_reqs[0]["repeatCell"]["cell"]["userEnteredFormat"]["numberFormat"]["pattern"]
        assert "$" in pattern

    def test_number_format_percentage(self):
        spreadsheet = _make_spreadsheet([0])
        sheets_data = [
            {
                "name": "S1",
                "headers": ["Name", "Rate"],
                "column_types": ["text", "percentage"],
                "rows": [["Item", 0.25]],
            }
        ]
        reqs = SheetsAgent._build_format_requests(spreadsheet, sheets_data)
        fmt_reqs = [
            r
            for r in reqs
            if "repeatCell" in r
            and r["repeatCell"].get("cell", {}).get("userEnteredFormat", {}).get("numberFormat")
            is not None
        ]
        assert len(fmt_reqs) == 1
        pattern = fmt_reqs[0]["repeatCell"]["cell"]["userEnteredFormat"]["numberFormat"]["pattern"]
        assert "%" in pattern

    def test_auto_resize_when_no_widths(self):
        spreadsheet = _make_spreadsheet([0])
        sheets_data = [{"name": "S1", "headers": ["A", "B", "C"], "rows": []}]
        reqs = SheetsAgent._build_format_requests(spreadsheet, sheets_data)
        auto_reqs = [r for r in reqs if "autoResizeDimensions" in r]
        assert len(auto_reqs) == 1

    def test_no_auto_resize_when_widths_provided(self):
        spreadsheet = _make_spreadsheet([0])
        sheets_data = [
            {
                "name": "S1",
                "headers": ["A", "B"],
                "column_widths": [100, 150],
                "rows": [],
            }
        ]
        reqs = SheetsAgent._build_format_requests(spreadsheet, sheets_data)
        auto_reqs = [r for r in reqs if "autoResizeDimensions" in r]
        assert len(auto_reqs) == 0

    def test_alignment_for_text_and_numbers(self):
        spreadsheet = _make_spreadsheet([0])
        sheets_data = [
            {
                "name": "S1",
                "headers": ["Name", "Count", "Date"],
                "column_types": ["text", "integer", "date"],
                "rows": [["A", 10, "2024-01-01"]],
            }
        ]
        reqs = SheetsAgent._build_format_requests(spreadsheet, sheets_data)
        # Find repeatCell requests with alignment
        align_reqs = [
            r
            for r in reqs
            if "repeatCell" in r
            and "horizontalAlignment"
            in r["repeatCell"].get("cell", {}).get("userEnteredFormat", {})
            # Exclude the header bold request which also has alignment
            and r["repeatCell"]["range"].get("startRowIndex", 0) > 0
        ]
        assert len(align_reqs) == 3  # text, integer, date
        alignments = [
            r["repeatCell"]["cell"]["userEnteredFormat"]["horizontalAlignment"] for r in align_reqs
        ]
        assert "LEFT" in alignments  # text
        assert "RIGHT" in alignments  # integer
        assert "CENTER" in alignments  # date
