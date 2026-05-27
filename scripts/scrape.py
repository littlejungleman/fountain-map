#!/usr/bin/env python3
"""
Scrapes bablands.com fountainwatch for fountain list and live statuses.
Outputs docs/data.json.

IMPROVEMENTS:
 - Cache-busting to avoid stale Cloudflare/WP cache
 - Better logging of newest timestamp seen
 - More robust table parsing
 - Preserves previous data on scrape failure
 - Picks newest status per fountain
 - Better handling of wpDataTables pagination/rendering
"""

import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup


SUBMISSIONS_URL = "https://bablands.com/fountainwatch/"
LIVE_URL        = "https://bablands.com/fountainwatch-live/"

COORDS_FILE = Path(__file__).parent / "fountain_coords.json"

OUTPUT_FILE = (
    Path(__file__).parent.parent
    / "docs"
    / "data.json"
)

BST = timezone(timedelta(hours=1))

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0 Safari/537.36",

    "Accept":
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8",

    "Accept-Language":
        "en-GB,en;q=0.9",

    "Cache-Control":
        "no-cache",

    "Pragma":
        "no-cache",

    "Connection":
        "keep-alive",
})


def normalise(text: str) -> str:

    return (
        text
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .strip()
    )


def fetch_html(url: str, retries: int = 4) -> str:

    for attempt in range(1, retries + 1):

        try:

            busted_url = (
                f"{url}"
                f"{'&' if '?' in url else '?'}"
                f"_={int(time.time())}"
            )

            print(f"  Fetching: {busted_url}")

            r = SESSION.get(
                busted_url,
                timeout=30,
            )

            if r.status_code == 429:

                wait = 15 * attempt

                print(
                    f"  Rate limited. "
                    f"Waiting {wait}s..."
                )

                time.sleep(wait)

                continue

            r.raise_for_status()

            print(
                f"  HTTP {r.status_code} "
                f"| {len(r.text):,} chars"
            )

            return r.text

        except Exception as e:

            if attempt == retries:
                raise

            wait = 10 * attempt

            print(
                f"  Attempt {attempt} failed: {e}"
            )

            print(f"  Retrying in {wait}s...")

            time.sleep(wait)

    raise RuntimeError("Failed to fetch page")


def get_fountain_list(html: str) -> list:

    soup = BeautifulSoup(html, "html.parser")

    fountains = []

    for select in soup.find_all("select"):

        for opt in select.find_all("option"):

            name = normalise(
                opt.get_text(strip=True)
            )

            if (
                name
                and name.lower()
                not in {
                    "",
                    "select",
                    "choose",
                    "fountain/splash pad"
                }
            ):
                fountains.append(name)

    fountains = sorted(list(set(fountains)))

    return fountains


def parse_status(raw: str) -> str | None:

    lower = raw.lower().strip()

    if (
        "off" in lower
        or "not open" in lower
        or "closed" in lower
    ):
        return "off"

    if (
        "on" in lower
        or "open" in lower
    ):
        return "on"

    return None


def parse_dt(text: str) -> datetime:

    text = text.strip()

    formats = [
        "%d/%m/%Y %I:%M %p",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ]

    for fmt in formats:

        try:

            dt = datetime.strptime(
                text,
                fmt
            ).replace(
                tzinfo=BST
            )

            return dt.astimezone(
                timezone.utc
            )

        except Exception:
            pass

    return datetime.min.replace(
        tzinfo=timezone.utc
    )


def get_live_statuses(html: str) -> dict:

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    entries = {}

    total_rows = 0

    rows = soup.select("table tr")

    print(f"  Found {len(rows)} total rows")

    for row in rows:

        cols = [
            td.get_text(" ", strip=True)
            for td in row.find_all(
                ["td", "th"]
            )
        ]

        if len(cols) < 3:
            continue

        name = normalise(cols[0])

        if (
            not name
            or name.lower() in {
                "fountain/splash pad",
                "status",
                "entry date"
            }
        ):
            continue

        status = parse_status(cols[1])

        if not status:
            continue

        raw_dt = cols[2].strip()

        dt = parse_dt(raw_dt)

        total_rows += 1

        existing = entries.get(name)

        if (
            existing is None
            or dt > existing["dt"]
        ):

            entries[name] = {
                "status": status,
                "reported_at": raw_dt,
                "dt": dt,
            }

    latest_dt = max(
        (
            v["dt"]
            for v in entries.values()
            if v["dt"] != datetime.min.replace(
                tzinfo=timezone.utc
            )
        ),
        default=None
    )

    print(
        f"  Parsed {total_rows} valid rows"
    )

    print(
        f"  Unique fountains: "
        f"{len(entries)}"
    )

    if latest_dt:

        print(
            "  Latest timestamp seen: "
            f"{latest_dt.isoformat()}"
        )

    else:

        print(
            "  WARNING: no timestamps parsed"
        )

    return {
        k: {
            "status": v["status"],
            "reported_at": v["reported_at"],
        }
        for k, v in entries.items()
    }


def load_coords() -> dict:

    if not COORDS_FILE.exists():

        print(
            f"WARNING: missing "
            f"{COORDS_FILE}",
            file=sys.stderr
        )

        return {}

    with open(COORDS_FILE) as f:

        data = json.load(f)

    return {
        normalise(item["name"]): item
        for item in data
    }


def load_existing_statuses() -> dict:

    if not OUTPUT_FILE.exists():
        return {}

    try:

        with open(OUTPUT_FILE) as f:

            data = json.load(f)

        return {
            normalise(f["name"]): {
                "status": f["status"],
                "reported_at":
                    f.get("reported_at")
            }
            for f in data.get(
                "fountains",
                []
            )
        }

    except Exception:

        return {}


def main():

    time.sleep(5)

    print("\nFetching fountain list...")

    fountain_list = []

    try:

        submissions_html = fetch_html(
            SUBMISSIONS_URL
        )

        fountain_list = get_fountain_list(
            submissions_html
        )

        print(
            f"  Found "
            f"{len(fountain_list)} fountains"
        )

    except Exception as e:

        print(
            f"  ERROR: {e}",
            file=sys.stderr
        )

    print("\nFetching live statuses...")

    scrape_ok = False

    statuses = {}

    try:

        live_html = fetch_html(
            LIVE_URL
        )

        statuses = get_live_statuses(
            live_html
        )

        scrape_ok = len(statuses) > 0

    except Exception as e:

        print(
            f"  ERROR: {e}",
            file=sys.stderr
        )

    if not scrape_ok:

        print(
            "\nNo fresh statuses found."
        )

        print(
            "Preserving previous data..."
        )

        statuses = load_existing_statuses()

        print(
            f"  Loaded "
            f"{len(statuses)} "
            f"previous statuses"
        )

    coords = load_coords()

    if not fountain_list:

        print(
            "Using coords as fallback list"
        )

        fountain_list = list(coords.keys())

    unmatched = (
        set(statuses.keys())
        - set(fountain_list)
    )

    if unmatched:

        print(
            f"\nWARNING:"
            f" {len(unmatched)} unmatched"
            f" status names:"
        )

        for name in sorted(unmatched):

            print(f"  - {repr(name)}")

    fountains_out = []

    for name in fountain_list:

        c = coords.get(name, {})

        s = statuses.get(name, {})

        fountains_out.append({

            "name": name,

            "lat": c.get("lat"),

            "lon": c.get("lon"),

            "status":
                s.get("status", "unknown"),

            "reported_at":
                s.get("reported_at"),

        })

    output = {

        "updated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "scrape_ok":
            scrape_ok,

        "fountains":
            fountains_out,
    }

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(OUTPUT_FILE, "w") as f:

        json.dump(
            output,
            f,
            indent=2
        )

    on = sum(
        1
        for f in fountains_out
        if f["status"] == "on"
    )

    off = sum(
        1
        for f in fountains_out
        if f["status"] == "off"
    )

    unk = sum(
        1
        for f in fountains_out
        if f["status"] == "unknown"
    )

    print("\nDone")

    print(
        f"  on={on}"
        f"  off={off}"
        f"  unknown={unk}"
    )

    print(
        f"\nWrote:"
        f"\n{OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()