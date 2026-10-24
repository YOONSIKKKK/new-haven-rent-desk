"""Build-time script: a searchable gazetteer of places people commute to.

The destination box used to know six places and ask a geocoder about everything
else. That is why it felt narrow: typing "Divinity School" worked only if
OpenStreetMap happened to carry that exact name, and typing "Sterling Memorial
Library" or "School of Architecture" did not work at all.

This builds a committed gazetteer from three sources, in descending order of
trust:

  curated   Yale's schools, libraries, residential colleges and landmarks,
            listed here by name with an address hint. Every one is resolved and
            then checked to be inside New Haven; anything that fails is
            reported and dropped rather than shipped wrong.
  osm       Everything else named in the area - parks, hospitals, museums,
            supermarkets, stations - harvested once from OpenStreetMap.
  (runtime) Anything still unmatched is geocoded live, as before.

Writes data/places.json, which the app loads at startup for instant matching
and type-ahead with no network call.

Run:  .venv/Scripts/python.exe scripts/build_places.py
"""
import json
import re
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "places.json"

UA = "NewHavenRentDesk/1.0 (MGT 409 student project; https://github.com/YOONSIKKKK/new-haven-rent-desk)"
CENSUS = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = "https://overpass-api.de/api/interpreter"

# Greater New Haven. Anything resolving outside this is a mismatch, not a place.
BBOX = (41.22, -73.05, 41.40, -72.83)   # south, west, north, east

# ---------------------------------------------------------------------------
# Curated: the names people actually type, with an address to resolve them by.
# ---------------------------------------------------------------------------
CURATED: list[tuple[str, str, str]] = [
    # Schools
    ("Yale School of Management", "165 Whitney Ave, New Haven, CT 06511", "school"),
    ("Yale Law School", "127 Wall St, New Haven, CT 06511", "school"),
    ("Yale School of Medicine", "333 Cedar St, New Haven, CT 06510", "school"),
    ("Yale School of Public Health", "60 College St, New Haven, CT 06510", "school"),
    ("Yale School of Nursing", "400 West Campus Dr, Orange, CT 06477", "school"),
    ("Yale Divinity School", "409 Prospect St, New Haven, CT 06511", "school"),
    ("Yale School of Architecture", "180 York St, New Haven, CT 06511", "school"),
    ("Yale School of Art", "1156 Chapel St, New Haven, CT 06510", "school"),
    ("Yale School of Drama", "222 York St, New Haven, CT 06511", "school"),
    ("Yale School of Music", "165 Elm St, New Haven, CT 06511", "school"),
    ("Yale School of the Environment", "195 Prospect St, New Haven, CT 06511", "school"),
    ("Yale Jackson School of Global Affairs", "55 Hillhouse Ave, New Haven, CT 06511", "school"),
    ("Yale Graduate School of Arts and Sciences", "320 York St, New Haven, CT 06511", "school"),
    ("Yale College", "344 College St, New Haven, CT 06511", "school"),

    # Health
    ("Yale Health", "55 Lock St, New Haven, CT 06511", "health"),
    ("Yale New Haven Hospital", "20 York St, New Haven, CT 06510", "health"),
    ("Smilow Cancer Hospital", "35 Park St, New Haven, CT 06519", "health"),

    # Libraries
    ("Sterling Memorial Library", "120 High St, New Haven, CT 06511", "library"),
    ("Beinecke Rare Book and Manuscript Library", "121 Wall St, New Haven, CT 06511", "library"),
    ("Bass Library", "110 Wall St, New Haven, CT 06511", "library"),
    ("Marx Science and Social Science Library", "219 Prospect St, New Haven, CT 06511", "library"),

    # Landmarks and facilities
    ("Payne Whitney Gymnasium", "70 Tower Pkwy, New Haven, CT 06511", "landmark"),
    ("Woolsey Hall", "500 College St, New Haven, CT 06511", "landmark"),
    ("Yale Peabody Museum", "170 Whitney Ave, New Haven, CT 06511", "landmark"),
    ("Yale University Art Gallery", "1111 Chapel St, New Haven, CT 06510", "landmark"),
    ("Yale Bowl", "81 Central Ave, New Haven, CT 06515", "landmark"),
    ("Ingalls Rink", "73 Sachem St, New Haven, CT 06511", "landmark"),
    ("Kline Tower", "219 Prospect St, New Haven, CT 06511", "landmark"),
    ("Yale Science Hill", "260 Whitney Ave, New Haven, CT 06511", "landmark"),
    ("Old Campus", "344 College St, New Haven, CT 06511", "landmark"),
    ("Yale West Campus", "800 West Campus Dr, Orange, CT 06477", "landmark"),

    # Residential colleges
    ("Benjamin Franklin College", "260 Prospect St, New Haven, CT 06511", "college"),
    ("Berkeley College", "205 Elm St, New Haven, CT 06511", "college"),
    ("Branford College", "74 High St, New Haven, CT 06511", "college"),
    ("Davenport College", "248 York St, New Haven, CT 06511", "college"),
    ("Ezra Stiles College", "302 York St, New Haven, CT 06511", "college"),
    ("Grace Hopper College", "189 Elm St, New Haven, CT 06511", "college"),
    ("Jonathan Edwards College", "68 High St, New Haven, CT 06511", "college"),
    ("Morse College", "304 York St, New Haven, CT 06511", "college"),
    ("Pauli Murray College", "130 Prospect St, New Haven, CT 06511", "college"),
    ("Pierson College", "261 Park St, New Haven, CT 06511", "college"),
    ("Saybrook College", "242 Elm St, New Haven, CT 06511", "college"),
    ("Silliman College", "505 College St, New Haven, CT 06511", "college"),
    ("Timothy Dwight College", "345 Temple St, New Haven, CT 06511", "college"),
    ("Trumbull College", "241 Elm St, New Haven, CT 06511", "college"),

    # Everyday destinations outside Yale
    ("Union Station", "50 Union Ave, New Haven, CT 06519", "transport"),
    ("Downtown New Haven", "900 Chapel St, New Haven, CT 06510", "area"),
    ("New Haven Green", "250 Temple St, New Haven, CT 06511", "area"),
    ("Southern Connecticut State University", "501 Crescent St, New Haven, CT 06515", "school"),
    ("Albertus Magnus College", "700 Prospect St, New Haven, CT 06511", "school"),
]

_last_osm = 0.0


def in_bbox(lat: float, lng: float) -> bool:
    s, w, n, e = BBOX
    return s <= lat <= n and w <= lng <= e


def census(address: str):
    params = urlencode({"address": address, "benchmark": "Public_AR_Current", "format": "json"})
    try:
        with urlopen(f"{CENSUS}?{params}", timeout=25) as r:
            data = json.loads(r.read().decode())
    except (URLError, json.JSONDecodeError, TimeoutError, OSError):
        return None
    m = data.get("result", {}).get("addressMatches") or []
    if not m:
        return None
    c = m[0]["coordinates"]
    return c["y"], c["x"], m[0]["matchedAddress"]


def nominatim(query: str):
    global _last_osm
    wait = 1.1 - (time.monotonic() - _last_osm)
    if wait > 0:
        time.sleep(wait)
    params = urlencode({"q": query, "format": "json", "limit": 1, "countrycodes": "us",
                        "viewbox": "-73.05,41.40,-72.83,41.22", "bounded": 1})
    try:
        with urlopen(Request(f"{NOMINATIM}?{params}", headers={"User-Agent": UA}), timeout=25) as r:
            data = json.loads(r.read().decode())
    except (URLError, json.JSONDecodeError, TimeoutError, OSError):
        return None
    finally:
        _last_osm = time.monotonic()
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"]), data[0].get("display_name", query)


def harvest_osm() -> list[dict]:
    query = """
    [out:json][timeout:120];
    (
      nwr["name"~"Yale",i](41.22,-73.05,41.40,-72.83);
      nwr["operator"~"Yale",i](41.22,-73.05,41.40,-72.83);
      nwr["amenity"~"^(university|college|library|hospital|clinic|school|theatre|museum|townhall)$"](41.22,-73.05,41.40,-72.83);
      nwr["shop"~"^(supermarket|department_store)$"](41.22,-73.05,41.40,-72.83);
      nwr["leisure"~"^(park|sports_centre|stadium)$"](41.22,-73.05,41.40,-72.83);
      nwr["railway"="station"](41.22,-73.05,41.40,-72.83);
      node["place"~"^(neighbourhood|suburb|quarter|borough)$"](41.22,-73.05,41.40,-72.83);
    );
    out center tags;
    """
    try:
        request = Request(OVERPASS, data=urlencode({"data": query}).encode(),
                          headers={"User-Agent": UA})
        with urlopen(request, timeout=180) as r:
            data = json.loads(r.read().decode())
    except (URLError, json.JSONDecodeError, TimeoutError, OSError) as exc:
        print(f"  OpenStreetMap harvest failed ({exc}); continuing with curated only")
        return []

    out = []
    for element in data.get("elements", []):
        tags = element.get("tags") or {}
        name = (tags.get("name") or "").strip()
        if not name or len(name) < 3:
            continue
        # Bare street-number names ("129 York") are noise next to real addresses.
        if re.fullmatch(r"[\d\-\s]+[A-Za-z ]{0,18}", name) and re.match(r"^\d", name):
            continue
        lat = element.get("lat") or (element.get("center") or {}).get("lat")
        lng = element.get("lon") or (element.get("center") or {}).get("lon")
        if lat is None or lng is None or not in_bbox(lat, lng):
            continue
        kind = (tags.get("place") if tags.get("place") in
                ("neighbourhood", "suburb", "quarter", "borough") else None)             or tags.get("amenity") or tags.get("leisure") or tags.get("shop")             or tags.get("railway") or "place"
        if kind in ("suburb", "quarter", "borough"):
            kind = "neighbourhood"
        out.append({"label": name, "lat": round(lat, 6), "lng": round(lng, 6),
                    "category": kind, "source": "osm"})
    return out


def main() -> None:
    print(f"Resolving {len(CURATED)} curated places...")
    curated, failed = [], []
    for label, address, category in CURATED:
        hit = census(address) or nominatim(label) or nominatim(address)
        if not hit or not in_bbox(hit[0], hit[1]):
            failed.append(label)
            continue
        curated.append({
            "label": label, "address": address,
            "lat": round(hit[0], 6), "lng": round(hit[1], 6),
            "category": category, "source": "curated", "matched_address": hit[2],
        })
    print(f"  resolved {len(curated)}, failed {len(failed)}")
    if failed:
        for name in failed:
            print(f"    DROPPED (would not resolve inside New Haven): {name}")

    print("Harvesting OpenStreetMap...")
    osm = harvest_osm()
    print(f"  {len(osm)} named places")

    seen = {re.sub(r"[^a-z0-9]", "", p["label"].lower()) for p in curated}
    merged = list(curated)
    for place in osm:
        key = re.sub(r"[^a-z0-9]", "", place["label"].lower())
        if key in seen:
            continue
        seen.add(key)
        merged.append(place)

    PRIORITY = {"curated": 0, "osm": 1}
    CATEGORY_RANK = {"neighbourhood": 0, "school": 1, "college": 1, "library": 1,
                     "health": 1, "landmark": 1, "transport": 1, "area": 1}
    merged.sort(key=lambda p: (PRIORITY[p["source"]],
                               CATEGORY_RANK.get(p["category"], 5), p["label"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "note": (
            "Searchable destinations. Curated entries are Yale's schools, libraries, "
            "residential colleges and landmarks, each resolved to coordinates at build "
            "time and checked to be inside New Haven. OSM entries add everything else "
            "named in the area. Anything not here is geocoded live at request time."
        ),
        "bbox": {"south": BBOX[0], "west": BBOX[1], "north": BBOX[2], "east": BBOX[3]},
        "sources": [
            "Curated by hand, resolved via the U.S. Census geocoder and OpenStreetMap",
            "OpenStreetMap via the Overpass API",
        ],
        "count": len(merged),
        "curated_count": len(curated),
        "places": merged,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    by_cat: dict[str, int] = {}
    for p in merged:
        by_cat[p["category"]] = by_cat.get(p["category"], 0) + 1
    print()
    print(f"wrote {OUT.relative_to(ROOT)}  -  {len(merged)} places "
          f"({len(curated)} curated, {len(merged) - len(curated)} from OSM)")
    for cat, n in sorted(by_cat.items(), key=lambda kv: -kv[1])[:10]:
        print(f"    {n:>4}  {cat}")


if __name__ == "__main__":
    main()
