#!/usr/bin/env python3

import json
import re
from pathlib import Path
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


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
        "Mozilla/5.0"
})


# -------------------------
# NORMALISE
# -------------------------

def normalise(text):

    if not text:
        return ""

    text = str(text)

    text = (
        text
        .replace("\u00a0", " ")
        .replace("\u200b", "")
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )

    # fix broken HTML entity issue

    text = text.replace("&amp;", "and")
    text = text.replace("andamp;", "and")
    text = text.replace("&", "and")

    # remove commas for consistent matching

    text = text.replace(",", " ")

    # collapse spaces

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# -------------------------
# FETCH HTML
# -------------------------

def fetch_html(url):

    print(f"\nFetching: {url}")

    r = SESSION.get(
        url,
        timeout=30
    )

    r.raise_for_status()

    return r.text


# -------------------------
# GET FOUNTAIN NAMES
# -------------------------

def get_fountain_names(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    names = set()

    for select in soup.find_all("select"):

        for option in select.find_all("option"):

            name = normalise(
                option.get_text(
                    strip=True
                )
            )

            if (
                name
                and "select" not in name.lower()
                and len(name) > 3
            ):
                names.add(name)

    return sorted(list(names))


# -------------------------
# STATUS PARSER
# -------------------------

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


# -------------------------
# DATE PARSER
# -------------------------

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


# -------------------------
# LOAD LIVE TABLE
# -------------------------

def get_live_statuses():

    print(
        f"\nOpening browser: "
        f"{LIVE_URL}"
    )

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page()

        page.goto(
            LIVE_URL,
            wait_until="networkidle",
            timeout=60000
        )

        # allow JS/DataTables to fully load

        page.wait_for_timeout(12000)

        print(
            "\nPreparing DataTable..."
        )

        # force ALL rows visible

        page.evaluate("""
        () => {

            if (
                !window.jQuery ||
                !jQuery.fn.dataTable
            ) {
                return;
            }

            const tables =
                jQuery.fn.dataTable.tables();

            if (!tables.length) {
                return;
            }

            const dt =
                jQuery(tables[0]).DataTable();

            dt.page.len(-1).draw();
        }
        """)

        page.wait_for_timeout(5000)

        print(
            "\nExtracting DataTables rows..."
        )

        rows = page.evaluate("""
        () => {

            if (
                !window.jQuery ||
                !jQuery.fn.dataTable
            ) {
                return [];
            }

            const tables =
                jQuery.fn.dataTable.tables();

            if (!tables.length) {
                return [];
            }

            const dt =
                jQuery(tables[0]).DataTable();

            return dt
                .rows()
                .data()
                .toArray();
        }
        """)

        browser.close()

    print(
        f"DataTables returned "
        f"{len(rows)} rows"
    )

    entries = {}

    for cols in rows:

        if len(cols) < 3:
            continue

        raw_name = str(cols[0]).strip()

        raw_status = str(cols[1]).strip()

        raw_date = str(cols[2]).strip()

        name = normalise(raw_name)

        status = parse_status(
            raw_status
        )

        if not status:
            continue

        dt = parse_dt(raw_date)

        existing = entries.get(name)

        if (
            existing is None
            or dt > existing["dt"]
        ):

            entries[name] = {

                "status":
                    status,

                "reported_at":
                    raw_date,

                "dt":
                    dt,
            }

    print(
        f"Unique fountains: "
        f"{len(entries)}"
    )

    recent = sorted(
        entries.items(),
        key=lambda x: x[1]["dt"],
        reverse=True
    )[:20]

    print("\nLatest rows selected:")

    for name, data in recent:

        print(
            f"{data['reported_at']} "
            f"| {name} "
            f"| {data['status']}"
        )

    print(
        "\n--- STATUS KEYS CONTAINING ELEPHANT ---"
    )

    for k in entries.keys():

        if "Elephant" in k:
            print(repr(k))

    return entries


# -------------------------
# LOAD COORDS
# -------------------------

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


# -------------------------
# MAIN
# -------------------------

def main():

    print(
        "\nFetching fountain list..."
    )

    html = fetch_html(
        SUBMISSIONS_URL
    )

    fountain_names = (
        get_fountain_names(html)
    )

    print(
        f"Found "
        f"{len(fountain_names)} fountains"
    )

    statuses = get_live_statuses()

    coords = load_coords()

    fountains = []

    no_matches = []

    for name in fountain_names:

        c = coords.get(name, {})

        s = statuses.get(name)

        if not s:
            no_matches.append(name)

        fountains.append({

            "name":
                name,

            "lat":
                c.get("lat"),

            "lon":
                c.get("lon"),

            "status":
                s["status"]
                if s else "unknown",

            "reported_at":
                s["reported_at"]
                if s else None,
        })

    if no_matches:

        print("\nNO STATUS MATCH:")

        for x in no_matches:
            print(repr(x))

    output = {

        "updated_at":
            datetime.now().strftime(
                "%d/%m/%Y, %H:%M"
            ),

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
        f"\nWrote:\n{OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()