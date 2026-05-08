#!/usr/bin/env python3
"""Run the daily purchase digest via Anthropic Managed Agents.

Required environment variables:
    ANTHROPIC_API_KEY       — Anthropic API key
    PURCHASE_AGENT_ID       — Agent ID from: ant beta:agents create < purchase-digest.agent.yaml
    PURCHASE_ENV_ID         — Environment ID from: ant beta:environments create < purchase-digest.environment.yaml
    SLACK_BOT_TOKEN         — Slack bot OAuth token
    SLACK_USER_ID           — Slack user/channel ID to DM

Requires gmail_token.json in the working directory (run setup_gmail_auth.py first).
"""

import json
import os

import anthropic
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from slack_sdk import WebClient

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

client = anthropic.Anthropic()
AGENT_ID = os.environ["PURCHASE_AGENT_ID"]
ENV_ID = os.environ["PURCHASE_ENV_ID"]


# ── Gmail helpers ──────────────────────────────────────────────────────────────

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
    return created["id"]


# ── Tool handlers ──────────────────────────────────────────────────────────────

def handle_search_gmail(tool_input: dict) -> str:
    service = get_gmail_service()
    query = tool_input.get("query", "")
    max_results = tool_input.get("max_results", 100)

    result = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    messages = result.get("messages", [])

    details = []
    for msg in messages:
        msg_data = service.users().messages().get(
            userId="me",
            id=msg["id"],
            format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        ).execute()
        headers = {h["name"]: h["value"] for h in msg_data["payload"]["headers"]}
        details.append(
            {
                "id": msg["id"],
                "threadId": msg["threadId"],
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
            }
        )

    thread_ids = list({m["threadId"] for m in messages})
    return json.dumps({"messages": details, "thread_ids": thread_ids, "total": len(messages)})


def handle_send_slack_dm(tool_input: dict) -> str:
    slack = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
    message = tool_input.get("message", "")
    result = slack.chat_postMessage(channel=os.environ["SLACK_USER_ID"], text=message)
    return json.dumps({"ok": result["ok"], "ts": result["ts"]})


def handle_archive_gmail_threads(tool_input: dict) -> str:
    service = get_gmail_service()
    thread_ids: list[str] = tool_input.get("thread_ids", [])

    label_id = get_or_create_label(service, "Purchase Digests/Processed")

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
        except Exception as exc:
            errors.append({"thread_id": thread_id, "error": str(exc)})

    return json.dumps(
        {
            "archived": archived,
            "label": "Purchase Digests/Processed",
            "errors": errors,
        }
    )


def dispatch_tool(call) -> str:
    if call.name == "search_gmail":
        return handle_search_gmail(call.input)
    elif call.name == "send_slack_dm":
        return handle_send_slack_dm(call.input)
    elif call.name == "archive_gmail_threads":
        return handle_archive_gmail_threads(call.input)
    return json.dumps({"error": f"Unknown tool: {call.name}"})


# ── Main event loop ────────────────────────────────────────────────────────────

def run_digest():
    session = client.beta.sessions.create(
        agent={"type": "agent", "id": AGENT_ID},
        environment_id=ENV_ID,
    )
    print(f"Session: {session.id}")

    # Stream-first: open the event stream BEFORE sending the first message
    # to avoid missing early events.
    with client.beta.sessions.events.stream(session_id=session.id) as stream:
        client.beta.sessions.events.send(
            session_id=session.id,
            events=[
                {
                    "type": "user.message",
                    "content": [{"type": "text", "text": "Run the daily purchase digest."}],
                }
            ],
        )

        tool_calls = []
        for event in stream:
            if event.type == "agent.message":
                for block in event.content:
                    if block.type == "text":
                        print(block.text, end="", flush=True)
            elif event.type == "agent.custom_tool_use":
                print(f"\n[Tool: {event.name}]")
                tool_calls.append(event)
            elif event.type == "session.status_terminated":
                print("\nSession terminated.")
                return
            elif event.type == "session.status_idle":
                break

    # Outer loop: keep running until there are no more pending tool calls
    while tool_calls:
        results = [
            {
                "type": "user.custom_tool_result",
                "custom_tool_use_id": call.id,
                "content": [{"type": "text", "text": dispatch_tool(call)}],
            }
            for call in tool_calls
        ]

        client.beta.sessions.events.send(session_id=session.id, events=results)
        tool_calls = []

        with client.beta.sessions.events.stream(session_id=session.id) as stream:
            for event in stream:
                if event.type == "agent.message":
                    for block in event.content:
                        if block.type == "text":
                            print(block.text, end="", flush=True)
                elif event.type == "agent.custom_tool_use":
                    print(f"\n[Tool: {event.name}]")
                    tool_calls.append(event)
                elif event.type == "session.status_terminated":
                    print("\nSession terminated.")
                    return
                elif event.type == "session.status_idle":
                    break

    print("\nDigest complete.")


if __name__ == "__main__":
    run_digest()
