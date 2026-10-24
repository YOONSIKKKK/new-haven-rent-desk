"""Build-time script: attach a census tract to every listing.

Uses the U.S. Census Geocoder, which needs no API key, so nothing here leaks
into the app's runtime requirements. Rewrites data/listings.json in place with
a `census_tract` field, which is what joins a listing to data/rent_baseline.json.

Note: the geocoder still reports Connecticut's *old* county FIPS (009), while
ACS 2023 reports the new Planning Region (170). The tract code itself is
unchanged between the two, so the tract is what we join on.

Run:  .venv/Scripts/python.exe scripts/geocode_listings.py
"""
import json
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
LISTINGS = ROOT / "data" / "listings.json"
BASELINE = ROOT / "data" / "rent_baseline.json"
GEOCODER = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
PAUSE_SECONDS = 0.25
RETRIES = 3


def lookup_tract(lat, lng):
    params = {
        "x": lng, "y": lat,
        "benchmark": "Public_AR_Current",
        "vintage": "Census2020_Current",
        "layers": "Census Tracts",
        "format": "json",
    }
    url = f"{GEOCODER}?{urlencode(params)}"
    for attempt in range(1, RETRIES + 1):
        try:
            with urlopen(url, timeout=45) as r:
                data = json.loads(r.read().decode("utf-8"))
            hits = data.get("result", {}).get("geographies", {}).get("Census Tracts") or []
            if not hits:
                return None
            return {
                "tract": hits[0].get("TRACT"),
                "geoid": hits[0].get("GEOID"),
                "tract_name": hits[0].get("NAME"),
            }
        except (URLError, json.JSONDecodeError, KeyError, TimeoutError):
            if attempt == RETRIES:
                return None
            time.sleep(1.5 * attempt)
    return None


def main() -> None:
    payload = json.loads(LISTINGS.read_text(encoding="utf-8"))
    listings = payload["listings"]

    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    by_tract = {t["tract"]: t for t in baseline["tracts"]}

    matched = joined = failed = 0
    for i, r in enumerate(listings, 1):
        if not (r.get("lat") and r.get("lng")):
            r["census_tract"] = None
            failed += 1
            continue
        geo = lookup_tract(r["lat"], r["lng"])
        if geo is None:
            r["census_tract"] = None
            failed += 1
        else:
            r["census_tract"] = geo["tract"]
            r["census_geoid"] = geo["geoid"]
            r["census_tract_name"] = geo["tract_name"]
            matched += 1
            if geo["tract"] in by_tract:
                joined += 1
        if i % 25 == 0 or i == len(listings):
            print(f"  {i:3d}/{len(listings)}  geocoded={matched} joined={joined} failed={failed}")
        time.sleep(PAUSE_SECONDS)

    payload["census_tract_note"] = (
        "census_tract joins to rent_baseline.json tracts. Geocoder reports the old "
        "Connecticut county FIPS (009); ACS 2023 uses Planning Region 170. Tract codes match."
    )
    LISTINGS.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print(f"geocoded        : {matched}/{len(listings)}")
    print(f"joined to ACS   : {joined}/{len(listings)}")
    print(f"failed          : {failed}/{len(listings)}")
    print(f"wrote {LISTINGS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
