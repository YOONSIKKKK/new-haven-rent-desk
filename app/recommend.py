"""Rank the whole snapshot against one person's constraints.

Deliberately contains no model call at all. Running the three agents over 152
listings would cost roughly thirty cents and several minutes to answer a
question that is arithmetic: given this budget, this household and this place
you have to get to every morning, which of these apartments are worth opening?

So the ranking reuses the same deterministic machinery the full evaluation
uses - the census utility measurement, the twelve-month simulation, the fair
price comparison - and the model is spent only on the listing the person
actually clicks.

The ranking is also, for the same reason, instant, free, and identical on every
run with the same inputs.
"""
from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from . import data_store as store
from . import tools
from .config import DATA_DIR
from .models import (
    Destination,
    ParsedListing,
    Recommendation,
    RecommendationResult,
    RenterProfile,
)

GEOCODER = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

# New Haven is flat and walkable; these are ordinary urban speeds, and the UI
# labels the result as an estimate from a straight line, not a routed walk.
WALK_KMH = 4.8
BIKE_KMH = 14.0
# Streets are not straight lines. A modest detour factor keeps the estimate
# honest without pretending to be a routing engine.
DETOUR_FACTOR = 1.25


@lru_cache(maxsize=1)
def quick_picks() -> list[dict]:
    path = DATA_DIR / "destinations.json"
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["destinations"]


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).strip()


def resolve_destination(text: str) -> tuple[Destination | None, str | None]:
    """Turn whatever the user typed into coordinates.

    Quick picks first, because they are free and cover most people. Then the
    Census geocoder, which needs no API key - important, because the app is
    only allowed to require PORTKEY_API_KEY.
    """
    query = (text or "").strip()
    if not query:
        return None, "Enter the address you need to get to every day."

    target = _normalise(query)
    for place in quick_picks():
        label = _normalise(place["label"])
        if target == label or target in label or label in target:
            return Destination(
                label=place["label"], address=place["address"],
                lat=place["lat"], lng=place["lng"],
                resolved_by="quick_pick", matched_address=place.get("matched_address"),
            ), None

    params = urlencode({
        "address": query, "benchmark": "Public_AR_Current", "format": "json",
    })
    try:
        with urlopen(f"{GEOCODER}?{params}", timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (URLError, json.JSONDecodeError, TimeoutError, OSError):
        return None, (
            "Could not reach the address lookup service. Pick one of the suggested "
            "destinations instead - those work without a network call."
        )

    matches = data.get("result", {}).get("addressMatches") or []
    if not matches:
        return None, (
            f'No address matched "{query}". Try including the street number and '
            '"New Haven, CT".'
        )

    coords = matches[0]["coordinates"]
    return Destination(
        label=query, address=query, lat=coords["y"], lng=coords["x"],
        resolved_by="geocoder", matched_address=matches[0]["matchedAddress"],
    ), None


def distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def listing_to_parsed(row: dict) -> ParsedListing:
    """Snapshot record -> the same structure the intake agent produces.

    Only fields the snapshot actually states are filled; everything else is
    named in unknown_fields exactly as it would be for a pasted advertisement,
    so a ranked listing carries the same honesty as an evaluated one.
    """
    features = row.get("property_features") or {}
    unit_features = " ".join(row.get("unit_features") or []).lower()

    if "in unit" in unit_features or "washer" in unit_features or "dryer" in unit_features:
        laundry = "in_unit"
    elif features.get("on-site-laundry") or "laundry" in unit_features:
        laundry = "on_site"
    else:
        laundry = "unknown"

    if features.get("parking") or row.get("parking_allowed"):
        parking = "included"
    else:
        parking = "unknown"

    floorplans = row.get("floorplans") or []
    square_feet = next((f.get("sq_footage") for f in floorplans if f.get("sq_footage")), None)
    deposit = next((f.get("security_deposit") for f in floorplans if f.get("security_deposit")), None)

    unknown = []
    if square_feet is None:
        unknown.append("square_feet")
    if deposit is None:
        unknown.append("security_deposit_text")
    if not row.get("utilities_included"):
        unknown.append("utilities_included")
    if laundry == "unknown":
        unknown.append("laundry")
    if not features.get("furnished"):
        unknown.append("furnished")
    unknown += ["floor", "lease_length_months", "broker_fee_text"]

    return ParsedListing(
        address=row.get("address"),
        bedrooms=row.get("bed_min"),
        asking_rent_usd=row.get("rent_min"),
        # Ten listings in the snapshot are priced per person, not per unit. Read
        # as whole-unit rents they look like bargains and dominate any ranking.
        rent_is_per_person=(row.get("rent_style") == "person") or None,
        utilities_included=row.get("utilities_included") or [],
        laundry=laundry,
        parking=parking,
        furnished=bool(features.get("furnished")) or None,
        square_feet=square_feet,
        security_deposit_text=deposit,
        unknown_fields=unknown,
    )


def _commute_minutes(km: float, kmh: float) -> int:
    return max(1, round(km * DETOUR_FACTOR / kmh * 60))


def score_listing(
    listing: ParsedListing,
    profile: RenterProfile,
    cost,
    fair,
    walk_minutes: int | None,
) -> tuple[int, list[str], list[str]]:
    """Rank on what the person said matters, and say why out loud.

    Returns (score, reasons it ranked well, warnings). A reason the user cannot
    read is a ranking they cannot trust, so every adjustment produces text.
    """
    score = 60.0
    reasons: list[str] = []
    warnings: list[str] = []

    # --- budget, against the real monthly cost rather than the advertised rent
    if profile.monthly_budget_usd and cost.monthly_total_usd:
        budget = profile.monthly_budget_usd
        over = cost.monthly_total_usd - budget
        if over <= 0:
            headroom = -over
            score += min(24, 10 + headroom / budget * 60)
            reasons.append(
                f"${cost.monthly_total_usd:,.0f}/mo all in, ${headroom:,.0f} under your budget"
            )
        else:
            score -= min(45, over / budget * 110)
            warnings.append(
                f"${over:,.0f}/mo over budget once utilities and the rest are counted "
                f"(advertised rent alone is ${cost.monthly_rent_usd:,.0f})"
            )

    # --- value for money against the census baseline for that tract
    if fair.delta_pct is not None:
        # The rule file's own judgement, applied here rather than only after the
        # fact: a listing far under the local baseline is more often a bad
        # record or a bad actor than a bargain, and a ranking that rewards it
        # puts exactly the wrong thing on top. Same -35% threshold as
        # SCAM-PRICE-TOO-GOOD in data/ct_rental_rules.json.
        if fair.delta_pct < -35:
            score -= 10
            warnings.append(
                f"{abs(fair.delta_pct):.0f}% below the local baseline - too far below to "
                "take at face value. Often a per-room price quoted as whole-unit rent, "
                "a stale record, or a listing that is not what it claims"
            )
        elif fair.delta_pct <= -10:
            score += 12
            reasons.append(f"{abs(fair.delta_pct):.0f}% below the local baseline for this tract")
        elif fair.delta_pct >= 20:
            score -= 12
            warnings.append(f"{fair.delta_pct:.0f}% above the local baseline for this tract")
        elif fair.delta_pct >= 10:
            score -= 5
            warnings.append(f"{fair.delta_pct:.0f}% above the local baseline")
        else:
            reasons.append("priced about level with the neighbourhood")

    # --- the commute they actually have
    if walk_minutes is not None:
        limit = profile.max_walk_minutes
        if limit and walk_minutes <= limit:
            score += min(12, (limit - walk_minutes) * 0.8 + 4)
            reasons.append(f"about {walk_minutes} min on foot to your destination")
        elif limit:
            score -= min(22, (walk_minutes - limit) * 1.2)
            warnings.append(
                f"about {walk_minutes} min on foot, past the {limit} min you set"
            )
        else:
            reasons.append(f"about {walk_minutes} min on foot to your destination")
        if walk_minutes > 25 and not profile.has_car:
            warnings.append("a long walk in a New Haven winter, and you said no car")

    # --- hard requirements
    if listing.bedrooms is not None and profile.household_size:
        if listing.bedrooms >= profile.household_size:
            # Spare bedrooms are not a benefit you were looking for; they are
            # rent you pay for rooms you do not use. Neither reward nor punish.
            if listing.bedrooms >= profile.household_size + 2:
                warnings.append(
                    f"{listing.bedrooms} bedrooms for {profile.household_size} - "
                    "usually a shared house, so the price may be per room"
                )
        else:
            score -= 20
            warnings.append(
                f"{listing.bedrooms} bedroom(s) for {profile.household_size} people"
            )

    if profile.needs_in_unit_laundry:
        if listing.laundry == "in_unit":
            score += 8
            reasons.append("in-unit laundry")
        elif listing.laundry == "on_site":
            score -= 6
            warnings.append("laundry is on-site, not in the unit")
        else:
            score -= 8
            warnings.append("the listing never says where the laundry is")

    if profile.needs_furnished:
        if listing.furnished:
            score += 8
            reasons.append("furnished")
        else:
            score -= 12
            warnings.append("not stated as furnished")

    # --- the calendar trap
    if cost.gap_months:
        score -= min(14, cost.gap_months * 6)
        warnings.append(
            f"standard June lease means about {cost.gap_months} month(s) of rent "
            f"before you arrive"
        )

    # --- how much of this is actually known
    unknowns = len(listing.unknown_fields)
    if unknowns >= 7:
        score -= 6
        warnings.append(f"the advertisement leaves {unknowns} facts unstated")
    elif unknowns <= 3:
        score += 4
        reasons.append("unusually complete advertisement")

    return int(max(0, min(100, round(score)))), reasons, warnings


def recommend(
    profile: RenterProfile,
    destination_text: str,
    limit: int = 12,
    max_rent: int | None = None,
    min_bedrooms: int | None = None,
) -> RecommendationResult:
    destination, error = resolve_destination(destination_text)

    note = (
        "Ranked by arithmetic, not by a model: census utility measurement for each "
        "listing's own tract, the twelve-month simulation, the fair-price comparison, "
        "and your own constraints. Walking times are straight-line distance with a "
        "detour allowance, not a routed walk. Open a listing to run the full analysis."
    )

    if destination is None:
        return RecommendationResult(
            destination=None, destination_error=error, considered=0, returned=0,
            method_note=note,
        )

    results: list[Recommendation] = []
    considered = 0

    for row in store.listings():
        if not row.get("rent_min"):
            continue
        if max_rent and row["rent_min"] > max_rent:
            continue
        if min_bedrooms is not None and (row.get("bed_max") or 0) < min_bedrooms:
            continue
        considered += 1

        listing = listing_to_parsed(row)
        tract = row.get("census_tract")

        utilities, _, _ = tools.estimate_tenant_utilities(listing.utilities_included, tract)
        fair = tools.assess_fair_price(listing, tract, utilities)
        cost = tools.simulate_cost(listing, profile, tract)

        km = walk = bike = None
        if row.get("lat") and row.get("lng"):
            km = round(distance_km(row["lat"], row["lng"], destination.lat, destination.lng), 2)
            walk = _commute_minutes(km, WALK_KMH)
            bike = _commute_minutes(km, BIKE_KMH)

        score, reasons, warnings = score_listing(listing, profile, cost, fair, walk)

        results.append(Recommendation(
            listing_id=row["id"],
            address=row.get("address") or "",
            bedrooms_min=row.get("bed_min"),
            bedrooms_max=row.get("bed_max"),
            advertised_rent_usd=row.get("rent_min"),
            utilities_tenant_pays_usd=round(utilities, 2),
            real_monthly_usd=cost.monthly_total_usd,
            first_year_total_usd=cost.first_year_total_usd,
            fair_price_delta_pct=fair.delta_pct,
            fair_price_verdict=fair.verdict,
            distance_km=km,
            walk_minutes=walk,
            bike_minutes=bike,
            score=score,
            within_budget=bool(
                profile.monthly_budget_usd
                and cost.monthly_total_usd <= profile.monthly_budget_usd
            ),
            reasons=reasons[:4],
            warnings=warnings[:4],
            unknown_count=len(listing.unknown_fields),
        ))

    results.sort(key=lambda r: (-r.score, r.real_monthly_usd or 1e9))
    top = results[:limit]

    return RecommendationResult(
        destination=destination,
        considered=considered,
        returned=len(top),
        recommendations=top,
        method_note=note,
    )
