"""Re-authorize Google OAuth with all scopes needed by CMO Agent.

Opens a browser window for you to sign in and authorize. Once complete,
the token at data/google-token.json is updated with spreadsheets, drive,
documents, and presentations scopes.

Run:  python scripts/reauth_google_drive.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/presentations",
]

OAUTH_CREDS = Path(__file__).resolve().parent.parent / "data" / "saverwell-oauth-credentials.json"
TOKEN_PATH = Path(__file__).resolve().parent.parent / "data" / "google-token.json"


def main() -> None:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Installing google-auth-oauthlib...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "google-auth-oauthlib"])
        from google_auth_oauthlib.flow import InstalledAppFlow

    print(f"OAuth credentials: {OAUTH_CREDS}")
    print(f"Token path: {TOKEN_PATH}")
    print(f"Scopes: {SCOPES}")
    print()
    print("Opening browser for Google sign-in...")
    print("Sign in with the Google account used for CMO Agent.")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(str(OAUTH_CREDS), SCOPES)
    creds = flow.run_local_server(port=0)

    # Save token
    TOKEN_PATH.write_text(creds.to_json())
    print(f"\nToken saved to {TOKEN_PATH}")

    # Verify scopes
    token_data = json.loads(TOKEN_PATH.read_text())
    print(f"Scopes: {token_data.get('scopes', [])}")
    print("\nDone! OAuth token now covers: Sheets, Drive, Docs, and Slides.")


if __name__ == "__main__":
    main()
