"""Loads the committed datasets once and hands them out.

Everything here is read from data/ on disk. No network, no key. That is what
lets the app run from a fresh clone with nothing but PORTKEY_API_KEY.
"""
from __future__ import annotations

import json
from functools import lru_cache

from .config import DATA_DIR


def _load(name: str) -> dict:
    path = DATA_DIR / name
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing {path}. Rebuild it with the matching script in scripts/, "
            "or restore it from the repo - it is committed on purpose."
        )
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def listings_payload() -> dict:
    return _load("listings.json")


@lru_cache(maxsize=1)
def baseline_payload() -> dict:
    return _load("rent_baseline.json")


@lru_cache(maxsize=1)
def rules() -> dict:
    return _load("ct_rental_rules.json")


@lru_cache(maxsize=1)
def assumptions() -> dict:
    return _load("cost_assumptions.json")


@lru_cache(maxsize=1)
def guide() -> dict:
    return _load("guide.json")


@lru_cache(maxsize=1)
def viewers() -> dict:
    """People offering to view an apartment on your behalf. Sample data for now."""
    return _load("viewers.json")


def listings() -> list[dict]:
    return listings_payload()["listings"]


@lru_cache(maxsize=1)
def _tract_index() -> dict[str, dict]:
    return {t["tract"]: t for t in baseline_payload()["tracts"] if t.get("tract")}


def tract(code: str | None) -> dict | None:
    """ACS record for one census tract, or None if we have no data for it."""
    if not code:
        return None
    return _tract_index().get(str(code))


def city_baseline() -> dict:
    """New Haven city-wide ACS record, used when a tract is unknown."""
    return baseline_payload()["city"]


def bedroom_key(bedrooms: int | None) -> str | None:
    """Map a bedroom count onto the ACS B25031 bucket names."""
    if bedrooms is None:
        return None
    return {0: "studio", 1: "1br", 2: "2br", 3: "3br", 4: "4br"}.get(
        bedrooms, "5br_plus" if bedrooms >= 5 else None
    )


def utility_total_for(code: str | None) -> tuple[int, str]:
    """Measured monthly tenant utility burden, and a citable source string.

    ACS median gross rent minus median contract rent for the tract. Falls back
    to the city figure when the tract is unknown or reports no utility gap.
    """
    rec = tract(code)
    if rec and rec.get("implied_monthly_utilities"):
        return (
            int(rec["implied_monthly_utilities"]),
            f"ACS B25064-B25058, census tract {code}",
        )
    city = city_baseline()
    return (
        int(city["implied_monthly_utilities"]),
        "ACS B25064-B25058, New Haven city",
    )


def baseline_rent_for(code: str | None, bedrooms: int | None) -> tuple[int | None, str | None]:
    """Median GROSS rent to compare a listing against, plus its source.

    Prefers the tract's own figure for that bedroom count, then the tract
    overall, then the city for that bedroom count, then the city overall.
    """
    key = bedroom_key(bedrooms)
    rec = tract(code)

    if rec and key:
        value = (rec.get("median_gross_rent_by_bedrooms") or {}).get(key)
        if value:
            return int(value), f"ACS B25031 {key}, census tract {code}"

    if rec and rec.get("median_gross_rent"):
        return int(rec["median_gross_rent"]), f"ACS B25064, census tract {code}"

    city = city_baseline()
    if key:
        value = (city.get("median_gross_rent_by_bedrooms") or {}).get(key)
        if value:
            return int(value), f"ACS B25031 {key}, New Haven city"

    if city.get("median_gross_rent"):
        return int(city["median_gross_rent"]), "ACS B25064, New Haven city"

    return None, None


def dataset_summary() -> dict:
    """Shown in the app so a user can see what it actually knows."""
    lp, bp = listings_payload(), baseline_payload()
    return {
        "listings": lp["count"],
        "listings_source": lp["source"],
        "listings_captured": lp["captured_at"],
        "tracts": len(bp["tracts"]),
        "acs_vintage": bp["vintage"],
        "city_median_gross_rent": bp["city"]["median_gross_rent"],
        "city_median_contract_rent": bp["city"]["median_contract_rent"],
        "city_implied_utilities": bp["city"]["implied_monthly_utilities"],
        "rules": len(rules()["rules"]),
        "scam_patterns": len(rules()["scam_patterns"]),
    }
