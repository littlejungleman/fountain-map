#!/usr/bin/env python3
"""
Scrapes bablands.com for fountain list and live statuses.
Outputs docs/data.json which the static map website reads.

Key points:
- wpDataTables renders ALL rows in the HTML (client-side pagination), so a single
  GET of the live page gets everything. No AJAX pagination needed unless the table
  grows > ~2000 rows (unlikely).
- Status values are "On/open" or "Off/not open" - must check "off" BEFORE checking
  for "open" since "Off/not open" contains "open".
- Table may not be sorted by date, so we pick the entry with the NEWEST timestamp
  per fountain.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SUBMISSIONS_URL = "https://bablands.com/fountainwatch/"
LIVE_URL        = "https://bablands.com/fountainwatch-live/"
COORDS_FILE     = Path(__file__).parent / "fountain_coords.json"
OUTPUT_FILE     = Path(__file__).parent.parent / "docs" / "data.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
}


def fetch_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text


def get_fountain_list(html: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    fountains = []
    for select in soup.find_all("select"):
        for opt in select.find_all("option"):
            name = opt.get_text(strip=True)
            if name and name.lower() not in ("", "select", "choose", "fountain/splash pad"):
                fountains.append(name)
    return fountains


def parse_status(raw: str) -> str | None:
    """
    Parse status string. IMPORTANT: check 'off' before 'open' because
    'Off/not open' contains the word 'open'.
    """
    lower = raw.lower()
    if "off" in lower or "not open" in lower or "closed" in lower:
        return "off"
    if "on" in lower or "open" in lower:
        return "on"
    return None


def parse_dt(s: str) -> datetime:
    for fmt in ("%d/%m/%Y %I:%M %p", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def get_live_statuses(html: str) -> dict:
    """
    Parse the live table and return the NEWEST status per fountain.
    wpDataTables renders all rows in HTML for client-side tables.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Collect all entries per fountain
    entries: dict[str, dict] = {}

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        count = 0
        for row in rows:
            cols = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if len(cols) < 3:
                continue
            name, raw_status, raw_date = cols[0].strip(), cols[1].strip(), cols[2].strip()

            # Skip header rows
            skip = {"fountain/splash pad", "status", "entry date", ""}
            if name.lower() in skip or raw_status.lower() in skip:
                continue

            status = parse_status(raw_status)
            if status is None:
                continue

            dt = parse_dt(raw_date)
            iso = dt.isoformat() if dt != datetime.min.replace(tzinfo=timezone.utc) else raw_date

            # Keep only the most recent entry per fountain
            if name not in entries or dt > entries[name]["dt"]:
                entries[name] = {"status": status, "reported_at": iso, "dt": dt}
            count += 1

        if count > 0:
            print(f"  Parsed {count} rows → {len(entries)} unique fountains")

    return {k: {"status": v["status"], "reported_at": v["reported_at"]}
            for k, v in entries.items()}


def load_coords() -> list:
    if not COORDS_FILE.exists():
        print(f"WARNING: coords file not found: {COORDS_FILE}", file=sys.stderr)
        return []
    with open(COORDS_FILE) as f:
        return json.load(f)


def main():
    print("Fetching fountain list from submissions page...")
    fountain_list = []
    try:
        fountain_list = get_fountain_list(fetch_html(SUBMISSIONS_URL))
        print(f"  {len(fountain_list)} fountains found")
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)

    print("Fetching live statuses...")
    statuses = {}
    try:
        statuses = get_live_statuses(fetch_html(LIVE_URL))
        print(f"  {len(statuses)} fountains with status data")
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)

    coords = load_coords()
    coords_by_name = {c["name"]: c for c in coords}

    # If scrape failed, fall back to coords list
    if not fountain_list:
        print("  Falling back to coords file for fountain list")
        fountain_list = [c["name"] for c in coords]

    fountains_out = []
    for name in fountain_list:
        c = coords_by_name.get(name, {})
        s = statuses.get(name, {})
        fountains_out.append({
            "name": name,
            "lat": c.get("lat"),
            "lon": c.get("lon"),
            "status": s.get("status", "unknown"),
            "reported_at": s.get("reported_at"),
        })

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "fountains": fountains_out,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    on  = sum(1 for f in fountains_out if f["status"] == "on")
    off = sum(1 for f in fountains_out if f["status"] == "off")
    unk = sum(1 for f in fountains_out if f["status"] == "unknown")
    print(f"\nWrote {OUTPUT_FILE}  |  on={on}  off={off}  no_data={unk}")


if __name__ == "__main__":
    main()
