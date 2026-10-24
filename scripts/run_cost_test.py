"""Measure what this app costs to run, and whether cutting cost hurt it.

Runs the same listings through two configurations:

  full    the shipped app - reference material in the cached prefix
  lean    the same agents with the reference material removed

"lean" is the cheaper-looking option: fewer input tokens per call. The point of
this script is to check whether it is actually cheaper once prompt caching is
accounted for, and what it costs in output quality if it is.

Writes output/cost_test.json and prints the tables that go in the report.

Run:  .venv/Scripts/python.exe scripts/run_cost_test.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import agents, data_store as store  # noqa: E402
from app.models import RenterProfile  # noqa: E402
from app.orchestrator import evaluate  # noqa: E402

OUT = ROOT / "output" / "cost_test.json"
SAMPLE = 8
PROFILE = RenterProfile(
    monthly_budget_usd=2200, arrival_month="August",
    is_international=True, max_walk_minutes=20,
)


def sample_listings(n: int) -> list[dict]:
    """Stratified, not the first n.

    The snapshot is ordered so that its first listings happen to be managed
    properties with almost no utility detail. Taking the head makes the parser
    look like it extracts nothing, which is a fact about the sample and not
    about the parser. Half the sample is drawn from listings that name three or
    more utilities and half from listings that name none, so the quality
    columns below mean something.
    """
    rows = [r for r in store.listings() if r.get("rent_min") and r.get("census_tract")]
    rich = [r for r in rows if len(r.get("utilities_included") or []) >= 3]
    bare = [r for r in rows if not r.get("utilities_included")]
    half = n // 2
    picked = rich[:half] + bare[:n - half]
    return picked or rows[:n]


def run_config(rows: list[dict], lean: bool) -> list[dict]:
    """lean=True strips the cached reference material from every agent."""
    original = {}
    if lean:
        for name in ("new_haven_glossary", "connecticut_rule_reference", "market_reference"):
            original[name] = getattr(agents.prompts, name)
            setattr(agents.prompts, name, lambda: "")

    try:
        out = []
        for row in rows:
            ev = evaluate(row["raw_ad_text"], PROFILE, listing_id=row["id"])
            out.append({
                "address": row["address"],
                "input_tokens": sum(s.usage.input_tokens for s in ev.steps),
                "cached_tokens": sum(s.usage.cached_input_tokens for s in ev.steps),
                "output_tokens": sum(s.usage.output_tokens for s in ev.steps),
                "cost_usd": ev.usage.estimated_cost_usd,
                "seconds": ev.seconds,
                # quality signals
                "unknown_fields": len(ev.listing.unknown_fields),
                "utilities_found": len(ev.listing.utilities_included),
                "parser_noted_ambiguity": bool(ev.listing.parser_notes),
                "risk_findings": len(ev.risk.findings) if ev.risk else 0,
                # Rule-based findings come from tools.check_rules, which never
                # sees a prompt, so they are identical across configurations by
                # construction. Any difference in totals is the agent
                # speculating on its own.
                "rule_findings": sum(
                    1 for f in (ev.risk.findings if ev.risk else [])
                    if not f.rule_id.startswith("OBSERVED-")
                ),
                "agent_added_findings": sum(
                    1 for f in (ev.risk.findings if ev.risk else [])
                    if f.rule_id.startswith("OBSERVED-")
                ),
                "questions": len(ev.advice.viewing_questions) if ev.advice else 0,
                "questions_with_dollar_impact": sum(
                    1 for q in (ev.advice.viewing_questions if ev.advice else [])
                    if q.dollar_impact
                ),
            })
        return out
    finally:
        for name, fn in original.items():
            setattr(agents.prompts, name, fn)


def summarise(runs: list[dict]) -> dict:
    n = len(runs)
    # The first run of a configuration pays to populate the cache; steady state
    # is what a real user after the first one actually costs.
    steady = runs[1:] or runs
    return {
        "runs": n,
        "mean_input": round(sum(r["input_tokens"] for r in runs) / n),
        "mean_cached": round(sum(r["cached_tokens"] for r in runs) / n),
        "mean_output": round(sum(r["output_tokens"] for r in runs) / n),
        "mean_cost_usd": round(sum(r["cost_usd"] for r in runs) / n, 6),
        "steady_cost_usd": round(sum(r["cost_usd"] for r in steady) / len(steady), 6),
        "cache_rate_pct": round(
            sum(r["cached_tokens"] for r in runs) / max(1, sum(r["input_tokens"] for r in runs)) * 100, 1
        ),
        "mean_seconds": round(sum(r["seconds"] for r in runs) / n, 2),
        "mean_unknown_fields": round(sum(r["unknown_fields"] for r in runs) / n, 1),
        "mean_utilities_found": round(sum(r["utilities_found"] for r in runs) / n, 1),
        "ambiguity_noted_pct": round(
            sum(1 for r in runs if r["parser_noted_ambiguity"]) / n * 100
        ),
        "mean_risk_findings": round(sum(r["risk_findings"] for r in runs) / n, 1),
        "mean_rule_findings": round(sum(r["rule_findings"] for r in runs) / n, 1),
        "mean_agent_added_findings": round(sum(r["agent_added_findings"] for r in runs) / n, 1),
        "mean_questions": round(sum(r["questions"] for r in runs) / n, 1),
        "mean_questions_with_dollar_impact": round(
            sum(r["questions_with_dollar_impact"] for r in runs) / n, 1
        ),
    }


def main() -> None:
    rows = sample_listings(SAMPLE)
    print(f"Running {len(rows)} listings in each configuration...\n")

    print("  full (reference material in the cached prefix)")
    full = run_config(rows, lean=False)
    print("  lean (reference material removed)")
    lean = run_config(rows, lean=True)

    s_full, s_lean = summarise(full), summarise(lean)

    print()
    print(f"{'':34}{'full':>12}{'lean':>12}")
    print("-" * 58)
    rows_out = [
        ("input tokens per listing", "mean_input", "{:,}"),
        ("  of which cached", "mean_cached", "{:,}"),
        ("cache rate", "cache_rate_pct", "{}%"),
        ("output tokens per listing", "mean_output", "{:,}"),
        ("cost per listing", "mean_cost_usd", "${:.6f}"),
        ("steady-state cost per listing", "steady_cost_usd", "${:.6f}"),
        ("seconds per listing", "mean_seconds", "{}s"),
        ("", None, None),
        ("unknown fields admitted", "mean_unknown_fields", "{}"),
        ("utilities extracted", "mean_utilities_found", "{}"),
        ("ambiguity flagged", "ambiguity_noted_pct", "{}%"),
        ("risk findings", "mean_risk_findings", "{}"),
        ("  from the rule file", "mean_rule_findings", "{}"),
        ("  the agent added itself", "mean_agent_added_findings", "{}"),
        ("viewing questions", "mean_questions", "{}"),
        ("  with a dollar figure", "mean_questions_with_dollar_impact", "{}"),
    ]
    for label, key, fmt in rows_out:
        if key is None:
            print()
            continue
        print(f"{label:34}{fmt.format(s_full[key]):>12}{fmt.format(s_lean[key]):>12}")

    per_run = s_full["steady_cost_usd"]
    print()
    print("AT SCALE (steady-state cost, full configuration)")
    print("-" * 58)
    for label, runs_per_month in [
        ("one student, 20 listings", 20),
        ("100 students a month", 100 * 20),
        ("10,000 students a month", 10_000 * 20),
    ]:
        print(f"  {label:32} {runs_per_month:>9,} runs   ${per_run * runs_per_month:>10,.2f}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "sample_size": len(rows),
        "price_source": store.assumptions()["pricing"]["source"],
        "full": {"summary": s_full, "runs": full},
        "lean": {"summary": s_lean, "runs": lean},
    }, indent=2), encoding="utf-8")
    print()
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
