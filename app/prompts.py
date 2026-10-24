"""Instruction blocks, assembled from the committed data files.

Two things are happening here at once, and both matter.

QUALITY. An agent that knows what "triple decker", "heat included" and
"Elm Campus" mean in New Haven parses a New Haven advertisement better than one
guessing from general knowledge. The reference material below is built from the
actual snapshot and the actual rule file, so it cannot drift away from what the
app enforces.

COST. That reference material is identical on every single run. Putting it at
the front of the prompt, ahead of anything that varies, makes it a stable
prefix the provider can cache. Below roughly a thousand tokens of stable prefix
nothing is cached at all, which is exactly what the first version of this app
measured: zero cached tokens on every call.
"""
from __future__ import annotations

from functools import lru_cache

from . import data_store as store


@lru_cache(maxsize=1)
def new_haven_glossary() -> str:
    """Listing idioms, with the utility vocabulary taken from the real snapshot."""
    rules = store.rules()
    seen: dict[str, int] = {}
    for row in store.listings():
        for utility in row.get("utilities_included") or []:
            seen[utility] = seen.get(utility, 0) + 1
    vocabulary = sorted(seen.items(), key=lambda kv: -kv[1])

    lines = [
        "REFERENCE: HOW NEW HAVEN RENTAL ADVERTISEMENTS ARE WRITTEN",
        "",
        "Utility wording that appears in the snapshot of this market, with how",
        "many of the 152 listings use each phrase. Treat these as the vocabulary",
        "you will actually meet. Record them verbatim; do not normalise them.",
        "",
    ]
    for term, count in vocabulary:
        lines.append(f"  {count:>3} listings   {term}")

    lines += [
        "",
        "Phrases that look informative and are not. When one appears, record it",
        "verbatim and raise it in parser_notes:",
        "",
    ]
    for item in rules["ambiguous_terms"]:
        lines.append(f'  "{item["term"]}"')
        lines.append(f"      {item['why']}")

    lines += [
        "",
        "Local facts that change how an advertisement should be read:",
        "",
        "  - Much of New Haven's rental stock is the three-storey wooden",
        "    multi-family house known locally as a triple decker. A listing that",
        "    says '3rd floor' in such a building usually means walk-up, no lift,",
        "    and the highest heating bill in the building.",
        "  - Student leases here overwhelmingly run 1 June to 31 May. The",
        "    academic year starts in late August. An advertisement that gives a",
        "    start month but no year is a real ambiguity, not a typo.",
        "  - 'Elm Campus' and 'Yale owned' listings are managed properties; their",
        "    advertisements often carry a generic description that says nothing",
        "    about the specific unit. Do not read unit detail into boilerplate.",
        "  - Heat is the dominant utility cost in Connecticut. 'Heat included'",
        "    does not imply hot water, cooking gas or electricity are included.",
        "  - Rent is sometimes quoted per person rather than per unit. Only set",
        "    rent_is_per_person when the advertisement actually says so.",
    ]
    return "\n".join(lines)


@lru_cache(maxsize=1)
def connecticut_rule_reference() -> str:
    """The full rule file, so the risk agent explains only rules that exist."""
    rules = store.rules()
    lines = [
        "REFERENCE: THE CONNECTICUT RULES THIS APP IS ALLOWED TO ASSERT",
        "",
        "This is the complete list. If a rule is not here, you have no authority",
        "to state it as Connecticut law, however confident you feel.",
        "",
    ]
    for rule in rules["rules"]:
        lines += [
            f"  [{rule['rule_id']}]  severity: {rule['severity']}",
            f"      {rule['title']}",
            f"      {rule['summary']}",
            f"      action: {rule.get('what_to_do', '-')}",
            "",
        ]

    lines += ["KNOWN SCAM PATTERNS", ""]
    for pattern in rules["scam_patterns"]:
        lines += [
            f"  [{pattern['rule_id']}]  severity: {pattern['severity']}",
            f"      {pattern['title']}",
            f"      {pattern['summary']}",
            f"      action: {pattern.get('what_to_do', '-')}",
            "",
        ]

    lines += [
        "SOURCES",
        "",
    ]
    for source in rules["sources"]:
        lines.append(f"  {source['title']} - {source['url']}")
    lines += [
        "",
        "These are summaries for a renter, not legal advice, and the app says so.",
    ]
    return "\n".join(lines)


@lru_cache(maxsize=1)
def market_reference() -> str:
    """Census figures, so the advisor talks about this market in context."""
    payload = store.baseline_payload()
    city = payload["city"]
    by_bed = city.get("median_gross_rent_by_bedrooms") or {}

    utilities = sorted(
        t["implied_monthly_utilities"] for t in payload["tracts"]
        if t.get("implied_monthly_utilities") is not None
    )
    low, mid, high = utilities[0], utilities[len(utilities) // 2], utilities[-1]

    return "\n".join([
        "REFERENCE: WHAT RENTING IN NEW HAVEN ACTUALLY COSTS",
        "",
        f"U.S. Census ACS {payload['vintage']} five-year estimates, "
        f"{len(payload['tracts'])} census tracts.",
        "",
        f"  Median gross rent, New Haven city      ${city['median_gross_rent']}",
        f"  Median contract rent (rent only)       ${city['median_contract_rent']}",
        f"  Implied utility cost to the tenant     ${city['implied_monthly_utilities']} per month",
        "",
        "  Median gross rent by bedroom count:",
        f"    studio ${by_bed.get('studio')}   1BR ${by_bed.get('1br')}   "
        f"2BR ${by_bed.get('2br')}   3BR ${by_bed.get('3br')}",
        "",
        f"  Across tracts the tenant's utility burden runs from ${low} to ${high} "
        f"per month, median ${mid}.",
        "",
        "That spread is the point of this app. Two apartments with the same",
        "advertised rent can differ by hundreds of dollars a month once heating",
        "is counted, and the advertisement is where that difference hides.",
        "",
        "Gross rent means rent plus utilities. Contract rent means rent alone.",
        "When comparing a listing to these figures, compare like with like.",
    ])
