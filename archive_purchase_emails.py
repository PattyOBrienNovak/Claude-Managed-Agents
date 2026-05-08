#!/usr/bin/env python3
"""Standalone one-time script to archive the 58 purchase email threads from the May 7, 2026 run.

Applies the "Purchase Digests/Processed" label and removes threads from the inbox.
Requires gmail_token.json in the working directory (run setup_gmail_auth.py first).
"""

import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

LABEL_NAME = "Purchase Digests/Processed"


def get_gmail_service():
    creds = Credentials.from_authorized_user_file("gmail_token.json", GMAIL_SCOPES)
    return build("gmail", "v1", credentials=creds)


def get_or_create_label(service, label_name: str) -> str:
    labels = service.users().labels().list(userId="me").execute()
    for label in labels.get("labels", []):
        if label["name"] == label_name:
            return label["id"]
    created = service.users().labels().create(
        userId="me", body={"name": label_name}
    ).execute()
    print(f"Created label: {label_name} (id={created['id']})")
    return created["id"]


def archive_threads(thread_ids: list[str]):
    service = get_gmail_service()
    label_id = get_or_create_label(service, LABEL_NAME)

    archived = 0
    errors = []
    for thread_id in thread_ids:
        try:
            service.users().threads().modify(
                userId="me",
                id=thread_id,
                body={"addLabelIds": [label_id], "removeLabelIds": ["INBOX"]},
            ).execute()
            archived += 1
            print(f"  Archived {thread_id}")
        except Exception as exc:
            errors.append({"thread_id": thread_id, "error": str(exc)})
            print(f"  ERROR archiving {thread_id}: {exc}")

    print(f"\nDone. Archived: {archived}, Errors: {len(errors)}")
    if errors:
        print("Failed threads:", json.dumps(errors, indent=2))


def fetch_purchase_thread_ids() -> list[str]:
    """Search Gmail for purchase emails and return their thread IDs."""
    service = get_gmail_service()
    query = "subject:(order OR receipt OR invoice OR confirmation OR purchase) newer_than:30d"
    result = service.users().messages().list(userId="me", q=query, maxResults=100).execute()
    messages = result.get("messages", [])
    thread_ids = list({m["threadId"] for m in messages})
    print(f"Found {len(messages)} messages across {len(thread_ids)} threads.")
    return thread_ids


if __name__ == "__main__":
    print("Fetching purchase email threads...")
    thread_ids = fetch_purchase_thread_ids()
    if not thread_ids:
        print("No threads found.")
    else:
        print(f"Archiving {len(thread_ids)} threads with label '{LABEL_NAME}'...")
        archive_threads(thread_ids)
