# Plan: Add Native Spreadsheet Reading Tools to Agents

## Goal
Give Research Agent and Sheets Agent the ability to read XLSX and CSV files directly, eliminating the need to manually convert spreadsheets to `.txt` files.

## Approach
Create a shared utility module and register tools on both agents.

---

## Step 1: Create `src/cmo_agent/files/spreadsheet.py` — shared utility

A single reusable function that both agents will call:

```python
async def read_spreadsheet(
    file_path: str,
    sheet_name: Optional[str] = None,  # XLSX only; defaults to first sheet
    max_rows: int = 500,
) -> Dict[str, Any]
```

**Returns:** `{"file": ..., "sheet": ..., "headers": [...], "rows": [[...]], "row_count": N, "truncated": bool}`

- Uses `openpyxl` for `.xlsx`/`.xls`, built-in `csv` for `.csv`
- Returns structured data (list of lists) — better for agents than pipe-delimited text
- Caps at `max_rows` (default 500) to stay within LLM context limits
- Also provides a `list_sheets(file_path)` helper for XLSX files with multiple sheets

Also add:

```python
def list_data_files(directory: str, extensions: tuple = (".xlsx", ".csv")) -> List[Dict[str, str]]
```

Returns `[{"name": ..., "path": ..., "size": ..., "modified": ...}]` for discovery.

**Reuse pattern from:** `workspace/manager.py:_extract_file_text()` and `files/processor.py:extract_text_from_spreadsheet()` — same openpyxl approach but returning structured data instead of pipe-delimited text.

---

## Step 2: Add `openpyxl` to `pyproject.toml` dependencies

It's already used dynamically in `workspace/manager.py` and `files/processor.py` but not declared. Add it as a proper dependency.

---

## Step 3: Register tools on Research Agent (`agents/research.py`)

Add two tools:

1. **`read_spreadsheet`** — Read data from an XLSX or CSV file. Parameters: `file_path` (str), `sheet_name` (str, optional), `max_rows` (int, optional, default 500).
2. **`list_data_files`** — List available spreadsheet files in the data directory. Parameters: `directory` (str, optional, defaults to `data/`).

---

## Step 4: Register tools on Sheets Agent (`agents/sheets.py`)

Same two tools registered on the Sheets Agent so it can read existing spreadsheets when creating new ones or analyzing data.

---

## Step 5: Update orchestrator system prompt (`agents/orchestrator.py`)

Update the research_agent and sheets_agent descriptions to mention spreadsheet reading capability so the LLM knows to route spreadsheet-related requests correctly.

---

## Step 6: Format, lint, test

- `ruff format src/`
- `ruff check src/`
- `pytest` (existing tests)

---

## Files Changed
| File | Change |
|------|--------|
| `src/cmo_agent/files/spreadsheet.py` | **New** — shared `read_spreadsheet()` and `list_data_files()` |
| `pyproject.toml` | Add `openpyxl` to dependencies |
| `src/cmo_agent/agents/research.py` | Register `read_spreadsheet` + `list_data_files` tools |
| `src/cmo_agent/agents/sheets.py` | Register `read_spreadsheet` + `list_data_files` tools |
| `src/cmo_agent/agents/orchestrator.py` | Update system prompt descriptions |
