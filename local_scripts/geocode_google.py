#!/usr/bin/env python3
"""
One-time script to geocode all fountain locations using Google Maps Geocoding API.
Run this once to produce an improved fountain_coords.json, then commit it.

Usage:
    export GOOGLE_GEOCODING_API_KEY="your_key_here"
    python scripts/geocode_google.py

Google Maps Geocoding API is free for ~40,000 requests/month.
Get a key at: https://console.cloud.google.com/
Enable: Geocoding API
"""

import json
import os
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

if not API_KEY:
    raise ValueError("Missing GOOGLE_MAPS_API_KEY in .env file")

import requests

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

COORDS_FILE = BASE_DIR / "scripts" / "fountain_coords.json"

print("Saving updated file...")
print(COORDS_FILE)

# Hand-crafted search queries for each fountain.
# These are more specific than just the name and give Google's geocoder
# enough context to find the precise playground/fountain rather than 
# just the nearest road or town.
SEARCH_QUERIES = {
    "Granary Square fountains, King's Cross":                    "Granary Square fountains King's Cross London N1C",
    "Lewis Cubitt Square fountains, King's Cross":               "Lewis Cubitt Square King's Cross London N1C",
    "Rosemary Gardens water play, Islington":                    "Rosemary Gardens Southgate Road Islington London N1",
    "Highbury Fields water play, Islington":                     "Highbury Fields playground Highbury London N5",
    "Priory Park paddling pool, Hornsey":                        "Priory Park Hornsey London N8",
    "Lordship Recreation Ground paddling pool, Tottenham":       "Lordship Recreation Ground Tottenham London N17",
    "Bruce Castle Park paddling pool, Tottenham":                "Bruce Castle Park Tottenham London N17",
    "Whittington Park water play, Archway":                      "Whittington Park Archway London N19",
    "Barnard Park water play, Islington":                        "Barnard Park Copenhagen Street Islington London N1",
    "Animal Adventure water play at London Zoo, Camden Town":    "ZSL London Zoo Regent's Park Camden NW1",
    "King Square Gardens splash pad, Islington":                 "King Square Gardens Goswell Road London EC1V",
    "Gloucester Gate Playground water play, Regent's Park, Camden Town": "Gloucester Gate playground Regent's Park London NW1",
    "Parliament Hill paddling pool, Hampstead Heath":            "Parliament Hill paddling pool Hampstead Heath London NW5",
    "Queen's Park paddling pool":                                "Queen's Park paddling pool Harvist Road London NW6",
    "Union Park play fountain, Wembley":                         "Union Park Wembley Park London HA9",
    "Arena Square, Wembley Park":                                "Arena Square Wembley Park London HA9",
    "Finsbury Park splash play":                                 "Finsbury Park splash pad London N4",
    "Elthorne Park Playground water play, Hornsey":              "Elthorne Park Hornsey Rise London N19",
    "Swiss Cottage Open Space splash pad, Swiss Cottage":        "Swiss Cottage Open Space Adelaide Road London NW3",
    "Kilburn Grange Park splash pad":                            "Kilburn Grange Park London NW6",
    "Paradise Park splash pad, Islington":                       "Paradise Park Mackenzie Road Islington London N7",
    "Barking Splash Park":                                       "Barking Splash Park Barking Park Longbridge Road London IG11",
    "Victoria Park splash pool, Hackney":                        "Victoria Park paddling pool Hackney London E3",
    "Tumbling Bay water play, Queen Elizabeth Olympic Park":     "Tumbling Bay Playground Queen Elizabeth Olympic Park Stratford London E20",
    "Waterworks Fountains (West Ham Stadium), Queen Elizabeth Olympic Park": "Waterworks Fountains London Stadium Queen Elizabeth Olympic Park E20",
    "Gauging Square fountains, Wapping":                         "Gauging Square London Dock Wapping London E1W",
    "Goodman's Field fountains, Aldgate":                        "Goodman's Field Aldgate London E1",
    "The Children's Play Pavilion & Park splash pad, Mile End Park": "Children's Play Pavilion Mile End Park London E3",
    "St John at Hackney Churchyard Gardens fountains, Hackney":  "St John at Hackney Churchyard Lower Clapton Road London E8",
    "Clissold Park splash pad, Stoke Newington":                 "Clissold Park splash pad Stoke Newington London N16",
    "Aldgate Square fountains":                                  "Aldgate Square London EC3N",
    "Fellowship Square fountains, Walthamstow":                  "Fellowship Square Walthamstow London E17",
    "Stratford Park paddling pool":                              "Stratford Park Water Lane Stratford London E15",
    "Broadgate Exchange play fountains, Liverpool Street":       "Exchange Square Broadgate Liverpool Street London EC2A",
    "St Mary's Churchyard Park fountains, Elephant & Castle":    "St Mary Newington Churchyard Elephant and Castle London SE17",
    "Elephant Springs water play, Elephant & Castle":            "Elephant Park natural play area Elephant and Castle London SE17",
    "Wimbledon Sprinkler Park":                                  "Wimbledon Park Home Park Road Wimbledon London SW19",
    "Sir Joseph Hood Playing Fields paddling pool, Motspur Park": "Sir Joseph Hood Playing Fields Motspur Park London KT3",
    "Kingston Market Square fountains":                          "Market Place Kingston upon Thames Surrey KT1",
    "Danson Splash Park, Bexleyheath":                           "Danson Park splash park Bexleyheath London DA6",
    "Southwark Park splash pad, Bermondsey":                     "Southwark Park Bermondsey London SE16",
    "Brockwell Park wet play, Lambeth":                          "Brockwell Park paddling pool Herne Hill London SE24",
    "Myatt's Fields splash pad, Camberwell":                     "Myatt's Fields Park Camberwell London SE5",
    "Norwood Park water play, Gypsy Hill":                       "Norwood Park Gipsy Hill London SE27",
    "Royal Arsenal Riverside fountains, Woolwich":               "Royal Arsenal Riverside Woolwich London SE18",
    "Ruskin Park paddling pool, Denmark Hill":                   "Ruskin Park paddling pool Denmark Hill London SE5",
    "Rookery paddling pool, Streatham Common":                   "Rookery Garden Streatham Common London SW16",
    "Clapham Common splash pad":                                 "Clapham Common paddling pool London SW4",
    "North Sheen Recreation Ground paddling pool, Richmond":     "North Sheen Recreation Ground Richmond Surrey TW9",
    "Vine Road Recreation Ground paddling pool, Barnes":         "Vine Road Recreation Ground Barnes London SW13",
    "Wells Park water play, Sydenham":                           "Wells Park Sydenham London SE26",
    "Greenwich Park Playground water play":                      "Greenwich Park children's playground London SE10",
    "Peckham Rye Park water play":                               "Peckham Rye Park London SE15",
    "Beddington Park water play, Sutton":                        "Beddington Park Wallington Surrey SM6",
    "Croydon Road Recreation Ground paddling pool, Beckenham":   "Croydon Road Recreation Ground Beckenham London BR3",
    "Magic Garden water play, Hampton Court Palace":             "Magic Garden Hampton Court Palace Surrey KT8",
    "London Bridge Pier fountain":                               "London Bridge City Pier fountain London SE1",
    "Fountain Park Way fountains, Westfield, Wood Lane":         "Fountain Park Way Shepherd's Bush London W12",
    "Diana Princess of Wales Memorial Fountain, Hyde Park":      "Diana Princess of Wales Memorial Fountain Hyde Park London W2",
    "John Madejski Garden paddling pool, V&A, South Kensington": "John Madejski Garden Victoria and Albert Museum South Kensington London SW7",
    "Kensington Memorial Park water play area, Ladbroke Grove":  "Kensington Memorial Park St Mark's Road London W10",
    "Duke of York Square fountains, Chelsea":                    "Duke of York Square Chelsea London SW3",
    "Duke's Meadows paddling pool, Chiswick":                    "Duke's Meadows paddling pool Chiswick London W4",
    "Merchant Square fountains, Paddington Basin":               "Merchant Square Paddington Basin London W2",
    "Design Museum fountains, Kensington":                       "Design Museum Kensington High Street London W8",
    "London Wetland Centre water play area":                     "WWT London Wetland Centre Barnes London SW13",
    "Castlenau Recreation Ground paddling pool, Barnes":         "Castlenau Recreation Ground Barnes London SW13",
    "Bishop's Park water play, Putney":                          "Bishop's Park Fulham Palace Road Fulham London SW6",
    "Kew Gardens Children's Garden, Kew":                        "Kew Gardens Children's Garden Richmond Surrey TW9",
    "Ruislip Lido splash pad":                                   "Ruislip Lido Reservoir Road Ruislip London HA4",
    "Ravenscourt Park paddling pool, Hammersmith":               "Ravenscourt Park Hammersmith London W6",
    "Palewell Common & Fields paddling pool, East Sheen":        "Palewell Common East Sheen London SW14",
    "Edmond J Safra fountain court at Somerset House":           "Somerset House courtyard Strand London WC2R",
    "Russell Square Gardens fountain, Bloomsbury":               "Russell Square Gardens Bloomsbury London WC1B",
    "Coram's Fields paddling pool, Bloomsbury":                  "Coram's Fields 93 Guilford Street Bloomsbury London WC1N",
    "Causton Street Playground water play, Pimlico":             "Causton Street Playground Pimlico London SW1P",
    "Leicester Square fountains":                                "Leicester Square London WC2H",
    "Marylebone Green Playground water play, Regent's Park, Marylebone": "Marylebone Green Playground Regent's Park London NW1",
    "More London Riverside Fountains, London Bridge":            "More London Riverside fountains Tooley Street London SE1",
    "Jeppe Hein's Appearing Rooms, Southbank Centre":            "Southbank Centre Royal Festival Hall forecourt London SE1",
    "Swanley Park water play, Swanley, Kent":                    "Swanley Park Swanley Kent BR8",
    "The Harlow splash park, Harlow":                            "Town Park Harlow Essex CM20",
    "Walmer paddling pool, Kent":                                "Walmer paddling pool Walmer Kent CT14",
    "Stanborough Park Splashlands, Welwyn Garden City":          "Stanborough Park Welwyn Garden City Hertfordshire AL8",
    "Splash 'n' Play, Willen Lake, Milton Keynes":               "Willen Lake North splash n play Milton Keynes MK15",
    "Lakeside Shopping Centre fountains, Grays, Essex":          "Lakeside Shopping Centre Grays Essex RM20",
    "The Strand Leisure Park, Gillingham, Kent":                 "Strand Leisure Park Gillingham Kent ME7",
    "Bancroft Recreation Ground splash park, Hitchin":           "Bancroft Recreation Ground Hitchin Hertfordshire SG5",
    "Howard Park splash park, Letchworth":                       "Howard Park Letchworth Garden City Hertfordshire SG6",
    "Royston splash park, Royston":                              "Royston splash park Priory Memorial Gardens Royston Hertfordshire SG8",
    "Stoke Park paddling pool, Guildford":                       "Stoke Park Guildford Surrey GU1",
    "Cassiobury Park splash pools, Watford":                     "Cassiobury Park Watford Hertfordshire WD17",
    "Verulamium splash park, St. Alban's":                       "Verulamium Park St Albans Hertfordshire AL3",
    "King George Recreation Ground splash park, Bushey":         "King George Recreation Ground Bushey Hertfordshire WD23",
}


def geocode(query: str, api_key: str) -> tuple[float, float] | None:
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": query, "key": api_key, "region": "gb"}
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if data["status"] == "OK":
            loc = data["results"][0]["geometry"]["location"]
            return loc["lat"], loc["lng"]
        else:
            print(f"    Google status: {data['status']}", file=__import__('sys').stderr)
    except Exception as e:
        print(f"    Request error: {e}", file=__import__('sys').stderr)
    return None


def main():
    if not API_KEY:
        print("ERROR: Set GOOGLE_GEOCODING_API_KEY environment variable", file=__import__('sys').stderr)
        print("  export GOOGLE_GEOCODING_API_KEY='your_key_here'")
        __import__('sys').exit(1)

    existing = json.load(open(COORDS_FILE))
    existing_by_name = {c["name"]: c for c in existing}

    results = []
    improved = 0
    failed = []

    for name, query in SEARCH_QUERIES.items():
        print(f"Geocoding: {name[:60]}")
        coords = geocode(query, API_KEY)
        time.sleep(0.05)  # ~20 req/sec, well within free tier

        if coords:
            lat, lon = coords
            old = existing_by_name.get(name, {})
            old_lat, old_lon = old.get("lat"), old.get("lon")
            if old_lat:
                dist = ((lat - old_lat)**2 + (lon - old_lon)**2) ** 0.5 * 111000  # metres approx
                if dist > 50:
                    print(f"  MOVED {dist:.0f}m: ({old_lat:.5f},{old_lon:.5f}) → ({lat:.5f},{lon:.5f})")
                    improved += 1
            results.append({"name": name, "lat": round(lat, 5), "lon": round(lon, 5)})
        else:
            print(f"  FAILED — keeping existing coords")
            if name in existing_by_name:
                results.append(existing_by_name[name])
            failed.append(name)

    with open(COORDS_FILE, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nDone. {len(results)} fountains geocoded.")
    print(f"  Improved (moved >50m): {improved}")
    print(f"  Failed (kept existing): {len(failed)}")
    if failed:
        for f in failed:
            print(f"    - {f}")


if __name__ == "__main__":
    main()
