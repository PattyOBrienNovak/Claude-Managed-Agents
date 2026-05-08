#!/usr/bin/env python3
"""One-time script to authorize Gmail OAuth and save gmail_token.json.

Run this once locally before using run_digest.py:
    python setup_gmail_auth.py

Requires credentials.json from Google Cloud Console (OAuth 2.0 client ID).
"""

import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

TOKEN_FILE = "gmail_token.json"
CREDENTIALS_FILE = "credentials.json"


def main():
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"ERROR: {CREDENTIALS_FILE} not found.")
        print("Download it from Google Cloud Console > APIs & Services > Credentials.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    print(f"Authorization complete. Token saved to {TOKEN_FILE}")


if __name__ == "__main__":
    main()
