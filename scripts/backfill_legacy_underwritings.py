"""Backfill legacy underwritings from the 'Underwritten Properties' Google Sheet export.

Reads either a local XLSX export or the live Google Sheet (--gsheet) and
loads each deal into iron_bank verbatim (no recalculation), marked with
source='legacy_sheet' and its sheet tab/link number so the team can verify
rows against the sheet.

Deal sources inside the workbook:
- Main_Sheet rows (header row 4) keyed by the 'Link' column
- Delete_Properties rows (header row 1) for deals already removed
- one tab per deal, named by its number ('233'..'1937'), parsed by section
  labels rather than fixed coordinates because the template shifted rows
  across versions.

Idempotent: deals whose sheet_number already exists in the DB are skipped
(and a partial unique index enforces this DB-side). Use --update to
delete-and-reinsert a range after parser fixes or a fresh export.

--gsheet reads live via the Sheets API instead of a local file (same
{summaries, tabs, listing_urls} shape either way, so everything downstream
is unaffected). Needs GOOGLE_SERVICE_ACCOUNT_CREDENTIALS set in the
environment -- a service account key as inline JSON, not a file path -- for
a service account already shared (Viewer) on the sheet.

Usage:
  python scripts/backfill_legacy_underwritings.py --dry-run
  python scripts/backfill_legacy_underwritings.py --range 1558:1937
  python scripts/backfill_legacy_underwritings.py --range 1558:1600 --update
  python scripts/backfill_legacy_underwritings.py --backfill-zpids
  python scripts/backfill_legacy_underwritings.py --gsheet <spreadsheet_id> --dry-run
"""

import argparse
import asyncio
import json
import os
import re
import sys
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parent.parent))

DEFAULT_XLSX = Path(__file__).resolve().parent.parent / "Underwritten Properties.xlsx"
REPORT_PATH = Path(__file__).resolve().parent / "backfill_report.json"

MAIN_SHEET = "Main_Sheet"
DELETE_SHEET = "Delete_Properties"
CLIENT_SHOWN_SHEET = "ClientShown_Properties"

# Status values as plain strings (mirroring app.iron_bank.enums.DealStatus and
# UnderwritingSource) so --dry-run never imports app.* — the app package pulls
# in config/DB at import time, which requires DATABASE_URL.
LEGACY_SOURCE = "legacy_sheet"
# Blank sheet statuses (no summary row, or an empty status cell) become this
# fixed DealStatus value.
NO_STATUS = "previously_underwritten_no_status"

# Sheet status label -> deal_status enum value.
STATUS_MAP: dict[str, str] = {
    "template generated": "template_generated",
    "analyst started": "analyst_started",
    "analyst completed": "analyst_completed",
    "delete - zillow": "delete_zillow",
    "delete zillow": "delete_zillow",
    "delete - deal": "delete_deal",
    "delete deal": "delete_deal",
    "delete": "delete_deal",
    "maybe": "maybe",
    "maybe (save for later)": "maybe",
    "re-forecast revenue": "re_forecast_revenue",
    "re forecast revenue": "re_forecast_revenue",
    "awaiting realtor details": "awaiting_realtor_details",
    "waiting on realtor": "awaiting_realtor_details",
    "present to clients": "present_to_clients",
    "client under contract": "client_under_contract",
    "training deal": "training_deal",
    "training deal for onboarding": "training_deal",
    "floorplan/ video needed": "awaiting_realtor_details",
    "taylor review needed": "analyst_completed",
}

# Sheet analyst labels that don't match "First LastInitial" against users.users.
# Values are matched against "first_name last_name" (lowercased). Extend as the
# unmatched-name warnings surface real cases.
NICKNAME_OVERRIDES: dict[str, str] = {
    "rizz (ahmed)": "ahmed mohamed rizk elsayed",
}


# ---------------------------------------------------------------------------
# value normalization
# ---------------------------------------------------------------------------


def to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().replace("$", "").replace(",", "").replace("%", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def to_int(value: Any) -> int | None:
    dec = to_decimal(value)
    return int(dec) if dec is not None else None


def to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def to_bool(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    # the sheet uses the literal string 'None' as its empty marker
    if not text or text.lower() == "none":
        return None
    return text


def jsonable(value: Any) -> Any:
    """Recursively converts Decimals to floats for JSONB columns."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    return value


# ---------------------------------------------------------------------------
# summary rows (Main_Sheet / Delete_Properties)
# ---------------------------------------------------------------------------

# field -> acceptable sheet header names, in preference order. Main_Sheet and
# Delete_Properties/ClientShown_Properties have drifted onto different header
# text for the same concept over time (e.g. 'Deal_Status' vs 'Status',
# 'Cash Needed' vs 'OOP', 'Notes' vs 'Note') -- every alias is matched, so
# either tab's current wording resolves to the same field.
SUMMARY_FIELD_ALIASES: dict[str, list[str]] = {
    "raw_status": ["Deal_Status", "Status"],
    "property_address": ["Property Address"],
    "city": ["City"],
    "state": ["ST"],
    "analyst_name": ["Analyst"],
    "approver_name": ["Approved By"],
    "deal_approved": ["Approved Time"],
    "purchase_price": ["PP"],
    "total_oop": ["Cash Needed", "OOP"],
    "prr": ["PRR"],
    "low_gross_revenue": ["Low"],
    "mid_gross_revenue": ["Mid"],
    "high_gross_revenue": ["High"],
    "l_cash_on_cash": ["L"],
    "m_cash_on_cash": ["M"],
    "h_cash_on_cash": ["H"],
    "deal_added": ["Date_Added"],
    "sleep_capacity": ["Bedrooms"],
    "turnkey": ["Turnkey?"],
    "property_pending": ["Property Pending"],
    "loom_vid": ["Loom_Vid"],
    "notes": ["Notes", "Note"],
    "link": ["Link"],
}

# Fields allowed to be absent from a given tab's header row without failing
# the run -- structural differences between tabs, not drift. Main_Sheet
# dropped its single 'Loom_Vid' column in favor of separate
# Deal_Pitch/video_walkthrough/Survey/Note columns this script doesn't parse
# yet. ClientShown_Properties is a minimal tab that has never tracked
# approver/turnkey/bedroom info. Every field not listed here is expected on
# that tab: if its header goes missing (renamed again, column deleted),
# that's exactly the kind of silent drift that produced wrong deal statuses
# for every row parsed after 'Deal_Status' became 'Status', so it's a hard
# error instead of a quiet None.
TAB_OPTIONAL_FIELDS: dict[str, set[str]] = {
    MAIN_SHEET: {"loom_vid"},
    CLIENT_SHOWN_SHEET: {"approver_name", "deal_approved", "sleep_capacity", "turnkey"},
}


def index_summary_rows(
    rows: Iterable[tuple], header_row: int, tab_name: str
) -> dict[int, dict[str, Any]]:
    """Returns {sheet_number: raw summary dict} for one summary tab.
    `rows` starts at `header_row` (the header itself is the first row)."""
    rows = iter(rows)
    headers = next(rows, None)
    if headers is None:
        return {}
    header_index = {name: idx for idx, name in enumerate(headers) if name}
    optional_fields = TAB_OPTIONAL_FIELDS.get(tab_name, set())
    col_for: dict[str, int] = {}
    missing: list[str] = []
    for field, aliases in SUMMARY_FIELD_ALIASES.items():
        idx = next((header_index[a] for a in aliases if a in header_index), None)
        if idx is not None:
            col_for[field] = idx
        elif field not in optional_fields:
            missing.append(f"{field} (tried {aliases})")
    if missing:
        raise ValueError(
            f"{tab_name!r} header row {header_row}: no matching column for "
            f"{', '.join(missing)}. The sheet's headers were likely renamed -- "
            "update SUMMARY_FIELD_ALIASES to match before backfilling."
        )
    address_col = col_for.get("property_address")
    result: dict[int, dict[str, Any]] = {}
    for row_number, row in enumerate(rows, start=header_row + 1):
        # read-only mode trims trailing empty cells, so rows vary in length
        raw = {
            field: row[idx] if idx < len(row) else None
            for field, idx in col_for.items()
        }
        link = to_int(raw.get("link"))
        if link is not None and _summary_has_content(raw):
            # where this row's address cell sits, e.g. "I5" — the tracking tabs
            # hyperlink the listing URL on the address text
            if address_col is not None:
                raw["_address_ref"] = f"{_column_letter(address_col)}{row_number}"
            result[link] = raw
    return result


def _column_letter(index: int) -> str:
    """0-based column index -> spreadsheet letters (0 -> A, 26 -> AA)."""
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _summary_has_content(raw: dict[str, Any]) -> bool:
    """Main_Sheet pre-numbers empty rows for future deals (Link filled,
    everything else blank) — those placeholders are not deals."""
    return any(
        clean_text(raw.get(field)) is not None
        for field in (
            "property_address",
            "raw_status",
            "purchase_price",
            "total_oop",
            "deal_added",
            "deal_approved",
            "loom_vid",
            "notes",
        )
    )


# ---------------------------------------------------------------------------
# deal tab parsing (label-anchored)
# ---------------------------------------------------------------------------

# column indexes in the grid (0-based): B=1, C=2, D=3, E=4, F=5, H=7, I=8,
# J=9, K=10, L=11, M=12


def _cell(grid: list[tuple], row: int, col: int) -> Any:
    if 0 <= row < len(grid) and 0 <= col < len(grid[row]):
        return grid[row][col]
    return None


def _find_row(grid: list[tuple], col: int, prefix: str) -> int | None:
    prefix = prefix.lower()
    for idx in range(len(grid)):
        value = _cell(grid, idx, col)
        if value is not None and str(value).strip().lower().startswith(prefix):
            return idx
    return None


def _parse_purchase_details(grid, warnings: list[str]) -> dict[str, Any]:
    start = _find_row(grid, 1, "purchase details")
    if start is None:
        warnings.append("section not found: Purchase Details")
        return {}
    labels = {
        "purchase price": ("purchase_price", 3),
        "down payment": ("down_payment", 3),
        "loan amount": ("loan_amount", 3),
        "interest rate": ("interest_rate", 3),
        "mortgage years": ("mortgage_years", 3),
        "closing costs": ("closing_costs", 3),
    }
    pct_labels = {"down payment": "down_payment_pct", "closing costs": "closing_costs_pct"}
    details: dict[str, Any] = {}
    for idx in range(start + 1, min(start + 10, len(grid))):
        label = clean_text(_cell(grid, idx, 1))
        if label is None:
            continue
        key = label.lower()
        for prefix, (field, col) in labels.items():
            if key.startswith(prefix):
                value = to_decimal(_cell(grid, idx, col))
                if value is not None:
                    details[field] = value
                if prefix in pct_labels:
                    pct = to_decimal(_cell(grid, idx, 2))
                    if pct is not None:
                        details[pct_labels[prefix]] = pct
                break
    return details


def _parse_construction_loan(grid) -> dict[str, Any] | None:
    """v4 tabs only: 'Loan Amount / Int Rate (Annual) / Term (Years)' in K/L/M."""
    for idx in range(len(grid)):
        if (
            clean_text(_cell(grid, idx, 10)) == "Loan Amount"
            and clean_text(_cell(grid, idx, 11)) is not None
            and "int rate" in str(_cell(grid, idx, 11)).lower()
        ):
            amount = to_decimal(_cell(grid, idx + 1, 10))
            if amount and amount > 0:
                return {
                    "loan_amount": amount,
                    "interest_rate": to_decimal(_cell(grid, idx + 1, 11)),
                    "term_years": to_decimal(_cell(grid, idx + 1, 12)),
                }
            return None
    return None


def _parse_optimization_items(grid, warnings: list[str]) -> list[dict[str, Any]]:
    # 'optim' catches both 'Optimization List (Estimate)' and the oldest
    # template's typo 'Optimzation List (Rough Estimate)'
    start = _find_row(grid, 4, "optim")
    if start is None:
        warnings.append("section not found: Optimization List")
        return []
    items: list[dict[str, Any]] = []
    for idx in range(start + 1, len(grid)):
        label = clean_text(_cell(grid, idx, 4))
        if label is None:
            continue
        if label.lower().startswith("total"):
            break
        price = to_decimal(_cell(grid, idx, 5))
        items.append({"category": label, "total_price": price})
    return items


def _parse_operating_expenses(grid, warnings: list[str]) -> list[dict[str, Any]]:
    start = _find_row(grid, 7, "operating expenses (opex)")
    if start is None:
        warnings.append("section not found: Operating Expenses (OPEX)")
        return []
    expenses: list[dict[str, Any]] = []
    for idx in range(start + 1, len(grid)):
        label = clean_text(_cell(grid, idx, 7))
        if label is None:
            continue
        lowered = label.lower()
        if lowered.startswith("total operating expenses"):
            break
        if lowered.startswith("disclaimer"):
            continue
        amount = to_decimal(_cell(grid, idx, 8))
        if amount is None and lowered in ("other", "misc"):
            continue
        expenses.append({"expense_name": label, "monthly_amount": amount})
    return expenses


def _parse_cleaning_cost(grid) -> dict[str, Any] | None:
    for idx in range(len(grid)):
        if (
            clean_text(_cell(grid, idx, 10)) == "Cleaning Cost"
            and clean_text(_cell(grid, idx, 11)) == "# of Turns"
        ):
            return {
                "cleaning_cost": to_decimal(_cell(grid, idx + 1, 10)),
                "turns_per_month": to_decimal(_cell(grid, idx + 1, 11)),
            }
    return None


def _parse_taxes(grid) -> dict[str, Any] | None:
    start = _find_row(grid, 1, "taxes")
    if start is None:
        return None
    labels = {
        "land assumptions": "land_assumptions_pct",
        "improvement basis": "improvement_basis",
        "estimated short life assets": "estimated_short_life_assets",
        "bonus amount": "bonus_amount_pct",
        "tax rate": "tax_rate_pct",
        "y1 loss from depreciation": "y1_loss_from_depreciation",
        "tax savings": "tax_savings",
    }
    taxes: dict[str, Any] = {}
    for idx in range(start + 1, min(start + 10, len(grid))):
        label = clean_text(_cell(grid, idx, 1))
        if label is None:
            continue
        key = label.lower()
        for prefix, field in labels.items():
            if key.startswith(prefix):
                value = to_decimal(_cell(grid, idx, 2))
                if value is not None:
                    taxes[field] = value
                break
    return taxes or None


# Sheet row label (column B) -> per-scenario key, matching the shape
# SaveUnderwritingService persists for app-created rows so the FE reads
# legacy and app underwritings identically. Values live in D/E/F = low/mid/high.
_SCENARIO_ROWS = {
    "forecasted revenue": "forecasted_revenue",
    "operating expenses (annual": "operating_expenses_annual",
    "co-hosting fee": "co_hosting_fee",
    "net operating income": "net_operating_income",
    "debt service (annual)": "debt_service_annual",
    "annual free cash flow": "annual_free_cash_flow",
}


def _parse_forecasted_revenue(grid) -> dict[str, Any] | None:
    anchor = _find_row(grid, 1, "forecasted revenue")
    if anchor is None:
        return None
    scenarios: dict[str, dict[str, Any]] = {"low": {}, "mid": {}, "high": {}}
    co_hosting_fee_pct = None
    for idx in range(anchor, min(anchor + 12, len(grid))):
        label = clean_text(_cell(grid, idx, 1))
        if label is None:
            continue
        key = label.lower()
        for prefix, field in _SCENARIO_ROWS.items():
            if key.startswith(prefix):
                for col, scenario in ((3, "low"), (4, "mid"), (5, "high")):
                    value = to_decimal(_cell(grid, idx, col))
                    if value is not None:
                        scenarios[scenario][field] = value
                if field == "co_hosting_fee":
                    co_hosting_fee_pct = to_decimal(_cell(grid, idx, 2))
                break
    if not any(scenarios.values()):
        return None
    result: dict[str, Any] = {"scenarios": scenarios}
    if co_hosting_fee_pct is not None:
        result["co_hosting_fee_pct"] = co_hosting_fee_pct
    return result


def _parse_y1_coc(grid) -> dict[str, Any] | None:
    """'Year 1 Cash on Cash, including Tax Savings' block (label in column D,
    Low/Mid/High header row, then the percentage values)."""
    for idx in range(len(grid)):
        label = clean_text(_cell(grid, idx, 3))
        if label is None or not label.lower().startswith("year 1 cash on cash"):
            continue
        for j in range(idx + 1, min(idx + 4, len(grid))):
            low = to_decimal(_cell(grid, j, 3))
            if low is not None:
                return {
                    "low_pct": low,
                    "mid_pct": to_decimal(_cell(grid, j, 4)),
                    "high_pct": to_decimal(_cell(grid, j, 5)),
                }
    return None


def _parse_comp_set(grid) -> list[dict[str, Any]]:
    header = None
    for idx in range(len(grid)):
        if clean_text(_cell(grid, idx, 7)) == "Listing URL":
            header = idx
            break
    if header is None:
        return []
    comps: list[dict[str, Any]] = []
    for idx in range(header + 1, len(grid)):
        url = clean_text(_cell(grid, idx, 7))
        if url is None:
            break
        comps.append(
            {
                "listing_url": url,
                "revenue": to_decimal(_cell(grid, idx, 8)),
                "bedrooms": to_int(_cell(grid, idx, 9)),
                "sleeps": to_int(_cell(grid, idx, 10)),
            }
        )
    return comps


def _parse_analyst_notes(grid) -> str | None:
    idx = _find_row(grid, 10, "analyst notes")
    if idx is None:
        return None
    return clean_text(_cell(grid, idx + 1, 10))


def _parse_prepared_by(grid) -> str | None:
    idx = _find_row(grid, 4, "prepared by")
    if idx is None:
        return None
    return clean_text(_cell(grid, idx, 5))


def _parse_property_url(grid) -> str | None:
    idx = _find_row(grid, 4, "property url")
    if idx is None:
        return None
    value = clean_text(_cell(grid, idx, 5))
    if value is not None and value.lower().startswith("http"):
        return value
    return None


def parse_deal_tab(grid: list[tuple]) -> dict[str, Any]:
    """Parses one deal tab's cell grid into child-record inputs + warnings."""
    warnings: list[str] = []
    purchase_details = _parse_purchase_details(grid, warnings)
    construction_loan = _parse_construction_loan(grid)
    if construction_loan:
        purchase_details["construction_loan"] = construction_loan
    return {
        "purchase_details": purchase_details,
        "cleaning_cost": _parse_cleaning_cost(grid),
        "forecasted_revenue": _parse_forecasted_revenue(grid),
        "y1_coc_incl_tax_savings": _parse_y1_coc(grid),
        "taxes": _parse_taxes(grid),
        "optimization_items": _parse_optimization_items(grid, warnings),
        "operating_expenses": _parse_operating_expenses(grid, warnings),
        "comp_set": _parse_comp_set(grid),
        "analyst_notes": _parse_analyst_notes(grid),
        "prepared_by": _parse_prepared_by(grid),
        "listing_url": _parse_property_url(grid),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# deal assembly
# ---------------------------------------------------------------------------


def map_deal_status(raw_status: Any) -> str:
    label = clean_text(raw_status)
    if label is None:
        return NO_STATUS
    status = STATUS_MAP.get(label.lower())
    if status is None:
        raise ValueError(f"unmapped sheet deal status: {label!r}")
    return status


def build_deal(
    sheet_number: int,
    summary: dict[str, Any] | None,
    tab: dict[str, Any] | None,
    listing_url: str | None = None,
) -> dict[str, Any]:
    """Assembles the repository.create() inputs for one deal."""
    warnings: list[str] = []
    notes: list[str] = []
    underwriting: dict[str, Any] = {
        "source": LEGACY_SOURCE,
        "sheet_number": sheet_number,
        "is_automated": False,
    }
    if listing_url:
        underwriting["listing_url"] = listing_url

    if summary is None:
        warnings.append("no summary row in any tracking tab (deal tab only)")
        underwriting["deal_status"] = NO_STATUS
    else:
        underwriting["deal_status"] = map_deal_status(summary.get("raw_status"))
        address = clean_text(summary.get("property_address"))
        underwriting.update(
            property_address=address,
            street=address.split(",")[0].strip() if address else None,
            city=clean_text(summary.get("city")),
            state=clean_text(summary.get("state")),
            purchase_price=to_decimal(summary.get("purchase_price")),
            total_oop=to_decimal(summary.get("total_oop")),
            prr=to_decimal(summary.get("prr")),
            low_gross_revenue=to_decimal(summary.get("low_gross_revenue")),
            mid_gross_revenue=to_decimal(summary.get("mid_gross_revenue")),
            high_gross_revenue=to_decimal(summary.get("high_gross_revenue")),
            l_cash_on_cash=to_decimal(summary.get("l_cash_on_cash")),
            m_cash_on_cash=to_decimal(summary.get("m_cash_on_cash")),
            h_cash_on_cash=to_decimal(summary.get("h_cash_on_cash")),
            deal_added=to_datetime(summary.get("deal_added")),
            deal_approved=to_datetime(summary.get("deal_approved")),
            sleep_capacity=to_int(summary.get("sleep_capacity")),
            turnkey=to_bool(summary.get("turnkey")),
            property_pending=to_bool(summary.get("property_pending")),
            loom_vid=clean_text(summary.get("loom_vid")),
        )
        pp = underwriting.get("purchase_price")
        oop = underwriting.get("total_oop")
        if pp and oop and pp > 0:
            underwriting["budget_to_pp"] = oop / pp
        # note carries only the sheet's own Notes column
        if clean_text(summary.get("notes")):
            notes.append(str(summary["notes"]).strip())

    detail: dict[str, Any] = {}
    taxes = None
    optimization_items: list[dict[str, Any]] = []
    operating_expenses: list[dict[str, Any]] = []
    comp_set: list[dict[str, Any]] = []

    if tab is None:
        warnings.append("no deal tab in workbook (summary row only)")
    else:
        warnings.extend(tab["warnings"])
        if tab["purchase_details"]:
            # JSONB columns can't take Decimals; numeric fidelity is preserved
            # in the typed columns, so floats are fine inside the JSON payloads
            detail["purchase_details"] = jsonable(tab["purchase_details"])
            if underwriting.get("purchase_price") is None:
                underwriting["purchase_price"] = tab["purchase_details"].get(
                    "purchase_price"
                )
        if tab["cleaning_cost"]:
            detail["cleaning_cost"] = jsonable(tab["cleaning_cost"])
        if tab["forecasted_revenue"]:
            detail["forecasted_revenue"] = jsonable(tab["forecasted_revenue"])
        if tab["y1_coc_incl_tax_savings"]:
            detail["y1_coc_incl_tax_savings"] = jsonable(
                tab["y1_coc_incl_tax_savings"]
            )
        if tab["analyst_notes"]:
            detail["analyst_notes"] = tab["analyst_notes"]
        if tab["listing_url"] and not underwriting.get("listing_url"):
            underwriting["listing_url"] = tab["listing_url"]
        taxes = tab["taxes"]
        optimization_items = tab["optimization_items"]
        operating_expenses = tab["operating_expenses"]
        comp_set = tab["comp_set"]

    analyst_name = clean_text(summary.get("analyst_name")) if summary else None
    if analyst_name is None and tab is not None:
        analyst_name = tab["prepared_by"]
    approver_name = clean_text(summary.get("approver_name")) if summary else None

    return {
        "sheet_number": sheet_number,
        "underwriting": underwriting,
        # Kept outside `underwriting`: it's spread straight into
        # Underwriting(**underwriting_data), and zpid is FK'd to
        # zillow.scheduled_listings, so it can only be assigned there once
        # load_deals() has confirmed it against that table.
        "candidate_zpid": extract_zpid(underwriting.get("listing_url")),
        "detail": detail or None,
        "taxes": taxes,
        "optimization_items": optimization_items,
        "operating_expenses": operating_expenses,
        "comp_set": comp_set,
        "analyst_name": analyst_name,
        "approver_name": approver_name,
        "notes": notes,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# workbook reading
# ---------------------------------------------------------------------------


def _sheet_targets(z) -> dict[str, str]:
    """Tab name -> worksheet xml path inside the xlsx."""
    workbook = z.read("xl/workbook.xml").decode()
    wb_rels = z.read("xl/_rels/workbook.xml.rels").decode()
    rel_target = {
        m.group(1): m.group(2)
        for m in re.finditer(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', wb_rels)
    }
    return {
        m.group(1): rel_target[m.group(2)]
        for m in re.finditer(r'<sheet[^>]*name="([^"]+)"[^>]*r:id="(rId\d+)"', workbook)
        if m.group(2) in rel_target
    }


def _external_hyperlinks(z, target: str) -> dict[str, str]:
    """Cell ref -> external URL for one worksheet file."""
    sheet_xml = z.read(f"xl/{target}").decode()
    links = re.findall(r'<hyperlink r:id="(rId\d+)" ref="([A-Z]+\d+)"', sheet_xml)
    if not links:
        return {}
    try:
        sheet_rels = z.read(
            f"xl/worksheets/_rels/{target.split('/')[-1]}.rels"
        ).decode()
    except KeyError:
        return {}
    targets = {
        m.group(1): m.group(2)
        for m in re.finditer(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', sheet_rels)
    }
    return {
        ref: targets[rid]
        for rid, ref in links
        if rid in targets and targets[rid].startswith("http")
    }


def extract_listing_urls(
    path: Path, tracking_rows: dict[str, dict[int, dict[str, Any]]]
) -> dict[int, str]:
    """Listing links live as hyperlinks in two places, neither visible to
    openpyxl's read-only mode, so they're pulled from the xlsx XML:
    - the PROPERTY URL / address cell (E/F, top rows) of each deal tab
    - the Property Address cell of each tracking-tab row (e.g. Main_Sheet I5)
    Precedence: deal tab > Main_Sheet > ClientShown > Delete_Properties."""
    import zipfile

    urls: dict[int, str] = {}
    with zipfile.ZipFile(path) as z:
        sheet_target = _sheet_targets(z)

        # lowest priority first; later writes win
        for tab in (DELETE_SHEET, CLIENT_SHOWN_SHEET, MAIN_SHEET):
            target = sheet_target.get(tab)
            if target is None or tab not in tracking_rows:
                continue
            by_ref = _external_hyperlinks(z, target)
            for link, raw in tracking_rows[tab].items():
                url = by_ref.get(raw.get("_address_ref", ""))
                if url:
                    urls[link] = url

        for name, target in sheet_target.items():
            if not re.fullmatch(r"\d+", name.strip()):
                continue
            by_ref = _external_hyperlinks(z, target)
            for ref, url in sorted(by_ref.items()):
                if re.fullmatch(r"[EF][1-6]", ref):
                    urls[int(name)] = url
                    break
    return urls


ZPID_RE = re.compile(r"(\d+)_zpid")


def extract_zpid(url: str | None) -> str | None:
    """Pulls the numeric zpid out of a Zillow listing URL, e.g.
    '.../12230595_zpid/'. Only Zillow URLs contain '_zpid', so no separate
    domain check is needed."""
    if not url:
        return None
    match = ZPID_RE.search(url)
    return match.group(1) if match else None


def read_workbook(path: Path) -> dict[str, Any]:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    main_rows = index_summary_rows(
        wb[MAIN_SHEET].iter_rows(min_row=4, values_only=True),
        header_row=4,
        tab_name=MAIN_SHEET,
    )
    deleted_rows = (
        index_summary_rows(
            wb[DELETE_SHEET].iter_rows(min_row=1, values_only=True),
            header_row=1,
            tab_name=DELETE_SHEET,
        )
        if DELETE_SHEET in wb.sheetnames
        else {}
    )
    client_shown_rows = (
        index_summary_rows(
            wb[CLIENT_SHOWN_SHEET].iter_rows(min_row=1, values_only=True),
            header_row=1,
            tab_name=CLIENT_SHOWN_SHEET,
        )
        if CLIENT_SHOWN_SHEET in wb.sheetnames
        else {}
    )
    tabs: dict[int, list[tuple]] = {}
    for name in wb.sheetnames:
        if re.fullmatch(r"\d+", name.strip()):
            tabs[int(name)] = [
                row for row in wb[name].iter_rows(max_row=80, values_only=True)
            ]
    wb.close()
    # When a link appears in several tracking tabs:
    # Main_Sheet > ClientShown_Properties > Delete_Properties.
    summaries = {**deleted_rows, **client_shown_rows, **main_rows}
    return {
        "summaries": summaries,
        "tabs": tabs,
        "listing_urls": extract_listing_urls(
            path,
            {
                MAIN_SHEET: main_rows,
                CLIENT_SHOWN_SHEET: client_shown_rows,
                DELETE_SHEET: deleted_rows,
            },
        ),
    }


# ---------------------------------------------------------------------------
# live Google Sheet reading (--gsheet)
# ---------------------------------------------------------------------------

GOOGLE_SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SHEETS_API_BATCH_SIZE = 50
DEAL_TAB_RANGE = "A1:Z80"  # deal tabs: every labeled section lives in the first 80 rows
SHEET_CELL_FIELDS = (
    "sheets(properties.title,data.rowData.values("
    "effectiveValue,effectiveFormat.numberFormat,hyperlink))"
)


def _sheets_service():
    """Authenticates via a service account passed as inline JSON (not a file
    path) in GOOGLE_SERVICE_ACCOUNT_CREDENTIALS -- the same service account
    already shared on the sheet, reused from another project rather than
    provisioning a new one.

    httplib2's default socket timeout is short enough that a metadata-only
    call started timing out once the workbook grew past ~800 tabs; an
    explicit, longer timeout on the transport (not the retry logic) fixes
    that without masking a real failure.
    """
    import httplib2
    from google.oauth2 import service_account
    from google_auth_httplib2 import AuthorizedHttp
    from googleapiclient.discovery import build

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_CREDENTIALS")
    if not raw:
        sys.exit(
            "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS is not set "
            "(a service account key, as inline JSON)."
        )
    info = json.loads(raw)
    credentials = service_account.Credentials.from_service_account_info(
        info, scopes=GOOGLE_SHEETS_SCOPES
    )
    authorized_http = AuthorizedHttp(credentials, http=httplib2.Http(timeout=180))
    return build("sheets", "v4", http=authorized_http, cache_discovery=False)


def _a1_ref(row_idx: int, col_idx: int) -> str:
    return f"{_column_letter(col_idx)}{row_idx + 1}"


def _cell_value(cell: dict[str, Any]) -> Any:
    """Converts one Sheets API CellData dict into the same typed value
    openpyxl's data_only=True mode would give us: a real datetime for a
    date/time-formatted cell, a plain number otherwise (percentages are
    already stored as their raw fraction, same as openpyxl -- '16.53%' is
    numberValue 0.1653), or a string."""
    effective = cell.get("effectiveValue") or {}
    if "numberValue" in effective:
        number = effective["numberValue"]
        fmt = ((cell.get("effectiveFormat") or {}).get("numberFormat") or {}).get(
            "type"
        )
        if fmt in ("DATE", "DATE_TIME"):
            # Sheets and Excel share the same serial-date epoch (1899-12-30)
            return datetime(1899, 12, 30, tzinfo=timezone.utc) + timedelta(
                days=number
            )
        return number
    if "stringValue" in effective:
        return effective["stringValue"]
    if "boolValue" in effective:
        return effective["boolValue"]
    return None


def _grid_from_sheet_data(
    sheet_data: dict[str, Any],
) -> tuple[list[tuple], dict[str, str]]:
    """One requested range's GridData -> (grid rows, {cell_ref: hyperlink})."""
    row_data = (sheet_data.get("data") or [{}])[0].get("rowData") or []
    grid: list[tuple] = []
    hyperlinks: dict[str, str] = {}
    for row_idx, row in enumerate(row_data):
        values = row.get("values") or []
        row_values = []
        for col_idx, cell in enumerate(values):
            row_values.append(_cell_value(cell))
            link = cell.get("hyperlink")
            if link:
                hyperlinks[_a1_ref(row_idx, col_idx)] = link
        grid.append(tuple(row_values))
    return grid, hyperlinks


def _fetch_sheet_grids(
    service, spreadsheet_id: str, ranges: list[str]
) -> dict[str, tuple[list[tuple], dict[str, str]]]:
    """Batched grid+hyperlink fetch for a list of A1 ranges (e.g.
    'Main_Sheet' or '233!A1:Z80'), chunked to stay within the API's
    per-request size/quota limits. Returns {tab_title: (grid, hyperlinks)}."""
    result: dict[str, tuple[list[tuple], dict[str, str]]] = {}
    for i in range(0, len(ranges), SHEETS_API_BATCH_SIZE):
        chunk = ranges[i : i + SHEETS_API_BATCH_SIZE]
        response = (
            service.spreadsheets()
            .get(spreadsheetId=spreadsheet_id, ranges=chunk, fields=SHEET_CELL_FIELDS)
            .execute()
        )
        for sheet in response.get("sheets", []):
            title = sheet["properties"]["title"]
            result[title] = _grid_from_sheet_data(sheet)
    return result


def read_google_sheet(spreadsheet_id: str) -> dict[str, Any]:
    """Live equivalent of read_workbook(), sourced from the Sheets API
    instead of a local xlsx export. Produces the identical
    {summaries, tabs, listing_urls} shape build_deal()/load_deals() expect,
    so nothing downstream needs to know which source was used."""
    service = _sheets_service()
    metadata = (
        service.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="sheets.properties.title")
        .execute()
    )
    titles = [s["properties"]["title"] for s in metadata.get("sheets", [])]
    deal_tab_names = [name for name in titles if re.fullmatch(r"\d+", name.strip())]

    tracking_names = [
        name for name in (MAIN_SHEET, DELETE_SHEET, CLIENT_SHOWN_SHEET) if name in titles
    ]
    tracking_grids = _fetch_sheet_grids(service, spreadsheet_id, tracking_names)

    deal_ranges = [f"{name}!{DEAL_TAB_RANGE}" for name in deal_tab_names]
    deal_grids = _fetch_sheet_grids(service, spreadsheet_id, deal_ranges)

    def summary_rows(tab_name: str, header_row: int) -> dict[int, dict[str, Any]]:
        if tab_name not in tracking_grids:
            return {}
        grid, _ = tracking_grids[tab_name]
        return index_summary_rows(
            iter(grid[header_row - 1 :]), header_row=header_row, tab_name=tab_name
        )

    main_rows = summary_rows(MAIN_SHEET, header_row=4)
    deleted_rows = summary_rows(DELETE_SHEET, header_row=1)
    client_shown_rows = summary_rows(CLIENT_SHOWN_SHEET, header_row=1)

    tabs: dict[int, list[tuple]] = {
        int(name): deal_grids.get(name, ([], {}))[0] for name in deal_tab_names
    }

    # Precedence: deal tab > Main_Sheet > ClientShown > Delete_Properties,
    # matching extract_listing_urls()'s ordering for the xlsx path.
    listing_urls: dict[int, str] = {}
    for tab_name, rows in (
        (DELETE_SHEET, deleted_rows),
        (CLIENT_SHOWN_SHEET, client_shown_rows),
        (MAIN_SHEET, main_rows),
    ):
        _, hyperlinks = tracking_grids.get(tab_name, ([], {}))
        for link, raw in rows.items():
            url = hyperlinks.get(raw.get("_address_ref", ""))
            if url:
                listing_urls[link] = url
    for name in deal_tab_names:
        _, hyperlinks = deal_grids.get(name, ([], {}))
        for ref, url in sorted(hyperlinks.items()):
            if re.fullmatch(r"[EF][1-6]", ref):
                listing_urls[int(name)] = url
                break

    summaries = {**deleted_rows, **client_shown_rows, **main_rows}
    return {"summaries": summaries, "tabs": tabs, "listing_urls": listing_urls}


# ---------------------------------------------------------------------------
# user matching
# ---------------------------------------------------------------------------


def build_user_matcher(users: list[Any]):
    """Matches sheet labels like 'Taylor J' / 'John B' to users.users ids.

    A bare first name (no last name/initial in the sheet label -- e.g. just
    'Carson') matches a *named* user (one with a last_name on file) only
    when exactly one such user shares that first name; two named users
    sharing a first name would make a bare label genuinely ambiguous, so
    neither gets a first-name-only key and the label falls through to a
    placeholder instead of guessing wrong.

    A user with NO last name is a different case and always gets the bare
    key regardless of how many named users share that first name: such a
    user is typically itself a placeholder created earlier for this exact
    bare-name label, and there's no more specific key it could ever match
    under -- refusing the bare match here would just recreate it every run
    and crash on the clerk_id unique constraint (a user with a first-only
    name and no matching entry has nothing to fall back to).
    """
    by_key: dict[str, int] = {}
    first_name_counts: dict[str, int] = {}
    for user in users:
        first = (user.first_name or "").strip().lower()
        last = (user.last_name or "").strip().lower()
        if first and last:
            first_name_counts[first] = first_name_counts.get(first, 0) + 1

    for user in users:
        first = (user.first_name or "").strip().lower()
        last = (user.last_name or "").strip().lower()
        if not first:
            continue
        if last:
            by_key.setdefault(f"{first} {last}", user.id)
            by_key.setdefault(f"{first} {last[0]}", user.id)
            if first_name_counts[first] == 1:
                by_key.setdefault(first, user.id)
        else:
            by_key.setdefault(first, user.id)

    def match(name: str | None) -> int | None:
        if not name:
            return None
        key = name.strip().lower()
        key = NICKNAME_OVERRIDES.get(key, key)
        return by_key.get(key)

    return match


def split_person_name(label: str) -> tuple[str, str | None]:
    """'Taylor J' -> ('Taylor', 'J'); 'Kevin' -> ('Kevin', None)."""
    first, _, last = label.strip().partition(" ")
    return first, (last.strip() or None)


def legacy_clerk_id(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")
    return f"legacy_{slug}"


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------


async def load_deals(deals: list[dict[str, Any]], update: bool) -> dict[str, Any]:
    from sqlalchemy import delete, select

    from app.core.database import AsyncSessionLocal
    from app.iron_bank.models import Underwriting
    from app.iron_bank.repositories.underwriting_repository import (
        UnderwritingRepository,
    )
    from app.users.models.user import User
    from app.zillow.repositories.scheduled_listings_repository import (
        ScheduledListingsRepository,
    )
    from app.zillow.services.scheduled_listings_service import (
        ScheduledListingsService,
    )

    inserted, skipped, failed = [], [], []
    zpids_matched = 0
    async with AsyncSessionLocal() as session:
        existing = set(
            (
                await session.execute(
                    select(Underwriting.sheet_number).where(
                        Underwriting.sheet_number.isnot(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        users = (
            (await session.execute(select(User).where(User.is_deleted.isnot(True))))
            .scalars()
            .all()
        )
        match_user = build_user_matcher(users)
        created_users: dict[str, int] = {}
        repository = UnderwritingRepository(session)

        # zpid is FK'd to zillow.scheduled_listings, which only holds Zillow's
        # currently-scraped listings, so a candidate extracted from an old
        # sheet URL may no longer be present there. Only ones that are get
        # written; everything else stays NULL, same as before this change.
        listings_service = ScheduledListingsService(ScheduledListingsRepository(session))
        candidate_zpids = list(
            {d["candidate_zpid"] for d in deals if d.get("candidate_zpid")}
        )
        confirmed_listings = await listings_service.get_by_zpids(candidate_zpids)

        async def resolve_user(name: str | None) -> int | None:
            """Match an existing user, or create a placeholder to link to."""
            if not name:
                return None
            user_id = match_user(name)
            if user_id is not None:
                return user_id
            key = name.strip().lower()
            if key not in created_users:
                first, last = split_person_name(name)
                user = User(
                    clerk_id=legacy_clerk_id(name), first_name=first, last_name=last
                )
                session.add(user)
                # commit immediately so a later failed deal insert can't roll
                # the user back while its id stays cached in created_users
                await session.commit()
                created_users[key] = user.id
            return created_users[key]

        for deal in deals:
            number = deal["sheet_number"]
            if number in existing:
                if not update:
                    skipped.append(number)
                    continue
                await session.execute(
                    delete(Underwriting).where(
                        Underwriting.sheet_number == number,
                        Underwriting.source == LEGACY_SOURCE,
                    )
                )
                await session.commit()

            underwriting = dict(deal["underwriting"])
            underwriting["analyst_id"] = await resolve_user(deal["analyst_name"])
            underwriting["approver_id"] = await resolve_user(deal["approver_name"])
            candidate_zpid = deal.get("candidate_zpid")
            if candidate_zpid in confirmed_listings:
                underwriting["zpid"] = candidate_zpid
                zpids_matched += 1
            if deal["notes"]:
                underwriting["note"] = "\n".join(deal["notes"])

            try:
                created = await repository.create(
                    underwriting_data=underwriting,
                    detail_data=deal["detail"],
                    tax_data=deal["taxes"],
                    optimization_items=deal["optimization_items"],
                    operating_expenses=deal["operating_expenses"],
                    comp_set=deal["comp_set"],
                )
                inserted.append({"sheet_number": number, "id": created.id})
            except Exception as exc:  # keep going; report at the end
                failed.append({"sheet_number": number, "error": str(exc)})

    return {
        "inserted": inserted,
        "skipped": skipped,
        "failed": failed,
        "created_users": created_users,
        "zpids_matched": zpids_matched,
    }


async def refresh_deals(deals: list[dict[str, Any]], dry_run: bool) -> dict[str, Any]:
    """In-place UPDATE for sheet_numbers that already exist in the DB, so a
    later sheet edit (status change, corrected price, parser fix) reaches
    rows already backfilled -- without --update's delete+reinsert downsides:
    no id churn, and uw_details.zillow_property (populated by a separate
    script, never by this one) is never touched.

    Two safety nets, both learned the hard way on this exact sheet:
    - A sheet_number whose fresh parse finds neither a summary row nor a
      deal tab (the sheet transiently or permanently lost both) is left
      alone entirely -- reported under 'no_current_data' -- rather than
      overwriting good historical data with an empty/no-status record.
    - optimization_items/operating_expenses are only replaced when the deal
      tab's parser actually found that section this time; a 'section not
      found' warning means the template didn't match, not that the sheet
      now has zero items, so the existing rows are left as-is rather than
      wiped by a parsing gap. taxes/comp_set have no such warning signal,
      so they're only replaced when the fresh parse is non-empty.

    Only touches rows that already exist; a sheet_number not yet in the DB
    is reported under 'not_found' -- run without --refresh to insert those.
    """
    from sqlalchemy import delete, select

    from app.core.database import AsyncSessionLocal
    from app.iron_bank.models import (
        Underwriting,
        UnderwritingCompSet,
        UnderwritingDetail,
        UnderwritingOperatingExpense,
        UnderwritingOptimizationItem,
        UnderwritingTax,
    )
    from app.users.models.user import User
    from app.zillow.repositories.scheduled_listings_repository import (
        ScheduledListingsRepository,
    )
    from app.zillow.services.scheduled_listings_service import (
        ScheduledListingsService,
    )

    updated, not_found, no_current_data, detail_only, failed = [], [], [], [], []
    zpids_matched = 0

    async with AsyncSessionLocal() as session:
        users = (
            (await session.execute(select(User).where(User.is_deleted.isnot(True))))
            .scalars()
            .all()
        )
        match_user = build_user_matcher(users)
        created_users: dict[str, int | None] = {}

        listings_service = ScheduledListingsService(ScheduledListingsRepository(session))
        candidate_zpids = list(
            {d["candidate_zpid"] for d in deals if d.get("candidate_zpid")}
        )
        confirmed_listings = await listings_service.get_by_zpids(candidate_zpids)

        async def resolve_user(name: str | None) -> int | None:
            """Match an existing user, or create a placeholder -- except in
            dry_run, where nothing is persisted and an unmatched name simply
            resolves to None for the preview."""
            if not name:
                return None
            user_id = match_user(name)
            if user_id is not None:
                return user_id
            key = name.strip().lower()
            if key not in created_users:
                if dry_run:
                    created_users[key] = None
                else:
                    first, last = split_person_name(name)
                    user = User(
                        clerk_id=legacy_clerk_id(name), first_name=first, last_name=last
                    )
                    session.add(user)
                    await session.commit()
                    created_users[key] = user.id
            return created_users[key]

        for deal in deals:
            number = deal["sheet_number"]

            warnings = set(deal["warnings"])
            no_summary = (
                "no summary row in any tracking tab (deal tab only)" in warnings
            )
            no_tab = "no deal tab in workbook (summary row only)" in warnings
            if no_summary and no_tab:
                no_current_data.append(number)
                continue

            try:
                # deal_status, property_address, city, state, analyst/
                # approver, revenue figures, turnkey, etc. only ever come
                # from the summary row (build_deal's underwriting dict is
                # just {source, sheet_number, is_automated, deal_status,
                # listing_url?, purchase_price?} when summary is None) --
                # deal_status specifically defaults to NO_STATUS in that
                # case. Applying that dict here when the summary is simply
                # missing from *this* parse (not permanently gone -- the tab
                # still exists) would silently downgrade a real status to
                # "no status" and blank out fields that were never actually
                # cleared on the sheet. So when summary is missing, skip the
                # underwriting row entirely and only refresh the deal tab's
                # own detail/tax/line-item data below.
                underwriting_data: dict[str, Any] | None = None
                if no_summary:
                    detail_only.append(number)
                else:
                    underwriting_data = dict(deal["underwriting"])
                    underwriting_data.pop("source", None)
                    underwriting_data.pop("sheet_number", None)
                    underwriting_data.pop("is_automated", None)
                    # Resolved before the fetch below, not after:
                    # resolve_user() may commit a new placeholder user, and
                    # an async session expires every loaded object on
                    # commit/rollback -- touching `existing` again after
                    # that without an explicit refresh raises
                    # greenlet_spawn errors. Resolving first guarantees it's
                    # never stale when the setattrs below run.
                    underwriting_data["analyst_id"] = await resolve_user(
                        deal["analyst_name"]
                    )
                    underwriting_data["approver_id"] = await resolve_user(
                        deal["approver_name"]
                    )
                    candidate_zpid = deal.get("candidate_zpid")
                    if candidate_zpid in confirmed_listings:
                        underwriting_data["zpid"] = candidate_zpid
                        zpids_matched += 1
                    if deal["notes"]:
                        underwriting_data["note"] = "\n".join(deal["notes"])

                existing = (
                    await session.execute(
                        select(Underwriting).where(
                            Underwriting.source == LEGACY_SOURCE,
                            Underwriting.sheet_number == number,
                        )
                    )
                ).scalar_one_or_none()
                if existing is None:
                    not_found.append(number)
                    continue
                if underwriting_data is not None:
                    for key, value in underwriting_data.items():
                        setattr(existing, key, value)

                detail_data = deal["detail"] or {}
                if detail_data:
                    detail = (
                        await session.execute(
                            select(UnderwritingDetail).where(
                                UnderwritingDetail.underwriting_id == existing.id
                            )
                        )
                    ).scalar_one_or_none()
                    if detail is None:
                        detail = UnderwritingDetail(underwriting_id=existing.id)
                        session.add(detail)
                    for key, value in detail_data.items():
                        setattr(detail, key, value)

                if deal["taxes"]:
                    await session.execute(
                        delete(UnderwritingTax).where(
                            UnderwritingTax.underwriting_id == existing.id
                        )
                    )
                    session.add(
                        UnderwritingTax(underwriting_id=existing.id, **deal["taxes"])
                    )

                if "section not found: Optimization List" not in warnings:
                    await session.execute(
                        delete(UnderwritingOptimizationItem).where(
                            UnderwritingOptimizationItem.underwriting_id == existing.id
                        )
                    )
                    for index, item in enumerate(deal["optimization_items"]):
                        session.add(
                            UnderwritingOptimizationItem(
                                underwriting_id=existing.id, sort_order=index, **item
                            )
                        )

                if "section not found: Operating Expenses (OPEX)" not in warnings:
                    await session.execute(
                        delete(UnderwritingOperatingExpense).where(
                            UnderwritingOperatingExpense.underwriting_id == existing.id
                        )
                    )
                    for index, item in enumerate(deal["operating_expenses"]):
                        session.add(
                            UnderwritingOperatingExpense(
                                underwriting_id=existing.id, sort_order=index, **item
                            )
                        )

                if deal["comp_set"]:
                    await session.execute(
                        delete(UnderwritingCompSet).where(
                            UnderwritingCompSet.underwriting_id == existing.id
                        )
                    )
                    for index, item in enumerate(deal["comp_set"]):
                        session.add(
                            UnderwritingCompSet(
                                underwriting_id=existing.id, sort_order=index, **item
                            )
                        )

                if dry_run:
                    await session.rollback()
                else:
                    await session.commit()
                updated.append(number)
            except Exception as exc:  # keep going; report at the end
                await session.rollback()
                failed.append({"sheet_number": number, "error": str(exc)})

    return {
        "updated": updated,
        "detail_only": detail_only,
        "not_found": not_found,
        "no_current_data": no_current_data,
        "failed": failed,
        "created_users": created_users,
        "zpids_matched": zpids_matched,
    }


async def backfill_missing_zpids() -> dict[str, Any]:
    """Fills zpid on already-loaded legacy rows from their stored listing_url.
    In-place UPDATE only (no delete/reinsert): ids and created_at on existing
    rows are untouched. Safe to run repeatedly -- it only ever targets rows
    where zpid is still NULL."""
    from sqlalchemy import select, update

    from app.core.database import AsyncSessionLocal
    from app.iron_bank.models import Underwriting
    from app.zillow.repositories.scheduled_listings_repository import (
        ScheduledListingsRepository,
    )
    from app.zillow.services.scheduled_listings_service import (
        ScheduledListingsService,
    )

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Underwriting.id, Underwriting.listing_url).where(
                    Underwriting.source == LEGACY_SOURCE,
                    Underwriting.zpid.is_(None),
                    Underwriting.listing_url.isnot(None),
                )
            )
        ).all()

        candidates = {
            row.id: zpid
            for row in rows
            if (zpid := extract_zpid(row.listing_url)) is not None
        }

        listings_service = ScheduledListingsService(ScheduledListingsRepository(session))
        confirmed = await listings_service.get_by_zpids(list(set(candidates.values())))

        updated = []
        for underwriting_id, zpid in candidates.items():
            if zpid in confirmed:
                await session.execute(
                    update(Underwriting)
                    .where(Underwriting.id == underwriting_id)
                    .values(zpid=zpid)
                )
                updated.append({"id": underwriting_id, "zpid": zpid})
        await session.commit()

    return {"checked": len(rows), "extracted": len(candidates), "updated": updated}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_range(text: str | None) -> tuple[int, int] | None:
    if text is None:
        return None
    low, _, high = text.partition(":")
    return int(low), int(high)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill legacy underwritings from the Google Sheet XLSX export."
    )
    parser.add_argument(
        "--xlsx",
        type=Path,
        default=DEFAULT_XLSX,
        help="Path to the 'Underwritten Properties' export.",
    )
    parser.add_argument(
        "--gsheet",
        type=str,
        default=None,
        help=(
            "Google Sheet spreadsheet id: pulls live instead of --xlsx. "
            "Needs GOOGLE_SERVICE_ACCOUNT_CREDENTIALS (a service account "
            "key, as inline JSON) set in the environment."
        ),
    )
    parser.add_argument(
        "--range",
        type=str,
        default=None,
        help="Only process sheet numbers LOW:HIGH inclusive, e.g. 1558:1937.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report only; no database access.",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Delete-and-reinsert deals that already exist (parser fixes, fresh export).",
    )
    parser.add_argument(
        "--backfill-zpids",
        action="store_true",
        help=(
            "Fill zpid on already-loaded legacy rows from their stored "
            "listing_url (targeted UPDATE; no xlsx, no delete/reinsert)."
        ),
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help=(
            "In-place UPDATE for sheet_numbers that already exist (status "
            "changes, corrected figures, parser fixes reaching the sheet "
            "since backfill) -- keeps id and uw_details.zillow_property "
            "untouched, unlike --update's delete+reinsert. Combine with "
            "--dry-run to preview without writing (still queries the DB, "
            "unlike a plain --dry-run)."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.backfill_zpids:
        result = asyncio.run(backfill_missing_zpids())
        print(json.dumps(result, indent=2, default=str))
        return
    bounds = parse_range(args.range)
    if args.gsheet is not None:
        data = read_google_sheet(args.gsheet)
    else:
        if not args.xlsx.exists():
            sys.exit(f"XLSX not found: {args.xlsx}")
        data = read_workbook(args.xlsx)
    numbers = sorted(set(data["summaries"]) | set(data["tabs"]))
    if bounds:
        numbers = [n for n in numbers if bounds[0] <= n <= bounds[1]]

    deals = [
        build_deal(
            n,
            data["summaries"].get(n),
            _parsed_tab(data, n),
            listing_url=data["listing_urls"].get(n),
        )
        for n in numbers
    ]

    if args.refresh:
        result = asyncio.run(refresh_deals(deals, dry_run=args.dry_run))
        report = {
            "source": (
                f"gsheet:{args.gsheet}" if args.gsheet is not None else str(args.xlsx)
            ),
            "range": args.range,
            "dry_run": args.dry_run,
            "deals_found": len(deals),
            "updated": len(result["updated"]),
            "detail_only": result["detail_only"],
            "not_found": len(result["not_found"]),
            "no_current_data": len(result["no_current_data"]),
            "created_placeholder_users": result["created_users"],
            "failed": result["failed"],
            "zpids_matched": result["zpids_matched"],
            "deals_with_warnings": [
                {"sheet_number": deal["sheet_number"], "warnings": deal["warnings"]}
                for deal in deals
                if deal["warnings"]
            ],
        }
        REPORT_PATH.write_text(json.dumps(report, indent=2, default=str))
        print(
            json.dumps(
                {k: v for k, v in report.items() if k != "deals_with_warnings"},
                indent=2,
                default=str,
            )
        )
        print(
            f"{len(report['deals_with_warnings'])} deals with warnings "
            f"-> {REPORT_PATH}"
        )
        return

    if args.dry_run:
        result = {
            "inserted": [],
            "skipped": [],
            "failed": [],
            "created_users": {},
            "zpids_matched": 0,
        }
    else:
        result = asyncio.run(load_deals(deals, update=args.update))

    report = {
        "source": f"gsheet:{args.gsheet}" if args.gsheet is not None else str(args.xlsx),
        "range": args.range,
        "dry_run": args.dry_run,
        "deals_found": len(deals),
        "inserted": len(result["inserted"]),
        "skipped_existing": len(result["skipped"]),
        "created_placeholder_users": result["created_users"],
        "failed": result["failed"],
        "zpids_extracted": sum(1 for deal in deals if deal.get("candidate_zpid")),
        "zpids_matched": result["zpids_matched"],
        "deals_with_warnings": [
            {"sheet_number": deal["sheet_number"], "warnings": deal["warnings"]}
            for deal in deals
            if deal["warnings"]
        ],
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, default=str))

    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "deals_with_warnings"},
            indent=2,
            default=str,
        )
    )
    print(
        f"{len(report['deals_with_warnings'])} deals with warnings "
        f"-> {REPORT_PATH}"
    )


def _parsed_tab(data: dict[str, Any], number: int) -> dict[str, Any] | None:
    grid = data["tabs"].get(number)
    return parse_deal_tab(grid) if grid is not None else None


if __name__ == "__main__":
    main()
