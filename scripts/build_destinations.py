"""Build-time script: pre-geocode the destinations people actually commute to.

The app can geocode any address the user types, through the U.S. Census
geocoder, which needs no key. This file exists for two other reasons: so the
common choices are one click rather than a typed address, and so the feature
still works when the geocoder is unreachable.

Run:  .venv/Scripts/python.exe scripts/build_destinations.py
"""
import json
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "destinations.json"
GEOCODER = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

PLACES = [
    ("Yale School of Management", "165 Whitney Ave, New Haven, CT 06511"),
    ("Yale central campus (Prospect St)", "1 Prospect St, New Haven, CT 06511"),
    ("Yale School of Medicine", "333 Cedar St, New Haven, CT 06510"),
    ("Yale Science Hill", "344 Winchester Ave, New Haven, CT 06511"),
    ("Downtown / Chapel St", "900 Chapel St, New Haven, CT 06510"),
    ("Union Station", "50 Union Ave, New Haven, CT 06519"),
]


def geocode(address: str) -> dict | None:
    query = urlencode({
        "address": address,
        "benchmark": "Public_AR_Current",
        "format": "json",
    })
    try:
        with urlopen(f"{GEOCODER}?{query}", timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (URLError, json.JSONDecodeError, TimeoutError):
        return None
    matches = data.get("result", {}).get("addressMatches") or []
    if not matches:
        return None
    coords = matches[0]["coordinates"]
    return {
        "lat": coords["y"],
        "lng": coords["x"],
        "matched_address": matches[0]["matchedAddress"],
    }


def main() -> None:
    out = []
    for label, address in PLACES:
        result = geocode(address)
        status = "ok " if result else "MISS"
        print(f"  {status} {label}")
        if result:
            out.append({"label": label, "address": address, **result})

    if not out:
        raise SystemExit("Nothing geocoded - is the network up?")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": "U.S. Census Bureau Geocoder (no API key required)",
        "note": (
            "Quick-pick destinations, pre-resolved so the common choices need no "
            "network call and the feature degrades gracefully when the geocoder "
            "is unreachable. Any other address is geocoded at request time."
        ),
        "destinations": out,
    }, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)} ({len(out)} destinations)")


if __name__ == "__main__":
    main()
