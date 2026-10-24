"""Structured outputs.

One rule runs through every schema here: a field the source did not state is
None, and its name goes in `unknown_fields`. The app is for people who cannot
visit the apartment, so a confident guess is worse than an admitted blank.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Basis = Literal["stated", "census_estimate", "profile_assumption", "market_default"]
Severity = Literal["illegal", "risky", "info"]
Verdict = Literal["below_market", "at_market", "above_market", "unknown"]


# --------------------------------------------------------------------------
# 1. Intake - what the agent pulls out of untrusted listing text
# --------------------------------------------------------------------------
class ParsedListing(BaseModel):
    """Extracted from a listing. Never invent a value that is not in the text."""

    address: str | None = Field(None, description="Street address exactly as written")
    neighborhood: str | None = None
    bedrooms: int | None = Field(None, description="Studio counts as 0")
    bathrooms: float | None = None
    asking_rent_usd: int | None = Field(None, description="Monthly rent as advertised")
    rent_is_per_person: bool | None = Field(
        None, description="True only if the ad says the price is per person/per bed"
    )

    utilities_included: list[str] = Field(
        default_factory=list,
        description="Verbatim utility terms the ad says are included, e.g. 'Heat Included'",
    )
    utilities_explicitly_excluded: list[str] = Field(default_factory=list)

    laundry: Literal["in_unit", "on_site", "nearby", "none", "unknown"] = "unknown"
    parking: Literal["included", "paid", "street", "none", "unknown"] = "unknown"
    furnished: bool | None = None
    floor: int | None = None
    square_feet: int | None = None

    lease_start_month: str | None = Field(None, description="Month name if stated, e.g. 'June'")
    lease_length_months: int | None = None
    security_deposit_text: str | None = Field(
        None, description="Deposit wording exactly as written, e.g. '2 months security'"
    )
    broker_fee_text: str | None = None
    payment_terms_text: str | None = Field(
        None, description="Any wording about how rent or deposit must be paid"
    )

    unknown_fields: list[str] = Field(
        default_factory=list,
        description="Names of fields this ad does not state. Be exhaustive and honest.",
    )
    parser_notes: str | None = Field(
        None, description="Ambiguities worth flagging, e.g. 'reasonable cap' on electricity"
    )


# --------------------------------------------------------------------------
# 2. Cost - the twelve-month picture, not the advertised monthly number
# --------------------------------------------------------------------------
class CostLine(BaseModel):
    label: str
    monthly_usd: float
    basis: Basis = Field(description="Where this number came from")
    source: str = Field(description="Citable origin, e.g. 'ACS B25064/B25058 tract 361401'")


class CostSimulation(BaseModel):
    monthly_rent_usd: float
    lines: list[CostLine]
    monthly_total_usd: float

    lease_months: int
    gap_months: int = Field(
        0, description="Months paid for but not needed, from lease/term calendar mismatch"
    )
    gap_explanation: str | None = None

    first_year_total_usd: float
    upfront_cash_usd: float = Field(
        0, description="Deposit plus first month due before move-in"
    )
    deposit_months: float | None = Field(
        None, description="Deposit in months of rent, None when the ad never says"
    )
    upfront_is_floor: bool = Field(
        False,
        description="True when the deposit was not stated, so upfront_cash_usd is a "
                    "lower bound rather than the real figure",
    )
    confidence: Literal["high", "medium", "low"]
    assumptions: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# 3. Fair price - measured against public data, not vibes
# --------------------------------------------------------------------------
class FairPriceAssessment(BaseModel):
    census_tract: str | None = None
    tract_name: str | None = None
    bedrooms: int | None = None

    tract_median_gross_rent_usd: int | None = None
    bedroom_median_gross_rent_usd: int | None = None
    baseline_used_usd: int | None = None
    baseline_source: str | None = None

    listing_gross_rent_usd: float | None = Field(
        None, description="Asking rent plus any utilities the tenant must pay"
    )
    delta_usd: float | None = None
    delta_pct: float | None = None
    verdict: Verdict = "unknown"
    caveat: str | None = Field(
        None, description="Why this comparison might mislead, if it might"
    )


# --------------------------------------------------------------------------
# 4. Legal and scam risk - every claim must carry a rule id
# --------------------------------------------------------------------------
class RiskFinding(BaseModel):
    rule_id: str = Field(description="Identifier of the rule or pattern, never invented")
    severity: Severity
    title: str
    evidence: str = Field(description="Quoted text from the listing that triggered this")
    explanation: str
    what_to_do: str | None = None


class RiskReport(BaseModel):
    findings: list[RiskFinding] = Field(default_factory=list)
    checked_rules: list[str] = Field(default_factory=list)
    nothing_found_note: str | None = None


# --------------------------------------------------------------------------
# 5. Fit against a person's actual constraints
# --------------------------------------------------------------------------
class RenterProfile(BaseModel):
    monthly_budget_usd: int | None = None
    destination: str = Field("Yale campus", description="Where they commute to")
    arrival_month: str | None = Field(None, description="When they actually need the place")
    has_car: bool = False
    max_walk_minutes: int | None = None
    household_size: int = 1
    needs_furnished: bool = False
    needs_in_unit_laundry: bool = False
    is_international: bool = Field(
        False, description="Cannot view in person, unfamiliar with US rental norms"
    )
    notes: str | None = None


class FitAssessment(BaseModel):
    score: int = Field(ge=0, le=100)
    meets: list[str] = Field(default_factory=list)
    fails: list[str] = Field(default_factory=list)
    commute_note: str | None = None
    calendar_note: str | None = None


# --------------------------------------------------------------------------
# 6. The advice a person who cannot visit actually needs
# --------------------------------------------------------------------------
class ViewingQuestion(BaseModel):
    question: str
    why_it_matters: str
    dollar_impact: str | None = Field(
        None, description="What getting this wrong costs, when it can be quantified"
    )


class Advice(BaseModel):
    headline: str = Field(description="One sentence a tired person can act on")
    reasoning: list[str] = Field(default_factory=list)
    biggest_unknown: str | None = None
    viewing_questions: list[ViewingQuestion] = Field(default_factory=list)
    walk_away_if: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# 7. Ranking the whole snapshot against one person's constraints
# --------------------------------------------------------------------------
class Destination(BaseModel):
    """Where the person actually has to get to every day."""

    label: str
    address: str | None = None
    lat: float
    lng: float
    resolved_by: Literal["quick_pick", "geocoder", "fallback"] = "geocoder"
    matched_address: str | None = None


class Recommendation(BaseModel):
    listing_id: int
    address: str
    bedrooms_min: int | None = None
    bedrooms_max: int | None = None

    advertised_rent_usd: int | None = None
    utilities_tenant_pays_usd: float | None = None
    real_monthly_usd: float | None = None
    first_year_total_usd: float | None = None

    fair_price_delta_pct: float | None = None
    fair_price_verdict: Verdict = "unknown"

    distance_km: float | None = None
    walk_minutes: int | None = None
    bike_minutes: int | None = None

    score: int = Field(ge=0, le=100)
    within_budget: bool = False
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    unknown_count: int = 0


class RecommendationResult(BaseModel):
    destination: Destination | None = None
    destination_error: str | None = None
    considered: int = 0
    returned: int = 0
    recommendations: list[Recommendation] = Field(default_factory=list)
    method_note: str
    model_calls: int = Field(
        0, description="Always zero. Ranking is arithmetic, not inference."
    )


# --------------------------------------------------------------------------
# Envelope returned to the browser
# --------------------------------------------------------------------------
class TokenUsage(BaseModel):
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    requests: int = 0
    estimated_cost_usd: float = 0.0


class AgentStep(BaseModel):
    agent: str
    summary: str
    usage: TokenUsage
    seconds: float


class Evaluation(BaseModel):
    listing: ParsedListing
    cost: CostSimulation | None = None
    fair_price: FairPriceAssessment | None = None
    risk: RiskReport | None = None
    fit: FitAssessment | None = None
    advice: Advice | None = None

    injection_blocked: bool = False
    injection_detail: str | None = None

    steps: list[AgentStep] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    seconds: float = 0.0
