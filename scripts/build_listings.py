"""Build-time script: snapshot New Haven student rentals from Yale's public
off-campus housing marketplace (offcampushousing.yale.edu, powered by College Pads).

The page is a Vue app that ships its full listing data as JSON inside the HTML,
so one ordinary page request gives the whole result set. No key, no login.

Writes data/listings.json, which IS committed so the app runs offline and the
teaching staff can reproduce every number without hitting the network.

Run:  .venv/Scripts/python.exe scripts/build_listings.py
"""
import base64
import binascii
import json
import re
from datetime import date
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "listings.json"
URL = "https://offcampushousing.yale.edu/listing"
BACKSLASH = chr(92)


def fetch(url: str) -> str:
    with urlopen(url, timeout=90) as r:
        return r.read().decode("utf-8", errors="replace")


def object_start(s: str, i: int) -> int:
    """Walk backwards from i to the '{' that opens the enclosing object."""
    depth = 0
    while i >= 0:
        c = s[i]
        if c == "}":
            depth += 1
        elif c == "{":
            if depth == 0:
                return i
            depth -= 1
        i -= 1
    return -1


def object_end(s: str, i: int) -> int:
    """Forward brace-match from an opening '{', respecting string literals."""
    depth = 0
    in_string = False
    escaped = False
    while i < len(s):
        c = s[i]
        if in_string:
            if escaped:
                escaped = False
            elif c == BACKSLASH:
                escaped = True
            elif c == '"':
                in_string = False
        else:
            if c == '"':
                in_string = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return i + 1
        i += 1
    return -1


def extract_properties(html: str) -> list[dict]:
    anchor = '"floorplans":' + "["
    starts = sorted({object_start(html, m.start()) for m in re.finditer(re.escape(anchor), html)})
    out = []
    for s in starts:
        if s == -1:
            continue
        e = object_end(html, s)
        if e == -1:
            continue
        try:
            out.append(json.loads(html[s:e]))
        except json.JSONDecodeError:
            continue
    return out


def strip_html(text) -> str:
    if not text:
        return ""
    t = re.sub(r"<(br|/p|/div|/li)[^>]*>", "\n", str(text), flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&rsquo;", "'"), ("&lsquo;", "'"),
                 ("&ldquo;", '"'), ("&rdquo;", '"'), ("&#39;", "'"), ("&quot;", '"'),
                 ("&ndash;", "-"), ("&mdash;", "-")]:
        t = t.replace(a, b)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


def decode_description(raw) -> str:
    """Descriptions ship base64-encoded; fall back to the raw value if not."""
    if not raw:
        return ""
    s = str(raw).strip()
    if re.fullmatch(r"[A-Za-z0-9+/=\s]{16,}", s):
        try:
            decoded = base64.b64decode(s, validate=True).decode("utf-8", errors="replace")
            if "<" in decoded or " " in decoded:
                return strip_html(decoded)
        except (binascii.Error, ValueError):
            pass
    return strip_html(s)


def utility_list(p: dict) -> list[str]:
    """`utilities` ships as a list for some properties and as an index-keyed
    dict ({"0": "Heat Included", "2": "Gas", ...}) for others. Normalise both,
    and fall back to features["Utilities"] when the top-level field is absent.
    """
    raw = p.get("utilities")
    if isinstance(raw, dict):
        values = list(raw.values())
    elif isinstance(raw, list):
        values = list(raw)
    else:
        values = []
    if not values:
        features = p.get("features")
        if isinstance(features, dict):
            values = list(features.get("Utilities") or [])
    seen, out = set(), []
    for v in values:
        v = str(v).strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


def as_int(v):
    try:
        return int(float(str(v).replace(",", "").replace("$", "")))
    except (TypeError, ValueError):
        return None


def walk_minutes(p) -> int | None:
    m = re.search(r"(\d+)", str(p.get("distance") or ""))
    return int(m.group(1)) if m else None


def build_ad_text(rec: dict) -> str:
    """The messy, human-readable blob the parsing agent is asked to read.

    Deliberately assembled the way a real ad reads - abbreviations, missing
    fields, utilities named inconsistently - so parsing accuracy means something.
    """
    bits = [rec["address"]]
    fp = rec["floorplans"]
    if fp:
        parts = []
        for f in fp:
            bed = f"{f['bed']}BR" if f.get("bed") else "?BR"
            bath = f"/{f['bath']}BA" if f.get("bath") else ""
            rent = f" ${f['rent_min']:,}" if f.get("rent_min") else ""
            parts.append(f"{bed}{bath}{rent}")
        bits.append(", ".join(parts) + "/mo")
    if rec["utilities_included"]:
        bits.append("Included: " + ", ".join(rec["utilities_included"]))
    else:
        bits.append("Utilities not listed")
    feats = [k.replace("-", " ") for k, v in rec["property_features"].items() if v]
    if feats:
        bits.append("Features: " + ", ".join(feats))
    if rec["walk_minutes_to_campus"] is not None:
        bits.append(f"{rec['walk_minutes_to_campus']} min {rec['distance_mode']} to campus")
    if rec["description_text"]:
        bits.append(rec["description_text"][:600])
    return ". ".join(b for b in bits if b)


def normalise(p: dict) -> dict:
    floorplans = []
    for f in p.get("floorplans") or []:
        floorplans.append({
            "bed": as_int(f.get("bed")),
            "bath": f.get("bath"),
            "rent_min": as_int(f.get("min_rent")) or as_int(f.get("rent")),
            "rent_max": as_int(f.get("max_rent")),
            "security_deposit": f.get("security_deposit") or None,
            "sq_footage": as_int(f.get("sq_footage")),
            "available_date": f.get("available_date"),
        })
    rec = {
        "id": p.get("id"),
        "source": "yale-offcampus-collegepads",
        "source_url": URL,
        "captured_at": date.today().isoformat(),
        "title": p.get("title"),
        "address": p.get("address"),
        "lat": p.get("lat"),
        "lng": p.get("lng"),
        "walk_minutes_to_campus": walk_minutes(p),
        "distance_mode": p.get("list_view_distance"),
        "bed_min": as_int(p.get("min_bed")),
        "bed_max": as_int(p.get("max_bed")),
        "bath_min": p.get("min_bath"),
        "bath_max": p.get("max_bath"),
        "rent_min": as_int(p.get("min_rent")),
        "rent_max": as_int(p.get("max_rent")),
        "rent_style": p.get("rent_style"),
        "floorplans": floorplans,
        "utilities_included": utility_list(p),
        "property_features": {k: bool(v) for k, v in (p.get("property_features") or {}).items()},
        "unit_features": p.get("unitFeatures") or [],
        "pets_allowed": p.get("pets_allowed"),
        "parking_allowed": p.get("parking_allowed"),
        "international_friendly": bool(p.get("international_friendly")),
        "good_neighbor": bool(p.get("good_neighbor")),
        "landlord_name": p.get("landlord_name"),
        "availability_note": p.get("available"),
        "description_text": decode_description(p.get("description")),
    }
    rec["raw_ad_text"] = build_ad_text(rec)
    return rec


def main() -> None:
    print(f"Fetching {URL} ...")
    html = fetch(URL)
    print(f"  {len(html):,} bytes")

    props = extract_properties(html)
    print(f"  {len(props)} property objects found")

    listings = [normalise(p) for p in props]
    listings = [r for r in listings if r["rent_min"] or r["floorplans"]]

    payload = {
        "source": "Yale University Off-Campus Housing Marketplace (College Pads)",
        "source_url": URL,
        "captured_at": date.today().isoformat(),
        "licence_note": (
            "Public listing page, no login required. Captured once at build time and "
            "committed so the app runs offline and results are reproducible."
        ),
        "count": len(listings),
        "listings": listings,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- coverage report: what the parsing agent will actually have to cope with
    def pct(n):
        return f"{n:3d}/{len(listings)} ({100 * n // max(1, len(listings)):2d}%)"

    print()
    print("field coverage")
    print("  rent known          ", pct(sum(1 for r in listings if r["rent_min"])))
    print("  utilities listed    ", pct(sum(1 for r in listings if r["utilities_included"])))
    print("  description present ", pct(sum(1 for r in listings if r["description_text"])))
    print("  walk time to campus ", pct(sum(1 for r in listings if r["walk_minutes_to_campus"] is not None)))
    print("  sq footage          ", pct(sum(1 for r in listings if any(f["sq_footage"] for f in r["floorplans"]))))
    print("  security deposit    ", pct(sum(1 for r in listings if any(f["security_deposit"] for f in r["floorplans"]))))
    print("  available date      ", pct(sum(1 for r in listings if any(f["available_date"] for f in r["floorplans"]))))
    print("  flagged intl-friendly", pct(sum(1 for r in listings if r["international_friendly"])))

    rents = sorted(r["rent_min"] for r in listings if r["rent_min"])
    if rents:
        print()
        print(f"asking rent: min ${rents[0]:,}  median ${rents[len(rents) // 2]:,}  max ${rents[-1]:,}")
    print()
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes, {len(listings)} listings)")


if __name__ == "__main__":
    main()
