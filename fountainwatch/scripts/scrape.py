#!/usr/bin/env python3
"""
Scrapes bablands.com fountainwatch for fountain list and live statuses.
Outputs docs/data.json.

Key fixes:
 - Normalises curly apostrophes (U+2019) → straight apostrophes for consistent
   name matching between website output and coords lookup.
 - wpDataTables is server-side paginated: iterates AJAX pages until all rows fetched.
 - Checks "off" before "open" since "Off/not open" contains the word "open".
 - Picks the NEWEST status per fountain by timestamp.
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
LIVE_URL        = "https://bablands.com/fountainwatch-live/"
COORDS_FILE     = Path(__file__).parent / "fountain_coords.json"
OUTPUT_FILE     = Path(__file__).parent.parent / "docs" / "data.json"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
})


def normalise(name: str) -> str:
    """Normalise curly/fancy apostrophes and quotes to plain ASCII equivalents."""
    return (name
            .replace("\u2019", "'")   # right single quotation mark → apostrophe
            .replace("\u2018", "'")   # left single quotation mark → apostrophe
            .replace("\u201c", '"')   # left double quotation mark
            .replace("\u201d", '"')   # right double quotation mark
            .strip())


def fetch_html(url: str) -> str:
    r = SESSION.get(url, timeout=20)
    r.raise_for_status()
    return r.text


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
    """
    IMPORTANT: check 'off' BEFORE 'open' — "Off/not open" contains "open".
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


def extract_wdt_config(html: str) -> tuple[str | None, str | None]:
    """Extract wpDataTables table_id and nonce from page JavaScript."""
    table_id = None
    nonce = None

    # Patterns seen in wpDataTables page source
    for pat in [
        r'"table_id"\s*:\s*"?(\d+)"?',
        r'wpdatatable_id["\s]*:["\s]*(\d+)',
        r'var\s+wdtVar\d+\s*=\s*\{[^}]*"id"\s*:\s*(\d+)',
        r'tableId["\s]*:["\s]*(\d+)',
    ]:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            table_id = m.group(1)
            break

    for pat in [
        r'"nonce"\s*:\s*"([a-f0-9]{10})"',
        r'wdtNonce["\s]*:["\s]*"([a-f0-9]{10})"',
        r'"nonce":"([^"]+)"',
    ]:
        m = re.search(pat, html)
        if m:
            nonce = m.group(1)
            break

    return table_id, nonce


def get_live_statuses_ajax(table_id: str, nonce: str | None) -> dict:
    """
    Fetch all rows via wpDataTables / DataTables.js AJAX endpoint.
    Paginates with start=0, 100, 200... until recordsTotal is reached.
    Returns dict: normalised_name -> {status, reported_at}
    """
    ajax_url = "https://bablands.com/wp-admin/admin-ajax.php"
    entries: dict[str, dict] = {}
    page_size = 100
    start = 0
    total = None

    SESSION.headers.update({
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": LIVE_URL,
    })

    draw = 1
    while True:
        payload = {
            "action": "get_wdtable",
            "table_id": table_id,
            "draw": str(draw),
            "start": str(start),
            "length": str(page_size),
            "search[value]": "",
            "search[regex]": "false",
            "order[0][column]": "2",   # sort by Entry Date
            "order[0][dir]": "desc",   # newest first
        }
        if nonce:
            payload["wdtNonce"] = nonce

        try:
            r = SESSION.post(ajax_url, data=payload, timeout=20)
            if r.status_code != 200:
                print(f"  AJAX page start={start}: HTTP {r.status_code}", file=sys.stderr)
                break

            data = r.json()
        except Exception as e:
            print(f"  AJAX page start={start} failed: {e}", file=sys.stderr)
            break

        if total is None:
            total = data.get("recordsTotal", 0)
            print(f"  AJAX: {total} total rows")

        rows = data.get("data", [])
        if not rows:
            break

        for row in rows:
            # DataTables returns array or dict per row
            if isinstance(row, list) and len(row) >= 3:
                raw_name, raw_status, raw_date = row[0], row[1], row[2]
            elif isinstance(row, dict):
                vals = list(row.values())
                if len(vals) < 3:
                    continue
                raw_name, raw_status, raw_date = vals[0], vals[1], vals[2]
            else:
                continue

            # Strip any HTML tags
            name = normalise(re.sub(r"<[^>]+>", "", str(raw_name)).strip())
            raw_status_clean = re.sub(r"<[^>]+>", "", str(raw_status)).strip()
            raw_date_clean = re.sub(r"<[^>]+>", "", str(raw_date)).strip()

            status = parse_status(raw_status_clean)
            if not status or not name:
                continue

            dt = parse_dt(raw_date_clean)
            iso = dt.isoformat() if dt != datetime.min.replace(tzinfo=timezone.utc) else raw_date_clean

            if name not in entries or dt > entries[name]["dt"]:
                entries[name] = {"status": status, "reported_at": iso, "dt": dt}

        start += len(rows)
        draw += 1
        print(f"  AJAX: fetched {start}/{total} rows, {len(entries)} unique fountains so far")

        if total is not None and start >= total:
            break

        time.sleep(0.3)  # be polite

    return {k: {"status": v["status"], "reported_at": v["reported_at"]}
            for k, v in entries.items()}


def get_live_statuses_html(html: str) -> dict:
    """
    Fallback: parse the HTML table directly.
    wpDataTables client-side mode renders all rows in the DOM.
    """
    soup = BeautifulSoup(html, "html.parser")
    entries: dict[str, dict] = {}

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cols = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if len(cols) < 3:
                continue
            name = normalise(cols[0])
            raw_status, raw_date = cols[1].strip(), cols[2].strip()

            skip = {"fountain/splash pad", "status", "entry date", ""}
            if name.lower() in skip:
                continue

            status = parse_status(raw_status)
            if not status:
                continue

            dt = parse_dt(raw_date)
            iso = dt.isoformat() if dt != datetime.min.replace(tzinfo=timezone.utc) else raw_date

            if name not in entries or dt > entries[name]["dt"]:
                entries[name] = {"status": status, "reported_at": iso, "dt": dt}

    if entries:
        print(f"  HTML fallback: {len(entries)} unique fountains")
    return {k: {"status": v["status"], "reported_at": v["reported_at"]}
            for k, v in entries.items()}


def get_live_statuses(html: str) -> dict:
    """Try AJAX first (gets all pages), fall back to HTML parsing."""
    table_id, nonce = extract_wdt_config(html)
    print(f"  wpDataTables config: table_id={table_id}, nonce={nonce}")

    if table_id:
        statuses = get_live_statuses_ajax(table_id, nonce)
        if statuses:
            return statuses
        print("  AJAX returned no results, falling back to HTML", file=sys.stderr)

    return get_live_statuses_html(html)


def load_coords() -> dict:
    if not COORDS_FILE.exists():
        print(f"WARNING: coords file not found: {COORDS_FILE}", file=sys.stderr)
        return {}
    with open(COORDS_FILE) as f:
        data = json.load(f)
    # Normalise names in coords file too, for consistent matching
    return {normalise(item["name"]): item for item in data}


def main():
    # Warm up session with homepage first (helps with some WAF setups)
    try:
        SESSION.get("https://bablands.com/", timeout=10)
    except Exception:
        pass

    print("Fetching fountain list...")
    fountain_list = []
    try:
        fountain_list = get_fountain_list(fetch_html(SUBMISSIONS_URL))
        print(f"  {len(fountain_list)} fountains found")
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)

    print("Fetching live statuses...")
    statuses = {}
    try:
        live_html = fetch_html(LIVE_URL)
        statuses = get_live_statuses(live_html)
        print(f"  {len(statuses)} fountains with status")
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)

    coords = load_coords()

    if not fountain_list:
        print("  Using coords file as fountain list fallback")
        fountain_list = list(coords.keys())

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

    # Warn about any unmatched names (helps catch new fountains)
    unmatched = [f["name"] for f in fountains_out if f["lat"] is None]
    if unmatched:
        print(f"\n  WARNING: {len(unmatched)} fountains have no coordinates:")
        for u in unmatched:
            print(f"    - {repr(u)}")

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
