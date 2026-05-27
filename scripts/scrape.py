#!/usr/bin/env python3
"""
Scrape latest fountain statuses from bablands.com
and write docs/data.json

Keeps original UK date strings for popup display.
Includes cache busting to avoid stale data.
"""

import json
import time
from pathlib import Path
from datetime import datetime

import requests
from bs4 import BeautifulSoup


LIVE_URL = "https://bablands.com/fountainwatch-live/"
SUBMISSIONS_URL = "https://bablands.com/fountainwatch/"

BASE_DIR = Path(__file__).resolve().parent

COORDS_FILE = BASE_DIR / "fountain_coords.json"

OUTPUT_FILE = (
    BASE_DIR.parent
    / "docs"
    / "data.json"
)

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent":
        "Mozilla/5.0",
    "Cache-Control":
        "no-cache",
    "Pragma":
        "no-cache",
})


def normalise(text):

    return (
        text
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .strip()
    )


def fetch_html(url):

    busted = (
        f"{url}"
        f"{'&' if '?' in url else '?'}"
        f"_={int(time.time())}"
    )

    print(f"Fetching {busted}")

    r = SESSION.get(
        busted,
        timeout=30
    )

    r.raise_for_status()

    return r.text


def get_fountain_list(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    names = set()

    for select in soup.find_all("select"):

        for option in select.find_all("option"):

            name = normalise(
                option.get_text(strip=True)
            )

            if (
                name
                and len(name) > 3
                and "select" not in name.lower()
            ):
                names.add(name)

    return sorted(list(names))


def parse_status(text):

    t = text.lower()

    if (
        "off" in t
        or "closed" in t
        or "not open" in t
    ):
        return "off"

    if (
        "on" in t
        or "open" in t
    ):
        return "on"

    return None


def parse_dt(text):

    formats = [
        "%d/%m/%Y %I:%M %p",
        "%d/%m/%Y %H:%M",
    ]

    for fmt in formats:

        try:
            return datetime.strptime(
                text.strip(),
                fmt
            )
        except Exception:
            pass

    return datetime.min


def get_live_statuses(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    rows = soup.select("table tr")

    print(
        f"Found {len(rows)} table rows"
    )

    entries = {}

    parsed_rows = 0

    for row in rows:

        cols = [
            td.get_text(
                " ",
                strip=True
            )
            for td in row.find_all(
                ["td", "th"]
            )
        ]

        if len(cols) < 3:
            continue

        name = normalise(cols[0])

        if (
            not name
            or name.lower()
            in {
                "fountain/splash pad",
                "status",
                "entry date"
            }
        ):
            continue

        status = parse_status(cols[1])

        if not status:
            continue

        reported_at = cols[2].strip()

        dt = parse_dt(reported_at)

        parsed_rows += 1

        existing = entries.get(name)

        if (
            existing is None
            or dt > existing["dt"]
        ):

            entries[name] = {

                "status":
                    status,

                # IMPORTANT:
                # keep ORIGINAL string
                # for popup display

                "reported_at":
                    reported_at,

                "dt":
                    dt,
            }

    latest = max(
        (
            v["dt"]
            for v in entries.values()
        ),
        default=None
    )

    print(
        f"Parsed {parsed_rows} rows"
    )

    print(
        f"Unique fountains: "
        f"{len(entries)}"
    )

    if latest:

        print(
            "Latest row timestamp: "
            f"{latest}"
        )

    return {

        name: {

            "status":
                data["status"],

            # IMPORTANT:
            # preserve raw UK date string

            "reported_at":
                data["reported_at"],
        }

        for name, data
        in entries.items()
    }


def load_coords():

    with open(COORDS_FILE) as f:

        coords = json.load(f)

    return {

        normalise(item["name"]): item
        for item in coords
    }


def main():

    print("\nFetching fountain list...")

    submissions_html = fetch_html(
        SUBMISSIONS_URL
    )

    fountain_names = get_fountain_list(
        submissions_html
    )

    print(
        f"Found "
        f"{len(fountain_names)} fountains"
    )

    print("\nFetching live data...")

    live_html = fetch_html(
        LIVE_URL
    )

    statuses = get_live_statuses(
        live_html
    )

    coords = load_coords()

    fountains = []

    for name in fountain_names:

        c = coords.get(name, {})

        s = statuses.get(name, {})

        fountains.append({

            "name":
                name,

            "lat":
                c.get("lat"),

            "lon":
                c.get("lon"),

            "status":
                s.get(
                    "status",
                    "unknown"
                ),

            # IMPORTANT:
            # keep raw UK format

            "reported_at":
                s.get("reported_at"),
        })

    output = {

        "updated_at":
            datetime.utcnow().isoformat(),

        "fountains":
            fountains,
    }

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False
        )

    print(
        f"\nWrote:"
        f"\n{OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()