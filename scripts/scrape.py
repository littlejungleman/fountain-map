#!/usr/bin/env python3
"""
Scrapes bablands.com fountainwatch for fountain list and live statuses.
Outputs docs/data.json.

Approach:
 - Fetches the live page HTML and parses ALL <tr> rows from the table.
 - wpDataTables client-side mode renders every row in the DOM even when
   paginated — pagination just hides rows with CSS/JS.
 - Does NOT use the AJAX endpoint (requires WordPress auth nonce).
 - On failure, preserves the previous data.json rather than wiping to unknown.
 - Normalises curly apostrophes for consistent name matching.
 - Checks "off" before "open" (since "Off/not open" contains "open").
 - Picks the NEWEST status per fountain by timestamp.
"""

import json
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SUBMISSIONS_URL = "https://bablands.com/fountainwatch/"
LIVE_URL        = "https://bablands.com/fountainwatch-live/"
COORDS_FILE     = Path(__file__).parent / "fountain_coords.json"
OUTPUT_FILE     = Path(__file__).parent.parent / "docs" / "data.json"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "LondonFountainMap/1.0 (public hobby project; github.com/littlejungleman/london-fountain-map)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
})


def normalise(name: str) -> str:
    """Normalise curly apostrophes to straight for consistent name matching."""
    return (name
            .replace("\u2019", "'").replace("\u2018", "'")
            .replace("\u201c", '"').replace("\u201d", '"')
            .strip())


def fetch_html(url: str, retries: int = 4) -> str:
    """Fetch with retry on 429/5xx."""
    for attempt in range(1, retries + 1):
        try:
            r = SESSION.get(url, timeout=25)
            if r.status_code == 429:
                wait = 20 * attempt
                print(f"  429 rate-limited, waiting {wait}s (attempt {attempt}/{retries})...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.text
        except requests.HTTPError as e:
            if attempt == retries:
                raise
            wait = 15 * attempt
            print(f"  HTTP {e}, retrying in {wait}s...")
            time.sleep(wait)
    raise RuntimeError(f"Failed to fetch {url} after {retries} attempts")


def get_fountain_list(html: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    fountains = []
    for select in soup.find_all("select"):
        for opt in select.find_all("option"):
            name = normalise(opt.get_text(strip=True))
            if name and name.lower() not in ("", "select", "choose", "fountain/splash pad"):
                fountains.append(name)
    return fountains


def parse_status(raw: str) -> str | None:
    """Check 'off' BEFORE 'open' — 'Off/not open' contains 'open'."""
    lower = raw.lower()
    if "off" in lower or "not open" in lower or "closed" in lower:
        return "off"
    if "on" in lower or "open" in lower:
        return "on"
    return None


def parse_dt(s: str) -> datetime:
    """Parse date, treating input as BST (UTC+1) during summer season."""
    BST = timezone(timedelta(hours=1))
    for fmt in ("%d/%m/%Y %I:%M %p", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            dt_local = datetime.strptime(s.strip(), fmt).replace(tzinfo=BST)
            return dt_local.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def get_live_statuses(html: str) -> dict:
    """
    Parse all rows from the HTML table.
    wpDataTables client-side mode renders ALL rows in the DOM even when
    paginated — pagination is purely visual. We parse every <tr>.
    """
    if "fountainwatch" not in html.lower() and "wpdatatable" not in html.lower():
        print("  Page does not look like fountainwatch — may be an error page", file=sys.stderr)
        return {}

    soup = BeautifulSoup(html, "html.parser")
    entries: dict = {}
    total_rows = 0

    for table in soup.find_all("table"):
        all_trs = table.find_all("tr")
        print(f"  Table has {len(all_trs)} <tr> elements in DOM (including header)")
        for row in all_trs:
            cols = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if len(cols) < 3:
                continue
            name = normalise(cols[0])
            if name.lower() in {"fountain/splash pad", "status", "entry date", ""}:
                continue
            status = parse_status(cols[1].strip())
            if not status:
                continue
            total_rows += 1
            dt = parse_dt(cols[2].strip())
            iso = dt.isoformat() if dt != datetime.min.replace(tzinfo=timezone.utc) else cols[2].strip()
            if name not in entries or dt > entries[name]["dt"]:
                entries[name] = {"status": status, "reported_at": iso, "dt": dt}

    # Also check if wpDataTables reports a total count in the page
    total_match = re.search(r'"iTotalRecords"\s*:\s*(\d+)|"recordsTotal"\s*:\s*(\d+)|(\d+)\s+entries', html)
    if total_match:
        reported_total = next(g for g in total_match.groups() if g)
        print(f"  wpDataTables reports {reported_total} total records")
        if int(reported_total) > total_rows:
            print(f"  WARNING: only got {total_rows} rows from HTML but table has {reported_total} total — server-side pagination is hiding rows")

    print(f"  Parsed {total_rows} rows -> {len(entries)} unique fountains")
    return {k: {"status": v["status"], "reported_at": v["reported_at"]} for k, v in entries.items()}


def load_coords() -> dict:
    if not COORDS_FILE.exists():
        print(f"WARNING: coords file not found: {COORDS_FILE}", file=sys.stderr)
        return {}
    with open(COORDS_FILE) as f:
        data = json.load(f)
    return {normalise(item["name"]): item for item in data}


def load_existing_statuses() -> dict:
    """Load ALL previously saved statuses to preserve on scrape failure."""
    if not OUTPUT_FILE.exists():
        return {}
    try:
        with open(OUTPUT_FILE) as f:
            data = json.load(f)
        return {
            normalise(f["name"]): {"status": f["status"], "reported_at": f.get("reported_at")}
            for f in data.get("fountains", [])
        }
    except Exception:
        return {}


def main():
    time.sleep(5)  # polite pause

    print("Fetching fountain list...")
    fountain_list = []
    try:
        fountain_list = get_fountain_list(fetch_html(SUBMISSIONS_URL))
        print(f"  {len(fountain_list)} fountains found")
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)

    print("Fetching live statuses...")
    scrape_ok = False
    statuses = {}
    try:
        live_html = fetch_html(LIVE_URL)
        statuses = get_live_statuses(live_html)
        scrape_ok = len(statuses) > 0
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)

    if not scrape_ok:
        print("  No statuses retrieved — preserving existing data from last successful run")
        statuses = load_existing_statuses()
        print(f"  Preserved {len(statuses)} existing statuses")

    coords = load_coords()

    if not fountain_list:
        print("  Using coords file as fountain list fallback")
        fountain_list = list(coords.keys())

    # Log any status names that don't match the fountain list (name mismatch)
    unmatched_statuses = set(statuses.keys()) - set(fountain_list)
    if unmatched_statuses:
        print(f"  WARNING: {len(unmatched_statuses)} status names not in fountain list:")
        for n in sorted(unmatched_statuses):
            print(f"    {repr(n)}")

    fountains_out = []
    for name in fountain_list:
        c = coords.get(name, {})
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
        "scrape_ok": scrape_ok,
        "fountains": fountains_out,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    on  = sum(1 for f in fountains_out if f["status"] == "on")
    off = sum(1 for f in fountains_out if f["status"] == "off")
    unk = sum(1 for f in fountains_out if f["status"] == "unknown")
    flag = "" if scrape_ok else " WARNING: scrape failed — preserved previous statuses"
    print(f"\nWrote {OUTPUT_FILE}  |  on={on}  off={off}  no_data={unk}{flag}")


if __name__ == "__main__":
    main()
