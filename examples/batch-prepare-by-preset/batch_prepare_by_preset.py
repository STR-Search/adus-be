#!/usr/bin/env python3
"""
Sample client for the ADUS Batch Underwriting by Preset API.

Calls POST /iron-bank/underwritings/batch-prepare-by-preset for a given preset
and prints the summary. Authenticates with a single X-ADUS-API-KEY header.

Usage:
    # 1. Install deps
    pip install -r requirements.txt

    # 2. Configure credentials
    cp .env.example .env   # then edit .env

    # 3. Run
    python batch_prepare_by_preset.py <preset_id> --since-hours 2

    # Optional: cap how many listings are processed
    python batch_prepare_by_preset.py <preset_id> --since-hours 2 --limit 50
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH)

# The batch job runs synchronously and can take a while for large presets.
REQUEST_TIMEOUT_SECONDS = 300


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        sys.exit(f"Missing required environment variable: {name} (set it in {ENV_PATH})")
    return value


def batch_prepare_by_preset(preset_id: str, since_hours: int, limit: int | None = None):
    base_url = require_env("ADUS_BE_BASE_URL").rstrip("/")
    api_key = require_env("ADUS_API_KEY")

    params = {"preset_id": preset_id, "since_hours": since_hours}
    if limit is not None:
        params["limit"] = limit

    resp = requests.post(
        f"{base_url}/iron-bank/underwritings/batch-prepare-by-preset",
        headers={"X-ADUS-API-KEY": api_key},
        params=params,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    if not resp.ok:
        try:
            detail = resp.json()
        except ValueError:
            detail = resp.text
        sys.exit(f"Request failed ({resp.status_code}): {detail}")

    return resp.json()


def main():
    parser = argparse.ArgumentParser(
        description="Trigger ADUS batch underwriting for a Zillow scheduled preset."
    )
    parser.add_argument("preset_id", help="Scheduled preset UUID")
    parser.add_argument(
        "--since-hours",
        type=int,
        required=True,
        help="Only process listings created in the last N hours (>= 1)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on listings processed (>= 1)",
    )
    args = parser.parse_args()

    result = batch_prepare_by_preset(
        args.preset_id, since_hours=args.since_hours, limit=args.limit
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
