#!/usr/bin/env python3
"""
Scrapes bablands.com fountainwatch for fountain list and live statuses.
Outputs docs/data.json.

Key behaviours:
 - Retries on 429 with exponential backoff (up to 3 attempts).
 - If scrape fails entirely, PRESERVES existing statuses from data.json
   rather than overwriting everything with "unknown".
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
})


def normalise(name: str) -> str:
    return (name
            .replace("\u2019", "'").replace("\u2018", "'")
            .replace("\u201c", '"').replace("\u201d", '"')
            .strip())


def fetch_html(url: str, retries: int = 4) -> str:
    """Fetch URL with retry on 429/5xx. Waits progressively longer between attempts."""
    for attempt in range(1, retries + 1):
        try:
            r = SESSION.get(url, timeout=25)
            if r.status_code == 429:
                wait = 20 * attempt  # 20s, 40s, 60s, 80s
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
    # bablands.com is a UK site — times are UK local (BST=UTC+1 in summer, GMT in winter).
    # We always assume BST (UTC+1) during the splash pad season (Apr-Oct).
    # Storing as UTC means the browser will display correctly in any timezone.
    BST = timezone(timedelta(hours=1))
    for fmt in ("%d/%m/%Y %I:%M %p", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            dt_local = datetime.strptime(s.strip(), fmt).replace(tzinfo=BST)
            return dt_local.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def extract_wdt_config(html: str) -> tuple:
    table_id, nonce = None, None
    for pat in [r'"table_id"\s*:\s*"?(\d+)"?', r'wpdatatable_id["\s]*:["\s]*(\d+)', r'tableId["\s]*:["\s]*(\d+)']:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            table_id = m.group(1)
            break
    for pat in [r'"nonce"\s*:\s*"([a-f0-9]{10})"', r'wdtNonce["\s]*:["\s]*"([a-f0-9]{10})"', r'"nonce":"([^"]+)"']:
        m = re.search(pat, html)
        if m:
            nonce = m.group(1)
            break
    return table_id, nonce


def get_live_statuses_ajax(table_id: str, nonce: str | None) -> dict:
    ajax_url = "https://bablands.com/wp-admin/admin-ajax.php"
    entries: dict = {}
    page_size, start, total, draw = 100, 0, None, 1

    SESSION.headers.update({
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": LIVE_URL,
    })

    while True:
        payload = {
            "action": "get_wdtable", "table_id": table_id,
            "draw": str(draw), "start": str(start), "length": str(page_size),
            "search[value]": "", "search[regex]": "false",
            "order[0][column]": "2", "order[0][dir]": "desc",
        }
        if nonce:
            payload["wdtNonce"] = nonce

        try:
            r = SESSION.post(ajax_url, data=payload, timeout=25)
            if r.status_code == 429:
                print(f"  AJAX 429, waiting 15s...", file=sys.stderr)
                time.sleep(15)
                continue
            if r.status_code != 200:
                print(f"  AJAX HTTP {r.status_code}", file=sys.stderr)
                break
            data = r.json()
        except Exception as e:
            print(f"  AJAX failed: {e}", file=sys.stderr)
            break

        if total is None:
            total = data.get("recordsTotal", 0)
            print(f"  AJAX: {total} total rows")

        rows = data.get("data", [])
        if not rows:
            break

        for row in rows:
            if isinstance(row, list) and len(row) >= 3:
                raw_name, raw_status, raw_date = row[0], row[1], row[2]
            elif isinstance(row, dict):
                vals = list(row.values())
                if len(vals) < 3:
                    continue
                raw_name, raw_status, raw_date = vals[0], vals[1], vals[2]
            else:
                continue

            name = normalise(re.sub(r"<[^>]+>", "", str(raw_name)).strip())
            status = parse_status(re.sub(r"<[^>]+>", "", str(raw_status)).strip())
            raw_date_clean = re.sub(r"<[^>]+>", "", str(raw_date)).strip()
            if not status or not name:
                continue
            dt = parse_dt(raw_date_clean)
            iso = dt.isoformat() if dt != datetime.min.replace(tzinfo=timezone.utc) else raw_date_clean
            if name not in entries or dt > entries[name]["dt"]:
                entries[name] = {"status": status, "reported_at": iso, "dt": dt}

        start += len(rows)
        draw += 1
        print(f"  AJAX: fetched {start}/{total} rows, {len(entries)} unique")
        if total is not None and start >= total:
            break
        time.sleep(0.5)

    return {k: {"status": v["status"], "reported_at": v["reported_at"]} for k, v in entries.items()}


def get_live_statuses_html(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    entries: dict = {}
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cols = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if len(cols) < 3:
                continue
            name = normalise(cols[0])
            if name.lower() in {"fountain/splash pad", "status", "entry date", ""}:
                continue
            status = parse_status(cols[1].strip())
            if not status:
                continue
            dt = parse_dt(cols[2].strip())
            iso = dt.isoformat() if dt != datetime.min.replace(tzinfo=timezone.utc) else cols[2].strip()
            if name not in entries or dt > entries[name]["dt"]:
                entries[name] = {"status": status, "reported_at": iso, "dt": dt}
    if entries:
        print(f"  HTML fallback: {len(entries)} unique fountains")
    return {k: {"status": v["status"], "reported_at": v["reported_at"]} for k, v in entries.items()}


def get_live_statuses(html: str) -> dict:
    """
    Use AJAX only — the HTML table only contains the currently-visible page
    (~10 rows) because bablands uses server-side DataTables pagination.
    Falling back to HTML would silently drop all rows on pages 2+.
    If AJAX fails, return empty dict and let the caller preserve old data.
    """
    table_id, nonce = extract_wdt_config(html)
    print(f"  wpDataTables config: table_id={table_id}, nonce={nonce}")
    if not table_id:
        print("  Could not find table_id in page — cannot fetch statuses", file=sys.stderr)
        return {}
    statuses = get_live_statuses_ajax(table_id, nonce)
    if not statuses:
        print("  AJAX returned no rows — NOT falling back to HTML (would only get ~10 rows)", file=sys.stderr)
    return statuses


def load_coords() -> dict:
    if not COORDS_FILE.exists():
        print(f"WARNING: coords file not found: {COORDS_FILE}", file=sys.stderr)
        return {}
    with open(COORDS_FILE) as f:
        data = json.load(f)
    return {normalise(item["name"]): item for item in data}


def load_existing_statuses() -> dict:
    """
    Load ALL previously saved statuses from data.json.
    Called when scrape fails so we preserve the last known state exactly,
    including unknown — better to show stale data than wipe to unknown.
    """
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
    # Brief pause to avoid hammering the server — especially important since
    # cron-job.org now triggers this every 30 minutes
    time.sleep(3)

    # Warm up session
    try:
        SESSION.get("https://bablands.com/", timeout=15)
        time.sleep(2)
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
    scrape_ok = False
    statuses = {}
    try:
        live_html = fetch_html(LIVE_URL)
        statuses = get_live_statuses(live_html)
        print(f"  {len(statuses)} fountains with status")
        scrape_ok = True
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)

    # If scrape failed, preserve existing statuses instead of wiping to unknown
    if not scrape_ok:
        print("  Scrape failed — preserving existing statuses from last successful run")
        statuses = load_existing_statuses()
        print(f"  Loaded {len(statuses)} existing statuses")

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
    flag = "" if scrape_ok else " ⚠️ SCRAPE FAILED — preserved previous statuses"
    print(f"\nWrote {OUTPUT_FILE}  |  on={on}  off={off}  no_data={unk}{flag}")


if __name__ == "__main__":
    main()
