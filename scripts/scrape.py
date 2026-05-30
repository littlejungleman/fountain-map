#!/usr/bin/env python3

import json
import re

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

    text = text.replace("&amp;", "and")
    text = text.replace("andamp;", "and")
    text = text.replace("&", "and")

    text = text.replace(",", " ")

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

    response = SESSION.get(
        url,
        headers={
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        },
        timeout=30
    )

    response.raise_for_status()

    return response.text


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

    import time

    def fetch_rows():

        url = (
            LIVE_URL +
            f"?t={int(time.time() * 1000)}"
        )

        response = SESSION.get(
            url,
            headers={
                "Cache-Control": "no-cache",
                "Pragma": "no-cache"
            },
            timeout=30
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        return soup.select(
            "#table_1 tbody tr"
        )

    print(
        f"\nFetching live table: "
        f"{LIVE_URL}"
    )

    rows1 = fetch_rows()

    print(
        f"Pass 1 rows: "
        f"{len(rows1)}"
    )

    time.sleep(2)

    rows2 = fetch_rows()

    print(
        f"Pass 2 rows: "
        f"{len(rows2)}"
    )

    rows = (
        rows2
        if len(rows2) >= len(rows1)
        else rows1
    )

    print(
        f"Using table with "
        f"{len(rows)} rows"
    )

    entries = {}

    for row in rows:

        cols = [
            td.get_text(
                " ",
                strip=True
            )
            for td in row.find_all("td")
        ]

        if len(cols) < 3:
            continue

        raw_name = cols[0]
        raw_status = cols[1]
        raw_date = cols[2]

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
        f"Unique fountains with status: "
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

    return entries

    print(
        f"\nFetching live table: "
        f"{LIVE_URL}"
    )

    response = SESSION.get(
        LIVE_URL,
        headers={
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        },
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    rows = soup.select(
        "#table_1 tbody tr"
    )

    print(
        f"HTML table returned "
        f"{len(rows)} rows"
    )

    entries = {}

    for row in rows:

        cols = [
            td.get_text(
                " ",
                strip=True
            )
            for td in row.find_all("td")
        ]

        if len(cols) < 3:
            continue

        raw_name = cols[0]
        raw_status = cols[1]
        raw_date = cols[2]

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
        f"Unique fountains with status: "
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