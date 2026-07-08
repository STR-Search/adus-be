# ADUS — Batch Underwriting by Preset (sample client)

A minimal client for `POST /iron-bank/underwritings/batch-prepare-by-preset`.
Full API reference: [`docs/iron_bank_batch_prepare_by_preset_api.md`](../../docs/iron_bank_batch_prepare_by_preset_api.md).

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env      # then edit .env with your ADUS_API_KEY
```

## Authentication

Requests authenticate with a single header — no login or token exchange:

```
X-ADUS-API-KEY: <your key>
```

The ADUS team gives you the key. Keep it secret; if it leaks, tell us and we'll
revoke it and issue a new one.

## Run

```bash
# Process listings created in the last 2 hours for a preset
python batch_prepare_by_preset.py 3f8b0c1e-1a2b-4c3d-9e8f-abc123456789 --since-hours 2

# Cap how many listings are processed
python batch_prepare_by_preset.py 3f8b0c1e-1a2b-4c3d-9e8f-abc123456789 --since-hours 2 --limit 50
```

The script prints the JSON summary (`found` / `saved` / `skipped_existing` /
`skipped_no_purchase_price` / `failed` and a per-listing `results` array). See the
API reference for the meaning of each per-listing status.

## Notes

- The call is synchronous and can take a while for large presets (the client uses a
  300s timeout).
- Retries are safe: underwritings already created are reported as `skipped_existing`
  rather than duplicated.
