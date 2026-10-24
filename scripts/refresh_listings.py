"""Refresh the listing snapshot, keeping what changed.

A rental market is not a static dataset. Listings appear, prices move, and
apartments get taken. A snapshot captured once is already wrong a week later,
and silently overwriting it throws away the single most useful signal a renter
has: that this place has been sitting unrented for a month, or that its price
just dropped.

So this does not overwrite. It diffs:

    new        in the source, not in ours        -> added, geocoded
    changed    price moved                       -> updated, old price kept
    gone       in ours, not in the source        -> marked inactive, not deleted
    unchanged  still there at the same price     -> last_seen bumped

Every observation is appended to data/listing_history.json, so "advertised at
$1,800 since June, now $1,650" becomes answerable.

Safety: if the fetch fails or returns implausibly few listings, nothing is
written. A refresh that cannot see the market must not conclude the market is
empty.

Run it manually, or on a schedule:

    .venv/Scripts/python.exe scripts/refresh_listings.py
    .venv/Scripts/python.exe scripts/refresh_listings.py --dry-run
"""
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_listings import extract_properties, fetch, normalise, URL  # noqa: E402
from geocode_listings import lookup_tract  # noqa: E402

LISTINGS = ROOT / "data" / "listings.json"
HISTORY = ROOT / "data" / "listing_history.json"
LOG = ROOT / "output" / "refresh_log.json"

# If a fetch returns fewer than this, assume the source broke rather than that
# New Haven emptied out. Tuned well below the ~150 normally present.
MIN_PLAUSIBLE = 40


def load_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def rent_of(record: dict):
    return record.get("rent_min")


def refresh(dry_run: bool = False) -> dict:
    today = date.today().isoformat()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    existing_payload = load_json(LISTINGS, {"listings": []})
    existing = {r["id"]: r for r in existing_payload.get("listings", []) if r.get("id")}
    history = load_json(HISTORY, {"observations": {}})
    observations = history.setdefault("observations", {})

    print(f"Fetching {URL} ...")
    html = fetch(URL)
    incoming = [normalise(p) for p in extract_properties(html)]
    incoming = {r["id"]: r for r in incoming if r.get("id") and (r.get("rent_min") or r.get("floorplans"))}
    print(f"  source has {len(incoming)} listings; we hold {len(existing)}")

    if len(incoming) < MIN_PLAUSIBLE:
        raise SystemExit(
            f"Refusing to refresh: the source returned only {len(incoming)} listings, "
            f"below the plausibility floor of {MIN_PLAUSIBLE}. Nothing was written."
        )

    added, changed, gone, unchanged = [], [], [], []
    merged: dict[int, dict] = {}

    for listing_id, fresh_record in incoming.items():
        old = existing.get(listing_id)
        record = dict(fresh_record)

        if old is None:
            record["first_seen"] = today
            record["last_seen"] = today
            record["status"] = "active"
            added.append(record)
        else:
            # Keep the geocoding; it costs a network call per listing and the
            # address has not moved.
            for key in ("census_tract", "census_geoid", "census_tract_name"):
                if old.get(key) is not None:
                    record[key] = old[key]
            record["first_seen"] = old.get("first_seen", old.get("captured_at", today))
            record["last_seen"] = today
            record["status"] = "active"

            before, after = rent_of(old), rent_of(record)
            if before is not None and after is not None and before != after:
                record["previous_rent_usd"] = before
                record["rent_change_usd"] = after - before
                record["rent_changed_on"] = today
                changed.append({"id": listing_id, "address": record.get("address"),
                                "from": before, "to": after, "delta": after - before})
            else:
                for key in ("previous_rent_usd", "rent_change_usd", "rent_changed_on"):
                    if old.get(key) is not None:
                        record[key] = old[key]
                unchanged.append(listing_id)

        merged[listing_id] = record
        observations.setdefault(str(listing_id), []).append({
            "seen": today, "rent_min": rent_of(record), "rent_max": record.get("rent_max"),
        })

    for listing_id, old in existing.items():
        if listing_id in incoming:
            continue
        record = dict(old)
        if record.get("status") != "inactive":
            record["status"] = "inactive"
            record["gone_on"] = today
            gone.append({"id": listing_id, "address": record.get("address"),
                         "last_seen": record.get("last_seen", record.get("captured_at"))})
        merged[listing_id] = record

    # Geocode only what is new. Everything else kept its tract above.
    to_locate = [r for r in merged.values() if r.get("status") == "active" and not r.get("census_tract")]
    if to_locate and not dry_run:
        print(f"  geocoding {len(to_locate)} new listing(s)...")
        for record in to_locate:
            if not (record.get("lat") and record.get("lng")):
                continue
            geo = lookup_tract(record["lat"], record["lng"])
            if geo:
                record["census_tract"] = geo["tract"]
                record["census_geoid"] = geo["geoid"]
                record["census_tract_name"] = geo["tract_name"]

    active = [r for r in merged.values() if r.get("status") == "active"]
    report = {
        "run_at": now,
        "source": URL,
        "dry_run": dry_run,
        "source_count": len(incoming),
        "held_before": len(existing),
        "added": len(added),
        "price_changed": len(changed),
        "gone": len(gone),
        "unchanged": len(unchanged),
        "active_after": len(active),
        "total_tracked": len(merged),
        "price_changes": changed[:50],
        "newly_gone": gone[:50],
        "new_listings": [{"id": r["id"], "address": r.get("address"),
                          "rent_min": r.get("rent_min")} for r in added[:50]],
    }

    if dry_run:
        print("\n  DRY RUN - nothing written\n")
    else:
        payload = dict(existing_payload)
        payload.update({
            "source": "Yale University Off-Campus Housing Marketplace (College Pads)",
            "source_url": URL,
            "captured_at": today,
            "count": len(active),
            "total_tracked": len(merged),
            "refresh_note": (
                "Refreshed by scripts/refresh_listings.py. Listings no longer in the "
                "source are kept with status 'inactive' rather than deleted, so a "
                "disappearance is itself a recorded fact."
            ),
            "listings": sorted(merged.values(), key=lambda r: (r.get("status") != "active", r["id"])),
        })
        LISTINGS.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

        history["updated_at"] = now
        history["note"] = (
            "One row per listing per refresh. Lets the app answer 'how long has this "
            "been advertised' and 'has the price moved', which no listing site shows."
        )
        HISTORY.write_text(json.dumps(history, indent=2), encoding="utf-8")

        LOG.parent.mkdir(parents=True, exist_ok=True)
        log = load_json(LOG, {"runs": []})
        log.setdefault("runs", []).append({k: v for k, v in report.items()
                                           if k not in ("price_changes", "newly_gone", "new_listings")})
        log["runs"] = log["runs"][-60:]
        LOG.write_text(json.dumps(log, indent=2), encoding="utf-8")

    print(f"{'':<4}{'added':>8}{'changed':>10}{'gone':>8}{'unchanged':>12}{'active':>9}")
    print("-" * 51)
    print(f"{'':<4}{len(added):>8}{len(changed):>10}{len(gone):>8}{len(unchanged):>12}{len(active):>9}")

    if changed:
        print("\nprice moves:")
        for c in changed[:10]:
            arrow = "down" if c["delta"] < 0 else "up  "
            print(f"  {arrow} ${abs(c['delta']):>5,}  {str(c['address'])[:44]}  "
                  f"${c['from']:,} -> ${c['to']:,}")
    if added:
        print("\nnew listings:")
        for r in added[:10]:
            rent = f"${r['rent_min']:,}" if r.get("rent_min") else "no price"
            print(f"  {rent:>8}  {str(r.get('address'))[:50]}")
    if gone:
        print("\nno longer advertised:")
        for g in gone[:10]:
            print(f"  {str(g['address'])[:50]}  (last seen {g['last_seen']})")

    if not dry_run:
        print(f"\nwrote {LISTINGS.relative_to(ROOT)}, {HISTORY.relative_to(ROOT)}, "
              f"{LOG.relative_to(ROOT)}")
    return report


if __name__ == "__main__":
    refresh(dry_run="--dry-run" in sys.argv)
