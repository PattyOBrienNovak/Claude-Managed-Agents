#!/usr/bin/env python3
"""Create or update the Managed Agent and Environment on Anthropic's platform.

First run:
    python3.12 setup_agent.py

To push config changes to an existing agent:
    python3.12 setup_agent.py --update

Reads ANTHROPIC_API_KEY from .env and writes PURCHASE_AGENT_ID / PURCHASE_ENV_ID back into it.
"""

import os
import re
import sys

import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

TOOLS = [
    {
        "type": "custom",
        "name": "search_gmail",
        "description": "Search Gmail for emails matching a query. Returns email metadata including thread IDs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Gmail search query string"},
                "max_results": {"type": "integer", "description": "Maximum number of emails to return (default 100)"},
            },
            "required": ["query"],
        },
    },
    {
        "type": "custom",
        "name": "send_slack_dm",
        "description": "Send a direct message to the configured Slack user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The message text to send"},
            },
            "required": ["message"],
        },
    },
    {
        "type": "custom",
        "name": "archive_gmail_threads",
        "description": 'Move the given Gmail thread IDs to the "Purchase Digest/Processed" folder (applies the label and removes from inbox).',
        "input_schema": {
            "type": "object",
            "properties": {
                "thread_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of Gmail thread IDs to label and archive",
                },
            },
            "required": ["thread_ids"],
        },
    },
]

SYSTEM = (
    "You are a Purchase Digest Agent. Your job is to:\n"
    "1. Search Gmail for up to 100 purchase-related emails (receipts, order confirmations, invoices)\n"
    '   older than 30 days. Use query: "subject:(order OR receipt OR invoice OR confirmation OR purchase) older_than:30d"\n'
    "2. Group the results by vendor/sender, counting emails per vendor.\n"
    "3. Send a formatted Slack DM summarizing: total emails found, breakdown by vendor (name + count),\n"
    "   and date range covered.\n"
    '4. Move all processed purchase email threads to the "Purchase Digest/Processed" folder by calling\n'
    "   archive_gmail_threads with the thread_ids returned from the search.\n\n"
    "Always complete all four steps in sequence. Never skip moving emails to the folder."
)


def update_env(key: str, value: str, env_path: str = ".env") -> None:
    with open(env_path, "r") as f:
        content = f.read()
    content = re.sub(rf"^{key}=.*$", f"{key}={value}", content, flags=re.MULTILINE)
    with open(env_path, "w") as f:
        f.write(content)


def main():
    if "--update" in sys.argv:
        agent_id = os.environ["PURCHASE_AGENT_ID"]
        print(f"Fetching current agent version for {agent_id}...")
        current = client.beta.agents.retrieve(agent_id)
        print(f"  Current version: {current.version}")
        agent = client.beta.agents.update(
            agent_id,
            version=current.version,
            system=SYSTEM,
            tools=TOOLS,
        )
        print(f"  Updated to version: {agent.version}")
        print("\nDone. Agent updated.")
        return

    print("Creating environment...")
    env = client.beta.environments.create(
        name="purchase-digest-env",
        config={"type": "cloud", "networking": {"type": "unrestricted"}},
    )
    print(f"  Environment ID: {env.id}")
    update_env("PURCHASE_ENV_ID", env.id)

    print("Creating agent...")
    agent = client.beta.agents.create(
        name="purchase-digest",
        model="claude-opus-4-7",
        system=SYSTEM,
        tools=TOOLS,
    )
    print(f"  Agent ID: {agent.id}")
    update_env("PURCHASE_AGENT_ID", agent.id)

    print("\nDone. .env updated with PURCHASE_AGENT_ID and PURCHASE_ENV_ID.")


if __name__ == "__main__":
    main()
