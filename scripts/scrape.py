#!/usr/bin/env python3
"""
Scrapes bablands.com for:
1. The list of fountains (from the submission form dropdown)
2. The latest status of each fountain (from the live table)

Outputs docs/data.json which the static website reads.
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SUBMISSIONS_URL = "https://bablands.com/fountainwatch/"
LIVE_URL = "https://bablands.com/fountainwatch-live/"
COORDS_FILE = Path(__file__).parent / "fountain_coords.json"
OUTPUT_FILE = Path(__file__).parent.parent / "docs" / "data.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def fetch_page(url: str) -> BeautifulSoup:
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def get_fountain_list(soup: BeautifulSoup) -> list[str]:
    """Extract fountain names from the select/option elements or plain text list."""
    fountains = []

    # Try select element first
    select = soup.find("select")
    if select:
        for opt in select.find_all("option"):
            name = opt.get_text(strip=True)
            if name and name.lower() not in ("", "select", "choose"):
                fountains.append(name)
        if fountains:
            return fountains

    # Fall back: look for the plain-text list of fountain names in the page body
    # (the page renders the select as plain text in some scraped versions)
    content = soup.get_text()
    # Extract lines that look like fountain names (between known first and last)
    start_marker = "Granary Square fountains"
    end_marker = "King George Recreation Ground"
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)
    if start_idx != -1 and end_idx != -1:
        block = content[start_idx : end_idx + len(end_marker) + 60]
        for line in block.split("\n"):
            line = line.strip()
            if len(line) > 5 and not line.startswith("Status") and not line.startswith("On/") and not line.startswith("Off/") and not line.startswith("Submit"):
                fountains.append(line)

    return fountains


def get_live_statuses(soup: BeautifulSoup) -> dict[str, dict]:
    """
    Parse the live table. Returns dict keyed by fountain name,
    value is {"status": "on"|"off", "reported_at": ISO string}
    Only keeps the MOST RECENT entry per fountain.
    """
    statuses = {}

    table = soup.find("table")
    if not table:
        return statuses

    rows = table.find_all("tr")
    for row in rows[1:]:  # skip header
        cols = [td.get_text(strip=True) for td in row.find_all("td")]
        if len(cols) < 3:
            continue
        name, raw_status, raw_date = cols[0], cols[1], cols[2]

        # Parse status
        if "on" in raw_status.lower() or "open" in raw_status.lower():
            status = "on"
        elif "off" in raw_status.lower() or "not open" in raw_status.lower():
            status = "off"
        else:
            continue

        # Parse date — format seen: "25/05/2026 05:06 PM"
        try:
            dt = datetime.strptime(raw_date.strip(), "%d/%m/%Y %I:%M %p")
            dt = dt.replace(tzinfo=timezone.utc)
            iso = dt.isoformat()
        except Exception:
            iso = raw_date.strip()

        # Keep only the most recent entry per fountain
        if name not in statuses:
            statuses[name] = {"status": status, "reported_at": iso}

    return statuses


def load_coords() -> dict[str, dict]:
    """Load hardcoded coordinates from JSON file."""
    if not COORDS_FILE.exists():
        print(f"WARNING: coords file not found at {COORDS_FILE}", file=sys.stderr)
        return {}
    with open(COORDS_FILE) as f:
        data = json.load(f)
    return {item["name"]: {"lat": item["lat"], "lon": item["lon"]} for item in data}


def main():
    print("Fetching fountain list...")
    try:
        sub_soup = fetch_page(SUBMISSIONS_URL)
        fountain_list = get_fountain_list(sub_soup)
        print(f"  Found {len(fountain_list)} fountains in list")
    except Exception as e:
        print(f"ERROR fetching fountain list: {e}", file=sys.stderr)
        fountain_list = []

    print("Fetching live statuses...")
    try:
        live_soup = fetch_page(LIVE_URL)
        statuses = get_live_statuses(live_soup)
        print(f"  Found statuses for {len(statuses)} fountains")
    except Exception as e:
        print(f"ERROR fetching live statuses: {e}", file=sys.stderr)
        statuses = {}

    coords = load_coords()

    # If we couldn't scrape the fountain list, fall back to coords keys
    if not fountain_list:
        fountain_list = list(coords.keys())

    # Build output
    fountains_out = []
    for name in fountain_list:
        coord = coords.get(name, {})
        status_info = statuses.get(name, {})
        fountains_out.append({
            "name": name,
            "lat": coord.get("lat"),
            "lon": coord.get("lon"),
            "status": status_info.get("status", "unknown"),
            "reported_at": status_info.get("reported_at"),
        })

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "fountains": fountains_out,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Written to {OUTPUT_FILE}")
    on_count = sum(1 for f in fountains_out if f["status"] == "on")
    off_count = sum(1 for f in fountains_out if f["status"] == "off")
    unknown_count = sum(1 for f in fountains_out if f["status"] == "unknown")
    print(f"  On: {on_count}, Off: {off_count}, No data: {unknown_count}")


if __name__ == "__main__":
    main()
