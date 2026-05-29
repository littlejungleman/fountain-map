#!/usr/bin/env python3
"""
Scrape latest fountain statuses from bablands.com
and write docs/data.json

Uses:
- requests for fountain list
- Playwright for live table rendering

Handles:
- DataTables pagination
- JS-rendered rows
- Latest status per fountain

Preserves original UK date strings
for popup display.
"""

import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


LIVE_URL = (
    "https://bablands.com/"
    "fountainwatch-live/"
)

SUBMISSIONS_URL = (
    "https://bablands.com/"
    "fountainwatch/"
)

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
)

COORDS_FILE = (
    BASE_DIR
    / "fountain_coords.json"
)

OUTPUT_FILE = (
    BASE_DIR.parent
    / "docs"
    / "data.json"
)


SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent":
        "Mozilla/5.0"
})


def normalise(text):

    return (
        text
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .strip()
    )


def fetch_html_requests(url):

    print(
        f"\nFetching via requests:"
        f"\n{url}"
    )

    r = SESSION.get(
        url,
        timeout=30
    )

    r.raise_for_status()

    return r.text


def open_live_page(url):

    print(
        f"\nOpening browser:"
        f"\n{url}"
    )

    playwright = sync_playwright().start()

    browser = playwright.chromium.launch(
        headless=True
    )

    page = browser.new_page()

    page.goto(
        url,
        wait_until="networkidle",
        timeout=60000
    )

    # allow wpDataTables/js hydration

    page.wait_for_timeout(12000)

    return playwright, browser, page


def get_fountain_list(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    names = set()

    for select in soup.find_all(
        "select"
    ):

        for option in select.find_all(
            "option"
        ):

            name = normalise(
                option.get_text(
                    strip=True
                )
            )

            if (
                name
                and len(name) > 3
                and "select"
                not in name.lower()
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


def get_all_rows(page):

    print(
        "\nExtracting rows "
        "from browser..."
    )

    # force table length larger if DataTables exists

    page.evaluate("""
    () => {

        if (
            window.jQuery &&
            jQuery.fn.dataTable
        ) {

            jQuery('table').each(function(){

                try {

                    const table =
                        jQuery(this)
                        .DataTable();

                    table.page.len(1000).draw();

                } catch(e) {}

            });
        }
    }
    """)

    page.wait_for_timeout(5000)

    rows = page.evaluate("""
    () => {

        const trs = Array.from(
            document.querySelectorAll(
                'table tr'
            )
        );

        return trs.map(tr => {

            const cells = Array.from(
                tr.querySelectorAll(
                    'td,th'
                )
            );

            return cells.map(
                c => c.innerText.trim()
            );
        });
    }
    """)

    print(
        f"Browser returned "
        f"{len(rows)} rows"
    )

    return rows


def get_live_statuses(page):

    rows = get_all_rows(page)

    entries = {}

    parsed_rows = 0

    for cols in rows:

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

        status = parse_status(
            cols[1]
        )

        if not status:
            continue

        reported_at = (
            cols[2].strip()
        )

        dt = parse_dt(
            reported_at
        )

        parsed_rows += 1

        existing = entries.get(name)

        if (
            existing is None
            or dt > existing["dt"]
        ):

            entries[name] = {

                "status":
                    status,

                # preserve raw
                # UK date string

                "reported_at":
                    reported_at,

                "dt":
                    dt,
            }

    print(
        f"\nParsed "
        f"{parsed_rows} rows"
    )

    print(
        f"Unique fountains: "
        f"{len(entries)}"
    )

    recent = sorted(
        entries.items(),
        key=lambda x: x[1]["dt"],
        reverse=True
    )[:15]

    print("\nLatest rows seen:")

    for name, data in recent:

        print(
            f"  {data['reported_at']} "
            f"| {name} "
            f"| {data['status']}"
        )

    return {

        name: {

            "status":
                data["status"],

            "reported_at":
                data["reported_at"],
        }

        for name, data
        in entries.items()
    }


def load_coords():

    with open(
        COORDS_FILE,
        encoding="utf-8"
    ) as f:

        coords = json.load(f)

    return {

        normalise(item["name"]): item
        for item in coords
    }


def main():

    print(
        "\nFetching fountain list..."
    )

    submissions_html = (
        fetch_html_requests(
            SUBMISSIONS_URL
        )
    )

    fountain_names = (
        get_fountain_list(
            submissions_html
        )
    )

    print(
        f"Found "
        f"{len(fountain_names)} fountains"
    )

    print(
        "\nFetching live table..."
    )

    playwright, browser, page = (
        open_live_page(
            LIVE_URL
        )
    )

    statuses = get_live_statuses(
        page
    )

    browser.close()

    playwright.stop()

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

            # preserve original
            # UK date string

            "reported_at":
                s.get(
                    "reported_at"
                ),
        })

    output = {

        "updated_at":
    datetime.now(
        ZoneInfo("Europe/London")
    ).strftime(
        "%d/%m/%Y, %H:%M"
    )

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

    on = sum(
        1
        for f in fountains
        if f["status"] == "on"
    )

    off = sum(
        1
        for f in fountains
        if f["status"] == "off"
    )

    unknown = sum(
        1
        for f in fountains
        if f["status"] == "unknown"
    )

    print("\nDone")

    print(f"Open: {on}")
    print(f"Closed: {off}")
    print(f"Unknown: {unknown}")

    print(
        f"\nWrote:\n"
        f"{OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()