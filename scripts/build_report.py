"""Assemble report.html from the template, the measured results and the screenshots.

Every number in the report is read out of data/ and output/ here rather than typed
into the template, so the report cannot drift away from what the tests actually
measured. Images are base64-embedded, so report.html opens by double-clicking on
any machine with nothing beside it.

Run the tests and the screenshots first, then:

    .venv/Scripts/python.exe scripts/build_report.py
"""
import base64
import json
import mimetypes
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402

TEMPLATE = ROOT / "scripts" / "report_template.html"
SHOTS = ROOT / "output" / "screenshots"
OUT = ROOT / "report.html"

REPO_URL = "https://github.com/YOONSIKKKK/new-haven-rent-desk"


def load(path: Path) -> dict:
    if not path.is_file():
        sys.exit(f"Missing {path}. Run the matching script in scripts/ first.")
    return json.loads(path.read_text(encoding="utf-8"))


def embed(name: str) -> str:
    path = SHOTS / f"{name}.png"
    if not path.is_file():
        sys.exit(f"Missing screenshot {path}. Run scripts/make_screenshots.py first.")
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def diagram() -> str:
    """Pipeline diagram. Inline SVG: scales, prints, and needs no asset file."""
    rows = [
        ("screen", "strip hidden text, detect injection", False),
        ("intake", "advertisement → structured record", True),
        ("locate", "match to a census tract, offline", False),
        ("utilities", "ACS gross rent − contract rent", False),
        ("fair price", "compare like with like vs ACS", False),
        ("cost", "twelve months + calendar gap", False),
        ("rules", "Connecticut law + scam patterns", False),
        ("risk", "explain the findings", True),
        ("fit", "score against this person", False),
        ("advice", "verdict + questions to ask", True),
    ]
    top, row_h, box_h = 64, 46, 34
    left_x, box_w = 150, 190
    height = top + len(rows) * row_h + 56

    parts = [
        f'<svg viewBox="0 0 760 {height}" xmlns="http://www.w3.org/2000/svg" '
        f'font-family="Pretendard,ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif">',
        '<rect width="760" height="%d" fill="#fff"/>' % height,
        '<text x="150" y="26" font-size="11" font-weight="700" fill="#1b64da" '
        'letter-spacing="1.2">DETERMINISTIC</text>',
        '<text x="420" y="26" font-size="11" font-weight="700" fill="#191f28" '
        'letter-spacing="1.2">MODEL CALL</text>',
        f'<line x1="150" y1="36" x2="710" y2="36" stroke="#e5e8eb" stroke-width="1"/>',
        # untrusted input
        '<rect x="12" y="52" width="124" height="34" rx="7" fill="#e8f3ff" '
        'stroke="#1b64da" stroke-width="1.5" stroke-dasharray="4 3"/>',
        '<text x="74" y="68" font-size="11.5" font-weight="650" fill="#1b64da" '
        'text-anchor="middle">listing text</text>',
        '<text x="74" y="80" font-size="9.5" fill="#1b64da" text-anchor="middle">untrusted</text>',
    ]

    for i, (name, what, is_agent) in enumerate(rows):
        y = top + i * row_h
        x = 420 if is_agent else left_x
        fill = "#191f28" if is_agent else "#f4f8ff"
        stroke = "#191f28" if is_agent else "#cfe2fb"
        text_col = "#ffffff" if is_agent else "#191f28"
        sub_col = "#aebdd0" if is_agent else "#5a7694"

        if i:
            py = top + (i - 1) * row_h + box_h
            px = (420 if rows[i - 1][2] else left_x) + box_w / 2
            parts.append(
                f'<path d="M{px} {py} C{px} {py + 8} {x + box_w / 2} {y - 8} '
                f'{x + box_w / 2} {y}" stroke="#d1d6db" stroke-width="1.5" fill="none"/>'
            )
        parts += [
            f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="7" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.3"/>',
            f'<text x="{x + 12}" y="{y + 15}" font-size="12" font-weight="650" '
            f'fill="{text_col}">{name}</text>',
            f'<text x="{x + 12}" y="{y + 27}" font-size="9.5" fill="{sub_col}">{what}</text>',
        ]
        if is_agent:
            parts.append(
                f'<text x="{x + box_w + 10}" y="{y + 21}" font-size="9.5" fill="#8b95a1">'
                f'{"no tools" if name == "intake" else "reference in cached prefix"}</text>'
            )

    # The untrusted text enters at the first stage, not somewhere down the middle.
    screen_mid = top + box_h / 2
    parts.append(
        f'<path d="M136 69 C{left_x - 26} 69 {left_x - 26} {screen_mid} {left_x - 5} {screen_mid}" '
        'stroke="#1b64da" stroke-width="1.5" fill="none" stroke-dasharray="4 3" '
        'marker-end="url(#pinkarrow)"/>'
    )
    parts.insert(1, (
        '<defs><marker id="pinkarrow" viewBox="0 0 8 8" refX="7" refY="4" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        '<path d="M0 0 L8 4 L0 8 z" fill="#1b64da"/></marker></defs>'
    ))
    y_end = top + len(rows) * row_h + 10
    parts += [
        f'<rect x="420" y="{y_end}" width="{box_w}" height="{box_h}" rx="7" '
        f'fill="#e8f3ff" stroke="#1b64da" stroke-width="1.5"/>',
        f'<text x="432" y="{y_end + 15}" font-size="12" font-weight="650" fill="#1b64da">'
        'what it really costs</text>',
        f'<text x="432" y="{y_end + 27}" font-size="9.5" fill="#6d93c4">'
        'every figure computed in Python</text>',
        f'<path d="M515 {y_end - 12} L515 {y_end}" stroke="#1b64da" stroke-width="1.5"/>',
        "</svg>",
    ]
    return "".join(parts)


def collect_values() -> dict:
    """Every number both deliverables quote, computed once, in one place.

    build_slides.py imports this, so the deck and the report cannot disagree.
    """
    listings_payload = load(ROOT / "data" / "listings.json")
    baseline = load(ROOT / "data" / "rent_baseline.json")
    cost = load(ROOT / "output" / "cost_test.json")
    assumptions = load(ROOT / "data" / "cost_assumptions.json")

    listings = listings_payload["listings"]
    city = baseline["city"]
    full = cost["full"]["summary"]
    lean = cost["lean"]["summary"]
    prices = assumptions["pricing"]

    utils = sorted(
        t["implied_monthly_utilities"] for t in baseline["tracts"]
        if t.get("implied_monthly_utilities") is not None
    )

    fresh_input = full["mean_input"] - full["mean_cached"]
    c_fresh = fresh_input / 1e6 * prices["input_usd_per_1m"]
    c_cached = full["mean_cached"] / 1e6 * prices["cached_input_usd_per_1m"]
    c_out = full["mean_output"] / 1e6 * prices["output_usd_per_1m"]
    per_listing = full["steady_cost_usd"]

    no_utils = sum(1 for r in listings if not r.get("utilities_included"))
    no_deposit = sum(
        1 for r in listings
        if not any((fp or {}).get("security_deposit") for fp in r.get("floorplans") or [])
    )

    values = {
        "DATE": date.today().strftime("%d %B %Y"),
        "REPO_URL": REPO_URL,
        "CAPTURE_DATE": listings_payload["captured_at"],

        "N_LISTINGS": f"{len(listings)}",
        "N_TRACTS": f"{len(baseline['tracts'])}",
        "CITY_GROSS": f"{city['median_gross_rent']:,}",
        "CITY_CONTRACT": f"{city['median_contract_rent']:,}",
        "CITY_UTIL": f"{city['implied_monthly_utilities']}",
        "UTIL_MIN": f"{utils[0]}",
        "UTIL_MAX": f"{utils[-1]}",
        "UTIL_PCT_OF_RENT": f"{utils[-1] / city['median_contract_rent'] * 100:.0f}",
        "PCT_NO_UTILS": f"{no_utils / len(listings) * 100:.0f}",
        "PCT_NO_DEPOSIT": f"{no_deposit / len(listings) * 100:.0f}",
        "GAP_PCT": f"{(2510.28 - 2205) / 2205 * 100:.0f}",

        "SAMPLE_N": f"{cost['sample_size']}",
        "PRICE_SOURCE": cost["price_source"],
        "P_IN": f"{prices['input_usd_per_1m']:.2f}",
        "P_CACHED": f"{prices['cached_input_usd_per_1m']:.2f}",
        "P_OUT": f"{prices['output_usd_per_1m']:.2f}",
        "FRESH_INPUT": f"{fresh_input:,}",
        "MEAN_INPUT": f"{full['mean_input']:,}",
        "MEAN_CACHED": f"{full['mean_cached']:,}",
        "MEAN_OUTPUT": f"{full['mean_output']:,}",
        "TOTAL_TOKENS": f"{full['mean_input'] + full['mean_output']:,}",
        "C_FRESH": f"{c_fresh:.6f}",
        "C_CACHED": f"{c_cached:.6f}",
        "C_OUT": f"{c_out:.6f}",
        "COST_PER_LISTING": f"{per_listing:.6f}",
        "CACHE_RATE": f"{full['cache_rate_pct']}",

        "COST_PER_USER": f"{per_listing * 20:.2f}",
        "COST_100": f"{per_listing * 20 * 100:,.2f}",
        "COST_10K": f"{per_listing * 20 * 10_000:,.2f}",
        "COST_YALE": f"{per_listing * 20 * 3_000:,.0f}",

        "LEAN_INPUT": f"{lean['mean_input']:,}",
        "LEAN_CACHED": f"{lean['mean_cached']:,}",
        "LEAN_CACHE_RATE": f"{lean['cache_rate_pct']}",
        "LEAN_COST": f"{lean['steady_cost_usd']:.6f}",
        "LEAN_PCT_FEWER": f"{(1 - lean['mean_input'] / full['mean_input']) * 100:.0f}",
        "LEAN_PCT_MORE": f"{(lean['steady_cost_usd'] / per_listing - 1) * 100:.0f}",

        "MEAN_UTILS": f"{full['mean_utilities_found']}",
        "LEAN_UTILS": f"{lean['mean_utilities_found']}",
        "MEAN_UNKNOWN": f"{full['mean_unknown_fields']}",
        "LEAN_UNKNOWN": f"{lean['mean_unknown_fields']}",
        "AMBIG_PCT": f"{full['ambiguity_noted_pct']}",
        "LEAN_AMBIG_PCT": f"{lean['ambiguity_noted_pct']}",
        "RULE_FINDINGS": f"{full['mean_rule_findings']}",
        "LEAN_RULE_FINDINGS": f"{lean['mean_rule_findings']}",
        "AGENT_FINDINGS": f"{full['mean_agent_added_findings']}",
        "LEAN_AGENT_FINDINGS": f"{lean['mean_agent_added_findings']}",
        "SPEC_INCREASE": f"{(lean['mean_agent_added_findings'] / max(full['mean_agent_added_findings'], 0.01) - 1) * 100:.0f}",

        "MAX_REQ": f"{config.MAX_REQUESTS_PER_RUN}",
        "MAX_IN": f"{config.MAX_INPUT_TOKENS_PER_RUN:,}",
        "MAX_OUT": f"{config.MAX_OUTPUT_TOKENS_PER_RUN:,}",
        "MAX_CHARS": f"{config.MAX_AD_TEXT_CHARS:,}",

        "DIAGRAM": diagram(),
    }
    return values


def main() -> None:
    values = collect_values()
    per_listing = float(values["COST_PER_LISTING"])
    full_cache = values["CACHE_RATE"]
    lean_more = values["LEAN_PCT_MORE"]

    html = TEMPLATE.read_text(encoding="utf-8")

    html = re.sub(r"\{\{IMG:([a-z0-9\-]+)\}\}", lambda m: embed(m.group(1)), html)
    for key, value in values.items():
        html = html.replace("{{" + key + "}}", str(value))

    leftover = sorted(set(re.findall(r"\{\{([A-Z_:a-z0-9\-]+)\}\}", html)))
    if leftover:
        sys.exit(f"Unfilled placeholders in the template: {leftover}")

    OUT.write_text(html, encoding="utf-8")

    size_mb = OUT.stat().st_size / 1_048_576
    print(f"wrote {OUT.name}  ({size_mb:.1f} MB, images embedded)")
    print(f"  cost per listing   ${per_listing:.6f}")
    print(f"  cache rate         {full_cache}%")
    print(f"  lean costs         {lean_more}% more")
    if "YOUR-GITHUB-USERNAME" in REPO_URL:
        print()
        print("  !! REPO_URL is still a placeholder - set it in this script before submitting.")


if __name__ == "__main__":
    main()
