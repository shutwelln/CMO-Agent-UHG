"""Google Sheets dashboard for the Product Ideas pipeline."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()

# Score conversion: 1-10 numeric -> label
_SCORE_LABELS = {
    range(1, 4): "Low",
    range(4, 7): "Medium",
    range(7, 9): "High",
    range(9, 11): "Very High",
}

# Category mapping: growth ideas agent category -> sheet category
_CATEGORY_MAP: Dict[str, str] = {
    "content_amplification": "SEO/Content",
    "new_channel": "Distribution",
    "optimization": "Tools",
    "partnership": "Distribution",
    "conversion": "Revenue",
    "retention": "Email/Retention",
}


def _score_to_label(score: Any) -> str:
    """Convert a numeric 1-10 score to a human label."""
    try:
        val = int(score)
    except (TypeError, ValueError):
        return str(score)
    for rng, label in _SCORE_LABELS.items():
        if val in rng:
            return label
    return str(score)


def _map_category(category: str) -> str:
    """Map a growth ideas agent category to a sheet-friendly label."""
    return _CATEGORY_MAP.get(category, category.replace("_", " ").title() if category else "")


class ProductIdeasDashboard:
    """Google Sheet integration for the Product Ideas spreadsheet.

    Lazy credential init, dedup-on-append, graceful degradation.
    """

    TAB_IDEAS = "Product Ideas"
    TAB_ARCHIVE = "Archive"
    TAB_DROPDOWNS = "Dropdowns"

    def __init__(
        self,
        google_credentials_path: str = "",
        google_oauth_token_path: str = "",
        spreadsheet_id: str = "",
    ) -> None:
        self._google_credentials_path = google_credentials_path
        self._google_oauth_token_path = google_oauth_token_path
        self._spreadsheet_id = spreadsheet_id
        self._sheets_service: Any = None

    def _get_google_service(self) -> bool:
        """Lazily initialize Google Sheets API service."""
        if self._sheets_service is not None:
            return True

        try:
            from googleapiclient.discovery import build

            from ..google_auth import get_google_credentials

            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
            ]
            # Force OAuth — this sheet is owned by a personal account,
            # not accessible to the service account.
            credentials = get_google_credentials(
                oauth_token_path=self._google_oauth_token_path,
                service_account_path="",
                scopes=scopes,
            )
            if credentials is None:
                logger.warning("product_ideas_dashboard_no_credentials")
                return False

            self._sheets_service = build("sheets", "v4", credentials=credentials)
            return True
        except Exception as e:
            logger.warning("product_ideas_dashboard_init_failed", error=str(e))
            return False

    async def _get_existing_idea_titles(self) -> set:
        """Read column A (Idea titles) from both Product Ideas and Archive tabs.

        Returns a set of lowercased titles for dedup.
        """
        if not self._get_google_service() or not self._spreadsheet_id:
            return set()

        titles: set = set()
        for tab in (self.TAB_IDEAS, self.TAB_ARCHIVE):
            try:
                result = (
                    self._sheets_service.spreadsheets()
                    .values()
                    .get(
                        spreadsheetId=self._spreadsheet_id,
                        range=f"'{tab}'!A2:A5000",
                    )
                    .execute()
                )
                rows = result.get("values", [])
                titles.update(row[0].strip().lower() for row in rows if row and row[0].strip())
            except Exception:
                # Tab may not exist yet (Archive not created) - skip
                continue

        return titles

    async def append_ideas(
        self,
        ideas: List[Dict[str, Any]],
        source_label: str = "",
    ) -> int:
        """Dedup against sheet and append new ideas in 9-column format (A-I).

        Returns the number of rows appended.
        """
        if not self._get_google_service() or not self._spreadsheet_id:
            return 0

        existing = await self._get_existing_idea_titles()
        today = date.today().strftime("%Y-%m-%d")

        rows: List[List[str]] = []
        for idea in ideas:
            title = idea.get("title", "").strip()
            if not title:
                continue
            if title.lower() in existing:
                continue

            rows.append(
                [
                    title,  # A: Idea
                    idea.get("description", ""),  # B: Description
                    "Not Started",  # C: Status
                    _map_category(idea.get("category", "")),  # D: Category
                    _score_to_label(idea.get("impact_score", "")),  # E: Impact
                    _score_to_label(idea.get("effort_score", "")),  # F: Effort
                    "",  # G: Moat (blank - growth ideas have no moat field)
                    source_label,  # H: Source
                    idea.get("date_created", today),  # I: Date Created
                ]
            )

        if not rows:
            logger.info("product_ideas_no_new_rows", existing_count=len(existing))
            return 0

        try:
            self._sheets_service.spreadsheets().values().append(
                spreadsheetId=self._spreadsheet_id,
                range=f"'{self.TAB_IDEAS}'!A2",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": rows},
            ).execute()
            logger.info("product_ideas_appended", count=len(rows), source=source_label)
            return len(rows)
        except Exception as e:
            logger.error("product_ideas_append_failed", error=str(e))
            return 0

    async def find_idea_row(self, idea_title: str) -> Optional[int]:
        """Find the 1-based row number of an idea by case-insensitive title match.

        Returns None if not found.
        """
        if not self._get_google_service() or not self._spreadsheet_id:
            return None

        try:
            result = (
                self._sheets_service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=self._spreadsheet_id,
                    range=f"'{self.TAB_IDEAS}'!A2:A5000",
                )
                .execute()
            )
            rows = result.get("values", [])
            target = idea_title.strip().lower()
            for i, row in enumerate(rows):
                if row and row[0].strip().lower() == target:
                    return i + 2  # +2: 1-indexed + skip header
            return None
        except Exception as e:
            logger.warning("product_ideas_find_row_failed", error=str(e))
            return None

    async def update_idea_status(self, idea_title: str, new_status: str) -> bool:
        """Update column C (Status) for the given idea.

        If new_status is "Skipped": reads the full row, appends it to the Archive
        tab, then deletes it from Product Ideas.

        Returns True on success, False on failure.
        """
        if not self._get_google_service() or not self._spreadsheet_id:
            return False

        row_num = await self.find_idea_row(idea_title)
        if row_num is None:
            logger.info("product_ideas_row_not_found", title=idea_title)
            return False

        if new_status == "Skipped":
            return await self._archive_row(row_num)

        # Simple status update (e.g. "In Progress")
        try:
            self._sheets_service.spreadsheets().values().update(
                spreadsheetId=self._spreadsheet_id,
                range=f"'{self.TAB_IDEAS}'!C{row_num}",
                valueInputOption="RAW",
                body={"values": [[new_status]]},
            ).execute()
            logger.info(
                "product_ideas_status_updated",
                title=idea_title,
                status=new_status,
                row=row_num,
            )
            return True
        except Exception as e:
            logger.error("product_ideas_status_update_failed", error=str(e))
            return False

    async def _archive_row(self, row_num: int) -> bool:
        """Read full row, append to Archive tab, delete from Product Ideas."""
        try:
            # Read the full row (A-I, 9 columns)
            result = (
                self._sheets_service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=self._spreadsheet_id,
                    range=f"'{self.TAB_IDEAS}'!A{row_num}:I{row_num}",
                )
                .execute()
            )
            row_data = result.get("values", [])
            if not row_data:
                return False

            # Update status to "Skipped" in the row data before archiving
            row = row_data[0]
            while len(row) < 9:
                row.append("")
            row[2] = "Skipped"  # Column C = Status

            # Append to Archive tab
            self._sheets_service.spreadsheets().values().append(
                spreadsheetId=self._spreadsheet_id,
                range=f"'{self.TAB_ARCHIVE}'!A2",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": [row]},
            ).execute()

            # Delete from Product Ideas
            tabs = (
                self._sheets_service.spreadsheets()
                .get(
                    spreadsheetId=self._spreadsheet_id,
                    fields="sheets.properties",
                )
                .execute()
            )

            sheet_id = None
            for sheet in tabs.get("sheets", []):
                if sheet["properties"]["title"] == self.TAB_IDEAS:
                    sheet_id = sheet["properties"]["sheetId"]
                    break

            if sheet_id is not None:
                self._sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=self._spreadsheet_id,
                    body={
                        "requests": [
                            {
                                "deleteDimension": {
                                    "range": {
                                        "sheetId": sheet_id,
                                        "dimension": "ROWS",
                                        "startIndex": row_num - 1,  # 0-based
                                        "endIndex": row_num,
                                    }
                                }
                            }
                        ]
                    },
                ).execute()

            logger.info("product_ideas_archived", row=row_num, title=row[0])
            return True
        except Exception as e:
            logger.error("product_ideas_archive_failed", error=str(e), row=row_num)
            return False

    async def setup_sheet(self) -> Dict[str, Any]:
        """One-time sheet setup: Source + Date Created headers, Original labels,
        Dropdowns tab with ONE_OF_RANGE validations, and Archive tab.
        """
        if not self._get_google_service() or not self._spreadsheet_id:
            return {"status": "not_configured"}

        try:
            # Get existing tabs
            meta = (
                self._sheets_service.spreadsheets()
                .get(
                    spreadsheetId=self._spreadsheet_id,
                    fields="sheets.properties",
                )
                .execute()
            )

            tab_names = [s["properties"]["title"] for s in meta.get("sheets", [])]
            ideas_sheet_id = None
            for s in meta.get("sheets", []):
                if s["properties"]["title"] == self.TAB_IDEAS:
                    ideas_sheet_id = s["properties"]["sheetId"]

            results: List[str] = []

            # 1. Write "Source" and "Date Created" headers in H1:I1
            self._sheets_service.spreadsheets().values().update(
                spreadsheetId=self._spreadsheet_id,
                range=f"'{self.TAB_IDEAS}'!H1:I1",
                valueInputOption="RAW",
                body={"values": [["Source", "Date Created"]]},
            ).execute()
            results.append("Source + Date Created headers written to H1:I1")

            # 2. Write "Original" in H2:H31 for existing 30 ideas
            original_values = [["Original"]] * 30
            self._sheets_service.spreadsheets().values().update(
                spreadsheetId=self._spreadsheet_id,
                range=f"'{self.TAB_IDEAS}'!H2:H31",
                valueInputOption="RAW",
                body={"values": original_values},
            ).execute()
            results.append("Original written in H2:H31")

            # 3. Format H1:I1 with navy header to match existing style
            if ideas_sheet_id is not None:
                self._sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=self._spreadsheet_id,
                    body={
                        "requests": [
                            {
                                "repeatCell": {
                                    "range": {
                                        "sheetId": ideas_sheet_id,
                                        "startRowIndex": 0,
                                        "endRowIndex": 1,
                                        "startColumnIndex": 7,  # H
                                        "endColumnIndex": 9,  # I
                                    },
                                    "cell": {
                                        "userEnteredFormat": {
                                            "backgroundColor": {
                                                "red": 0.0,
                                                "green": 0.0,
                                                "blue": 0.5,
                                            },
                                            "textFormat": {
                                                "foregroundColor": {
                                                    "red": 1.0,
                                                    "green": 1.0,
                                                    "blue": 1.0,
                                                },
                                                "bold": True,
                                            },
                                        }
                                    },
                                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                                }
                            }
                        ]
                    },
                ).execute()
                results.append("H1:I1 formatted with navy header")

            # 4. Create Dropdowns tab if it doesn't exist
            dropdowns_sheet_id = None
            if self.TAB_DROPDOWNS not in tab_names:
                self._sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=self._spreadsheet_id,
                    body={
                        "requests": [{"addSheet": {"properties": {"title": self.TAB_DROPDOWNS}}}]
                    },
                ).execute()

                # Fetch new sheet ID
                meta_dd = (
                    self._sheets_service.spreadsheets()
                    .get(spreadsheetId=self._spreadsheet_id, fields="sheets.properties")
                    .execute()
                )
                for s in meta_dd.get("sheets", []):
                    if s["properties"]["title"] == self.TAB_DROPDOWNS:
                        dropdowns_sheet_id = s["properties"]["sheetId"]

                # Seed dropdown values (headers + values)
                dropdown_data = [
                    ["Status", "Category", "Traffic Impact", "Build Effort", "Competitive Moat"],
                    ["Not Started", "SEO/Content", "Low", "Low", "Low"],
                    ["In Progress", "Distribution", "Medium", "Medium", "Medium"],
                    ["Done", "Tools", "High", "High", "High"],
                    ["Skipped", "Revenue", "Very High", "Very High", "Very High"],
                    ["", "Email/Retention", "", "", ""],
                ]
                self._sheets_service.spreadsheets().values().update(
                    spreadsheetId=self._spreadsheet_id,
                    range=f"'{self.TAB_DROPDOWNS}'!A1",
                    valueInputOption="RAW",
                    body={"values": dropdown_data},
                ).execute()

                # Format header row
                if dropdowns_sheet_id is not None:
                    self._sheets_service.spreadsheets().batchUpdate(
                        spreadsheetId=self._spreadsheet_id,
                        body={
                            "requests": [
                                {
                                    "repeatCell": {
                                        "range": {
                                            "sheetId": dropdowns_sheet_id,
                                            "startRowIndex": 0,
                                            "endRowIndex": 1,
                                            "startColumnIndex": 0,
                                            "endColumnIndex": 5,
                                        },
                                        "cell": {
                                            "userEnteredFormat": {
                                                "backgroundColor": {
                                                    "red": 0.0,
                                                    "green": 0.0,
                                                    "blue": 0.5,
                                                },
                                                "textFormat": {
                                                    "foregroundColor": {
                                                        "red": 1.0,
                                                        "green": 1.0,
                                                        "blue": 1.0,
                                                    },
                                                    "bold": True,
                                                },
                                            }
                                        },
                                        "fields": "userEnteredFormat(backgroundColor,textFormat)",
                                    }
                                }
                            ]
                        },
                    ).execute()

                results.append("Dropdowns tab created with values")
            else:
                # Get existing Dropdowns sheet ID for validations
                for s in meta.get("sheets", []):
                    if s["properties"]["title"] == self.TAB_DROPDOWNS:
                        dropdowns_sheet_id = s["properties"]["sheetId"]
                results.append("Dropdowns tab already exists")

            # 5. Apply ONE_OF_RANGE validations from Dropdowns tab
            # Column mapping: C=Status(A), D=Category(B), E=Impact(C), F=Effort(D), G=Moat(E)
            if ideas_sheet_id is not None and dropdowns_sheet_id is not None:
                dd_col_map = [
                    (2, 0),  # C (Status) <- Dropdowns col A
                    (3, 1),  # D (Category) <- Dropdowns col B
                    (4, 2),  # E (Traffic Impact) <- Dropdowns col C
                    (5, 3),  # F (Build Effort) <- Dropdowns col D
                    (6, 4),  # G (Competitive Moat) <- Dropdowns col E
                ]
                validation_requests = []
                for target_col, dd_col in dd_col_map:
                    validation_requests.append(
                        {
                            "setDataValidation": {
                                "range": {
                                    "sheetId": ideas_sheet_id,
                                    "startRowIndex": 1,
                                    "endRowIndex": 5000,
                                    "startColumnIndex": target_col,
                                    "endColumnIndex": target_col + 1,
                                },
                                "rule": {
                                    "condition": {
                                        "type": "ONE_OF_RANGE",
                                        "values": [
                                            {
                                                "userEnteredValue": (
                                                    f"='{self.TAB_DROPDOWNS}'!"
                                                    f"{chr(65 + dd_col)}2:"
                                                    f"{chr(65 + dd_col)}100"
                                                )
                                            }
                                        ],
                                    },
                                    "showCustomUi": True,
                                    "strict": False,
                                },
                            }
                        }
                    )
                self._sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=self._spreadsheet_id,
                    body={"requests": validation_requests},
                ).execute()
                results.append("ONE_OF_RANGE validations applied to Product Ideas")

            # 6. Create Archive tab if it doesn't exist
            if self.TAB_ARCHIVE not in tab_names:
                self._sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=self._spreadsheet_id,
                    body={"requests": [{"addSheet": {"properties": {"title": self.TAB_ARCHIVE}}}]},
                ).execute()

                # Get the Archive tab sheet ID for formatting
                meta2 = (
                    self._sheets_service.spreadsheets()
                    .get(
                        spreadsheetId=self._spreadsheet_id,
                        fields="sheets.properties",
                    )
                    .execute()
                )
                archive_sheet_id = None
                for s in meta2.get("sheets", []):
                    if s["properties"]["title"] == self.TAB_ARCHIVE:
                        archive_sheet_id = s["properties"]["sheetId"]

                # Write headers (9-column structure including Date Created)
                headers = [
                    "Idea",
                    "Description",
                    "Status",
                    "Category",
                    "Impact",
                    "Effort",
                    "Moat",
                    "Source",
                    "Date Created",
                ]
                self._sheets_service.spreadsheets().values().update(
                    spreadsheetId=self._spreadsheet_id,
                    range=f"'{self.TAB_ARCHIVE}'!A1",
                    valueInputOption="RAW",
                    body={"values": [headers]},
                ).execute()

                fmt_requests = []
                # Format Archive header row
                if archive_sheet_id is not None:
                    fmt_requests.append(
                        {
                            "repeatCell": {
                                "range": {
                                    "sheetId": archive_sheet_id,
                                    "startRowIndex": 0,
                                    "endRowIndex": 1,
                                    "startColumnIndex": 0,
                                    "endColumnIndex": 9,
                                },
                                "cell": {
                                    "userEnteredFormat": {
                                        "backgroundColor": {
                                            "red": 0.0,
                                            "green": 0.0,
                                            "blue": 0.5,
                                        },
                                        "textFormat": {
                                            "foregroundColor": {
                                                "red": 1.0,
                                                "green": 1.0,
                                                "blue": 1.0,
                                            },
                                            "bold": True,
                                        },
                                    }
                                },
                                "fields": "userEnteredFormat(backgroundColor,textFormat)",
                            }
                        }
                    )

                # Apply same ONE_OF_RANGE validations to Archive tab
                if archive_sheet_id is not None and dropdowns_sheet_id is not None:
                    for target_col, dd_col in dd_col_map:
                        fmt_requests.append(
                            {
                                "setDataValidation": {
                                    "range": {
                                        "sheetId": archive_sheet_id,
                                        "startRowIndex": 1,
                                        "endRowIndex": 5000,
                                        "startColumnIndex": target_col,
                                        "endColumnIndex": target_col + 1,
                                    },
                                    "rule": {
                                        "condition": {
                                            "type": "ONE_OF_RANGE",
                                            "values": [
                                                {
                                                    "userEnteredValue": (
                                                        f"='{self.TAB_DROPDOWNS}'!"
                                                        f"{chr(65 + dd_col)}2:"
                                                        f"{chr(65 + dd_col)}100"
                                                    )
                                                }
                                            ],
                                        },
                                        "showCustomUi": True,
                                        "strict": False,
                                    },
                                }
                            }
                        )

                if fmt_requests:
                    self._sheets_service.spreadsheets().batchUpdate(
                        spreadsheetId=self._spreadsheet_id,
                        body={"requests": fmt_requests},
                    ).execute()

                results.append("Archive tab created with headers, formatting, and validations")
            else:
                results.append("Archive tab already exists")

            logger.info("product_ideas_setup_complete", results=results)
            return {"status": "ok", "results": results}
        except Exception as e:
            logger.error("product_ideas_setup_failed", error=str(e))
            return {"status": "error", "message": str(e)}
