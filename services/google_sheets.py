# services/google_sheets.py
import os
import asyncio
import gspread
from google.oauth2.service_account import Credentials
from typing import List, Dict, Any

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _blocking_sync_to_sheet(candidates: List[Dict[str, Any]]) -> int:
    """Synchronous function to interact with the Google Sheets API."""
    creds_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE", "credentials.json")
    sheet_id = os.getenv("GOOGLE_SHEET_ID")

    if not os.path.exists(creds_path):
        raise FileNotFoundError(f"Google credentials file not found at {creds_path}")
    if not sheet_id:
        raise ValueError("GOOGLE_SHEET_ID environment variable is not set")

    # Authorize and connect
    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(sheet_id).sheet1

    # Clear existing data
    sheet.clear()

    # Prepare data payload
    headers = ["Name", "Phone", "Role", "Base Score", "AI Score", "Total Score", "Status"]
    rows = [headers]

    for candidate in candidates:
        rows.append([
            candidate.get("full_name", "Noma'lum"),
            candidate.get("phone_number", "-"),
            candidate.get("vacancy_title", "-"),
            candidate.get("base_score", 0),
            candidate.get("ai_score", 0),
            candidate.get("total_score", 0),
            candidate.get("status", "Noma'lum")
        ])

    # Batch update to minimize API calls and avoid rate limits
    sheet.update(range_name="A1", values=rows)

    # Return number of synced candidate rows (excluding header)
    return len(rows) - 1


async def sync_candidates_to_sheet(candidates: List[Dict[str, Any]]) -> int:
    """
    Asynchronous wrapper for gspread synchronization.
    Pushes candidate data to Google Sheets without blocking the FastAPI event loop.
    """
    return await asyncio.to_thread(_blocking_sync_to_sheet, candidates)