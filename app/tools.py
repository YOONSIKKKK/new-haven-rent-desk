"""Deterministic calculations.

None of this is a model call. Every dollar figure the app shows is computed
here, from committed public data, so a language model cannot invent a number,
drift between runs, or be talked into a different answer by hostile text in a
listing. The agents read these results and explain them; they do not produce
them.
"""
from __future__ import annotations

import re

from . import data_store as store
from .models import (
    CostLine,
    CostSimulation,
    FairPriceAssessment,
    ParsedListing,
    RenterProfile,
    RiskFinding,
    RiskReport,
)

MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]


def month_number(name: str | None) -> int | None:
    if not name:
        return None
    key = str(name).strip().lower()[:3]
    for i, m in enumerate(MONTHS, start=1):
        if m.startswith(key):
            return i
    return None


# --------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------
def _covered_components(utilities_included: list[str]) -> set[str]:
    """Map a listing's utility wording onto cost components it removes."""
    term_map = store.assumptions()["utility_term_map"]
    covered: set[str] = set()
    for raw in utilities_included or []:
        key = str(raw).strip().lower()
        if key in term_map:
            covered.update(term_map[key])
            continue
        # Fall back to substring matching for wording we have not seen before.
        for term, components in term_map.items():
            if term.startswith("_"):
                continue
            if term in key or key in term:
                covered.update(components)
                break
    return covered


def estimate_tenant_utilities(
    utilities_included: list[str], census_tract: str | None
) -> tuple[float, str, list[str]]:
    """Monthly utility cost the tenant still carries.

    The total is measured (ACS gross rent minus contract rent for the tract).
    Only the split across components is assumed, and the caller is told so.
    """
    total, source = store.utility_total_for(census_tract)
    shares = store.assumptions()["utility_component_shares"]
    covered = _covered_components(utilities_included)

    remaining_share = sum(
        weight for name, weight in shares.items()
        if not name.startswith("_") and name not in covered
    )
    monthly = round(total * remaining_share, 2)

    notes = []
    if covered:
        notes.append(
            f"Listing says these are included: {', '.join(sorted(covered))}. "
            f"Credited against the ${total}/mo measured for this area."
        )
    else:
        notes.append(
            f"No utilities stated as included, so the full ${total}/mo measured "
            "for this area is assumed to fall on the tenant."
        )
    return monthly, source, notes


# --------------------------------------------------------------------------
# Twelve-month cost
# --------------------------------------------------------------------------
def simulate_cost(
    listing: ParsedListing, profile: RenterProfile, census_tract: str | None
) -> CostSimulation:
    assumptions = store.assumptions()
    extras = assumptions["costs_outside_gross_rent"]
    calendar = assumptions["academic_calendar"]

    rent = float(listing.asking_rent_usd or 0)
    if listing.rent_is_per_person and profile.household_size > 1:
        rent = rent * profile.household_size

    lines: list[CostLine] = []
    notes: list[str] = []

    utilities, util_source, util_notes = estimate_tenant_utilities(
        listing.utilities_included, census_tract
    )
    notes.extend(util_notes)
    if utilities > 0:
        lines.append(CostLine(
            label="Utilities you pay",
            monthly_usd=utilities,
            basis="census_estimate",
            source=util_source,
        ))

    if not any("internet" in u.lower() or "wifi" in u.lower()
               for u in listing.utilities_included):
        lines.append(CostLine(
            label="Internet",
            monthly_usd=float(extras["internet"]["monthly_usd"]),
            basis="market_default",
            source=extras["internet"]["note"],
        ))

    if listing.laundry in ("on_site", "nearby", "none", "unknown"):
        label = "Laundry (coin/card)" if listing.laundry != "unknown" else "Laundry (not stated)"
        lines.append(CostLine(
            label=label,
            monthly_usd=float(extras["laundry"]["monthly_usd"]),
            basis="market_default",
            source=extras["laundry"]["note"],
        ))
        if listing.laundry == "unknown":
            notes.append("Laundry arrangement is not stated; assumed not in-unit.")

    if profile.has_car and listing.parking in ("paid", "none", "street", "unknown"):
        lines.append(CostLine(
            label="Parking",
            monthly_usd=float(extras["parking"]["monthly_usd"]),
            basis="market_default",
            source=extras["parking"]["note"],
        ))

    lines.append(CostLine(
        label="Renters insurance",
        monthly_usd=float(extras["renters_insurance"]["monthly_usd"]),
        basis="market_default",
        source=extras["renters_insurance"]["note"],
    ))

    if profile.is_international and not listing.furnished:
        lines.append(CostLine(
            label="Furnishing (spread over 12 months)",
            monthly_usd=float(extras["furnishing_amortised"]["monthly_usd"]),
            basis="profile_assumption",
            source=extras["furnishing_amortised"]["note"],
        ))

    monthly_total = round(rent + sum(line.monthly_usd for line in lines), 2)

    # Academic-calendar gap: months billed before the renter actually arrives.
    lease_months = listing.lease_length_months or 12
    start = month_number(listing.lease_start_month) or month_number(
        calendar["default_lease_start_month"]
    )
    arrive = month_number(profile.arrival_month) or month_number(
        calendar["yale_term_start_month"]
    )
    gap = 0
    gap_explanation = None
    if start and arrive and arrive > start:
        gap = arrive - start
        gap_explanation = (
            f"The lease starts in {listing.lease_start_month or calendar['default_lease_start_month']} "
            f"but you arrive in {profile.arrival_month or calendar['yale_term_start_month']}. "
            f"That is {gap} month(s) of rent for an empty apartment "
            f"(${round(rent * gap):,}), unless you can sublet."
        )
        if listing.lease_start_month is None:
            notes.append(
                "Lease start month was not stated; assumed the New Haven student "
                f"standard of {calendar['default_lease_start_month']} 1."
            )

    first_year = round(monthly_total * lease_months, 2)

    deposit_months = parse_deposit_months(listing.security_deposit_text)
    upfront = round(rent * (deposit_months or 0) + rent, 2)
    if deposit_months is None:
        # Connecticut allows up to two months. An ad that stays silent is not an
        # ad with no deposit, so say so rather than quietly implying zero.
        notes.append(
            "The advertisement never states a security deposit. Connecticut allows "
            f"up to two months' rent, so budget for up to ${rent * 2:,.0f} more than "
            "the figure shown before you move in."
        )

    stated = sum(1 for line in lines if line.basis == "stated")
    assumed = sum(1 for line in lines if line.basis in ("market_default", "profile_assumption"))
    unknown_count = len(listing.unknown_fields)
    if unknown_count >= 5 or assumed > stated + 3:
        confidence = "low"
    elif unknown_count >= 2:
        confidence = "medium"
    else:
        confidence = "high"

    return CostSimulation(
        monthly_rent_usd=rent,
        lines=lines,
        monthly_total_usd=monthly_total,
        lease_months=lease_months,
        gap_months=gap,
        gap_explanation=gap_explanation,
        first_year_total_usd=first_year,
        upfront_cash_usd=upfront,
        deposit_months=deposit_months,
        upfront_is_floor=deposit_months is None,
        confidence=confidence,
        assumptions=notes,
    )


# --------------------------------------------------------------------------
# Fair price against public data
# --------------------------------------------------------------------------
def assess_fair_price(
    listing: ParsedListing, census_tract: str | None, tenant_utilities_usd: float
) -> FairPriceAssessment:
    """Compare like with like: ACS reports GROSS rent, so we gross up the ad."""
    rec = store.tract(census_tract)
    baseline, source = store.baseline_rent_for(census_tract, listing.bedrooms)

    out = FairPriceAssessment(
        census_tract=census_tract,
        tract_name=(rec or {}).get("name"),
        bedrooms=listing.bedrooms,
        tract_median_gross_rent_usd=(rec or {}).get("median_gross_rent"),
        bedroom_median_gross_rent_usd=(
            ((rec or {}).get("median_gross_rent_by_bedrooms") or {})
            .get(store.bedroom_key(listing.bedrooms) or "")
        ),
        baseline_used_usd=baseline,
        baseline_source=source,
    )

    if not listing.asking_rent_usd or not baseline:
        out.caveat = "Not enough information to compare this against local rents."
        return out

    gross = round(float(listing.asking_rent_usd) + tenant_utilities_usd, 2)
    out.listing_gross_rent_usd = gross
    out.delta_usd = round(gross - baseline, 2)
    out.delta_pct = round((gross - baseline) / baseline * 100, 1)

    if out.delta_pct <= -10:
        out.verdict = "below_market"
    elif out.delta_pct >= 10:
        out.verdict = "above_market"
    else:
        out.verdict = "at_market"

    out.caveat = (
        "ACS medians cover all rentals in the tract, not just student housing, and "
        "do not adjust for condition, floor or renovation. Treat this as a bearing, "
        "not a valuation."
    )
    return out


# --------------------------------------------------------------------------
# Legal and scam checks
# --------------------------------------------------------------------------
def parse_deposit_months(text: str | None) -> float | None:
    """Pull a month count out of deposit wording like '2 months security'."""
    if not text:
        return None
    t = text.lower()
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "half": 0.5}
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:month|mo\b)", t)
    if m:
        return float(m.group(1))
    for word, value in words.items():
        if re.search(rf"\b{word}\b\s*(?:month|mo\b)", t):
            return float(value)
    return None


def check_rules(
    listing: ParsedListing,
    ad_text: str,
    delta_pct: float | None = None,
    tenant_is_62_plus: bool = False,
) -> RiskReport:
    """Apply the rule file. Deterministic: a finding exists only if a rule fires."""
    rules_file = store.rules()
    findings: list[RiskFinding] = []
    checked: list[str] = []
    haystack = (ad_text or "").lower()

    deposit_months = parse_deposit_months(listing.security_deposit_text)

    for rule in rules_file["rules"]:
        checked.append(rule["rule_id"])
        test = rule["test"]
        fired = False
        evidence = listing.security_deposit_text or ""

        if test == "security_deposit_months > 2":
            fired = deposit_months is not None and deposit_months > 2
        elif test == "tenant_is_62_plus and security_deposit_months > 1":
            fired = tenant_is_62_plus and deposit_months is not None and deposit_months > 1
        elif test == "pet_deposit_separate":
            fired = bool(re.search(r"pet\s+(deposit|fee)", haystack))
            if fired:
                evidence = _quote(ad_text, r"pet\s+(deposit|fee)")
        elif test == "always_inform":
            fired = deposit_months is not None or bool(listing.security_deposit_text)
            evidence = listing.security_deposit_text or "A deposit will be required."

        if fired:
            findings.append(RiskFinding(
                rule_id=rule["rule_id"],
                severity=rule["severity"],
                title=rule["title"],
                evidence=evidence or "(stated in the listing)",
                explanation=rule["summary"],
                what_to_do=rule.get("what_to_do"),
            ))

    for pattern in rules_file["scam_patterns"]:
        checked.append(pattern["rule_id"])
        if pattern.get("test") == "delta_pct < -35":
            if delta_pct is not None and delta_pct < -35:
                findings.append(RiskFinding(
                    rule_id=pattern["rule_id"],
                    severity=pattern["severity"],
                    title=pattern["title"],
                    evidence=f"Priced {abs(delta_pct):.0f}% below the local baseline.",
                    explanation=pattern["summary"],
                    what_to_do=pattern.get("what_to_do"),
                ))
            continue

        hit = next((k for k in pattern.get("keywords", []) if k in haystack), None)
        if hit:
            findings.append(RiskFinding(
                rule_id=pattern["rule_id"],
                severity=pattern["severity"],
                title=pattern["title"],
                evidence=_quote(ad_text, re.escape(hit)),
                explanation=pattern["summary"],
                what_to_do=pattern.get("what_to_do"),
            ))

    for term in rules_file["ambiguous_terms"]:
        if term["term"] in haystack:
            findings.append(RiskFinding(
                rule_id=f"AMBIGUOUS-{term['term'].replace(' ', '-').upper()}",
                severity="info",
                title=f'Vague wording: "{term["term"]}"',
                evidence=_quote(ad_text, re.escape(term["term"])),
                explanation=term["why"],
                what_to_do="Ask the landlord to put a specific number or list in writing.",
            ))

    return RiskReport(
        findings=findings,
        checked_rules=checked,
        nothing_found_note=(
            None if findings else
            "No rule in the Connecticut rule file fired on this listing. That is not "
            "a clean bill of health - most of what matters is in the lease, not the ad."
        ),
    )


def _quote(text: str, pattern: str, window: int = 70) -> str:
    m = re.search(pattern, text or "", re.I)
    if not m:
        return ""
    start = max(0, m.start() - window)
    end = min(len(text), m.end() + window)
    snippet = text[start:end].strip().replace("\n", " ")
    return f"...{snippet}..." if start > 0 or end < len(text) else snippet


# --------------------------------------------------------------------------
# Listing search over the committed snapshot
# --------------------------------------------------------------------------
def search_listings(
    max_rent: int | None = None,
    min_bedrooms: int | None = None,
    max_walk_minutes: int | None = None,
    requires_laundry: bool = False,
    limit: int = 20,
) -> list[dict]:
    out = []
    for r in store.listings():
        if max_rent and (r.get("rent_min") or 0) > max_rent:
            continue
        if min_bedrooms is not None and (r.get("bed_max") or 0) < min_bedrooms:
            continue
        walk = r.get("walk_minutes_to_campus")
        if max_walk_minutes and walk is not None and walk > max_walk_minutes:
            continue
        if requires_laundry:
            features = r.get("property_features") or {}
            unit_features = " ".join(r.get("unit_features") or []).lower()
            if not (features.get("on-site-laundry") or "laundry" in unit_features):
                continue
        out.append(r)
        if len(out) >= limit:
            break
    return out
