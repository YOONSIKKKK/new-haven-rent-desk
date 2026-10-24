"""Summarise the user-study sessions into output/user_study.json.

Reads every research/sessions/*.json that does not start with an underscore and
computes the one number the study exists for: how far the app's twelve-month
prediction lands from what participants actually paid.

Deliberately refuses to average away a small sample. With fewer than three
sessions it reports the individual figures and says so, because a mean of two
people is a number that looks like evidence and is not.

    .venv/Scripts/python.exe scripts/build_user_study.py
"""
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSIONS = ROOT / "research" / "sessions"
OUT = ROOT / "output" / "user_study.json"

# Fields that must never appear in a public repository.
FORBIDDEN_KEYS = {"name", "full_name", "email", "phone", "address", "street", "landlord"}


def load_sessions() -> list[dict]:
    files = sorted(p for p in SESSIONS.glob("*.json") if not p.name.startswith("_"))
    out = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            sys.exit(f"{path.name} is not valid JSON: {exc}")
        data["_file"] = path.name
        out.append(data)
    return out


def check_anonymity(sessions: list[dict]) -> list[str]:
    """The repo is public. Shout about anything that looks identifying."""
    problems = []
    for s in sessions:
        def walk(node, trail=""):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k.startswith("_"):
                        continue
                    if k.lower() in FORBIDDEN_KEYS and v:
                        problems.append(f"{s['_file']}: field '{trail}{k}' looks identifying")
                    walk(v, f"{trail}{k}.")
            elif isinstance(node, list):
                for item in node:
                    walk(item, trail)
        walk(s)
        quote = (s.get("reaction") or {}).get("quote")
        consented = (s.get("reaction") or {}).get("consented_to_anonymous_quote")
        if quote and not consented:
            problems.append(f"{s['_file']}: has a quote but consent is not recorded")
    return problems


def num(node, *path):
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node if isinstance(node, (int, float)) else None


def main() -> None:
    sessions = load_sessions()

    if not sessions:
        print("No sessions yet.")
        print()
        print("  1. cp research/sessions/_template.json research/sessions/P1.json")
        print("  2. Run the interview: research/interview_protocol.md")
        print("  3. Re-run this script")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({"sessions": 0, "status": "not started"}, indent=2), encoding="utf-8")
        return

    problems = check_anonymity(sessions)
    if problems:
        print("ANONYMITY CHECK FAILED - fix before committing:")
        for p in problems:
            print("  -", p)
        sys.exit(1)

    rows = []
    for s in sessions:
        actual = num(s, "their_actual_first_year", "total_usd")
        predicted = num(s, "app_said", "first_year_total_usd")
        error_pct = None
        if actual and predicted:
            error_pct = round((predicted - actual) / actual * 100, 1)

        surprises = (s.get("surprises") or {}).get("costs_discovered_after_moving_in") or []
        surprise_monthly = sum(
            c.get("monthly_usd") or 0 for c in surprises if isinstance(c, dict)
        )

        rows.append({
            "participant": s.get("participant"),
            "group": s.get("group"),
            "hours_spent": num(s, "search", "hours_spent"),
            "monthly_rent_usd": num(s, "what_they_signed", "monthly_rent_usd"),
            "surprise_costs": len(surprises),
            "surprise_monthly_usd": surprise_monthly or None,
            "gap_months_paid": num(s, "surprises", "gap_months_paid"),
            "actual_first_year_usd": actual,
            "predicted_first_year_usd": predicted,
            "prediction_error_pct": error_pct,
            "listing_used": (s.get("app_said") or {}).get("listing_used"),
            "corrections": len((s.get("app_said") or {}).get("corrections") or []),
            "learned_something_new": (s.get("reaction") or {}).get("learned_something_new"),
            "would_have_used_before_signing": (s.get("reaction") or {}).get("would_have_used_before_signing"),
            "would_recommend": (s.get("reaction") or {}).get("would_recommend_to_incoming_student"),
            "quote": (s.get("reaction") or {}).get("quote")
                     if (s.get("reaction") or {}).get("consented_to_anonymous_quote") else None,
        })

    errors = [r["prediction_error_pct"] for r in rows if r["prediction_error_pct"] is not None]
    hours = [r["hours_spent"] for r in rows if r["hours_spent"] is not None]
    surprises = [r["surprise_monthly_usd"] for r in rows if r["surprise_monthly_usd"]]

    summary = {
        "sessions": len(rows),
        "sample_is_small": len(rows) < 3,
        "with_a_comparable_total": len(errors),
        "prediction_error_pct": {
            "values": errors,
            "median": round(statistics.median(errors), 1) if errors else None,
            "worst_absolute": max((abs(e) for e in errors), default=None),
        },
        "hours_spent_searching": {
            "values": hours,
            "median": round(statistics.median(hours), 1) if hours else None,
        },
        "monthly_cost_discovered_after_moving_in": {
            "values": surprises,
            "median": round(statistics.median(surprises), 1) if surprises else None,
        },
        "learned_something_new": sum(1 for r in rows if r["learned_something_new"]),
        "would_have_used_before_signing": sum(1 for r in rows if r["would_have_used_before_signing"]),
        "would_recommend": sum(1 for r in rows if r["would_recommend"]),
        "quotes": [r["quote"] for r in rows if r["quote"]],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"summary": summary, "participants": rows}, indent=2), encoding="utf-8")

    print(f"{len(rows)} session(s)\n")
    head = f"{'id':<5}{'hrs':>5}{'surprise/mo':>13}{'actual yr':>12}{'predicted':>11}{'error':>9}"
    print(head)
    print("-" * len(head))
    for r in rows:
        def fmt(v, pre="", suf=""):
            return f"{pre}{v:,.0f}{suf}" if isinstance(v, (int, float)) else "-"
        print(
            f"{str(r['participant'] or '?'):<5}"
            f"{fmt(r['hours_spent']):>5}"
            f"{fmt(r['surprise_monthly_usd'], '$'):>13}"
            f"{fmt(r['actual_first_year_usd'], '$'):>12}"
            f"{fmt(r['predicted_first_year_usd'], '$'):>11}"
            f"{(f'{r['prediction_error_pct']:+.1f}%' if r['prediction_error_pct'] is not None else '-'):>9}"
        )

    print()
    if errors:
        if len(errors) < 3:
            print(f"prediction error: {', '.join(f'{e:+.1f}%' for e in errors)}")
            print("  too few to summarise - report these individually, not as an average")
        else:
            print(f"prediction error: median {statistics.median(errors):+.1f}%, "
                  f"worst {max(abs(e) for e in errors):.1f}%")
    else:
        print("No participant yet has both an actual and a predicted first-year total.")
        print("That comparison is the point of the study - chase it.")

    print()
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
