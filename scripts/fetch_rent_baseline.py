"""Build-time script: download public Census ACS rent data for New Haven.

Writes data/rent_baseline.json, which IS committed to the repo so the running
app needs no key other than PORTKEY_API_KEY and works with no internet.

Run once:  .venv/Scripts/python.exe scripts/fetch_rent_baseline.py
"""
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

KEY = os.environ.get("CENSUS_API_KEY")
if not KEY:
    sys.exit("CENSUS_API_KEY missing from .env (build-time only)")

YEAR = 2023
BASE = f"https://api.census.gov/data/{YEAR}/acs/acs5"

# B25064_001E  median GROSS rent   (rent + utilities)
# B25058_001E  median CONTRACT rent (rent only)
#   gross - contract = implied monthly utility cost  <- powers the cost simulator
# B25031_002E..007E  median gross rent by bedroom count (studio -> 5+)
VARS = [
    "NAME",
    "B25064_001E",
    "B25058_001E",
    "B25031_002E", "B25031_003E", "B25031_004E",
    "B25031_005E", "B25031_006E", "B25031_007E",
]
BEDROOM_LABELS = {
    "B25031_002E": "studio", "B25031_003E": "1br", "B25031_004E": "2br",
    "B25031_005E": "3br", "B25031_006E": "4br", "B25031_007E": "5br_plus",
}
NULLS = {None, "", "-666666666", "-999999999", "-222222222"}


def fetch(geo_for, geo_in=None):
    params = {"get": ",".join(VARS), "for": geo_for, "key": KEY}
    if geo_in:
        params["in"] = geo_in
    url = f"{BASE}?{urlencode(params)}"
    with urlopen(url, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def num(v):
    return None if v in NULLS else int(v)


def shape(rows):
    hdr, body = rows[0], rows[1:]
    out = []
    for r in body:
        rec = dict(zip(hdr, r))
        gross = num(rec["B25064_001E"])
        contract = num(rec["B25058_001E"])
        out.append({
            "name": rec["NAME"],
            "tract": rec.get("tract"),
            "median_gross_rent": gross,
            "median_contract_rent": contract,
            "implied_monthly_utilities": (
                gross - contract if gross is not None and contract is not None else None
            ),
            "median_gross_rent_by_bedrooms": {
                label: num(rec[code]) for code, label in BEDROOM_LABELS.items()
            },
        })
    return out


print("Fetching South Central CT Planning Region tracts...")
tracts = shape(fetch("tract:*", "state:09 county:170"))
print("Fetching New Haven city (place)...")
city = shape(fetch("place:52000", "state:09"))
print("Fetching planning region total...")
county = shape(fetch("county:170", "state:09"))

with_rent = [t for t in tracts if t["median_gross_rent"] is not None]
with_util = [t for t in with_rent if t["implied_monthly_utilities"] is not None]

payload = {
    "source": "U.S. Census Bureau, American Community Survey 5-Year Estimates",
    "vintage": YEAR,
    "geography_note": (
        "Connecticut replaced counties with Planning Regions as census "
        "county-equivalents starting with 2022 ACS. New Haven sits in the "
        "South Central Connecticut Planning Region (state 09, county 170)."
    ),
    "tables": {
        "B25064": "Median gross rent (contract rent + utilities)",
        "B25058": "Median contract rent (rent only)",
        "B25031": "Median gross rent by number of bedrooms",
    },
    "note": "implied_monthly_utilities = median_gross_rent - median_contract_rent",
    "city": city[0] if city else None,
    "planning_region": county[0] if county else None,
    "tracts": with_rent,
}

out_path = ROOT / "data" / "rent_baseline.json"
out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

print()
print(f"tracts returned         : {len(tracts)}")
print(f"tracts with rent data   : {len(with_rent)}")
print(f"tracts with utility calc: {len(with_util)}")
if city:
    c = city[0]
    print()
    print("New Haven city:")
    print(f"  median gross rent    : ${c['median_gross_rent']}")
    print(f"  median contract rent : ${c['median_contract_rent']}")
    print(f"  implied utilities/mo : ${c['implied_monthly_utilities']}")
    print(f"  by bedrooms          : {c['median_gross_rent_by_bedrooms']}")
if with_util:
    u = sorted(t["implied_monthly_utilities"] for t in with_util)
    print()
    print(f"utility cost across tracts: min ${u[0]}  median ${u[len(u)//2]}  max ${u[-1]}")
print()
print(f"wrote {out_path.relative_to(ROOT)} ({out_path.stat().st_size:,} bytes)")
