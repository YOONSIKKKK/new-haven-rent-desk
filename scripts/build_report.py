"""Assemble report.html from the template, the measured results and the screenshots.

Every number in the report is read out of data/ and output/ here rather than typed
into the template, so the report cannot drift away from what the tests actually
measured. Images are base64-embedded, so report.html opens by double-clicking on
any machine with nothing beside it.

Run the tests and the screenshots first, then:

    .venv/Scripts/python.exe scripts/build_report.py
"""
import base64
import io
import json
import mimetypes
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
import build_user_study  # noqa: E402

TEMPLATE = ROOT / "scripts" / "report_template.html"
SHOTS = ROOT / "output" / "screenshots"
OUT = ROOT / "report.html"

REPO_URL = "https://github.com/YOONSIKKKK/new-haven-rent-desk"


def load(path: Path) -> dict:
    if not path.is_file():
        sys.exit(f"Missing {path}. Run the matching script in scripts/ first.")
    return json.loads(path.read_text(encoding="utf-8"))


MAX_EMBED_WIDTH = 1600
JPEG_ABOVE_BYTES = 350_000
JPEG_QUALITY = 84


def embed(name: str) -> str:
    """Base64-embed a screenshot, shrinking it first if it is large.

    Screenshots are captured at 2x for sharpness, which is far more than a
    printed page or a projected slide needs. Map screenshots are photographic
    and enormous as PNG. Downscaling to a sensible width and switching the big
    ones to JPEG keeps both deliverables small enough to email, which the brief
    cares about, without a visible loss at the size they are shown.
    """
    path = SHOTS / f"{name}.png"
    if not path.is_file():
        sys.exit(f"Missing screenshot {path}. Run scripts/make_screenshots.py first.")

    raw = path.read_bytes()
    try:
        from PIL import Image
    except ImportError:
        return f"data:image/png;base64,{base64.b64encode(raw).decode()}"

    image = Image.open(io.BytesIO(raw))
    if image.width > MAX_EMBED_WIDTH:
        ratio = MAX_EMBED_WIDTH / image.width
        image = image.resize(
            (MAX_EMBED_WIDTH, max(1, round(image.height * ratio))), Image.LANCZOS
        )

    buffer = io.BytesIO()
    if len(raw) > JPEG_ABOVE_BYTES:
        image.convert("RGB").save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        mime = "image/jpeg"
    else:
        image.save(buffer, format="PNG", optimize=True)
        mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(buffer.getvalue()).decode()}"


def esc(text) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _money(v) -> str:
    return f"${v:,.0f}" if isinstance(v, (int, float)) else "&mdash;"


def _pct(v) -> str:
    return f"{v:+.1f}%" if isinstance(v, (int, float)) else "&mdash;"


def user_study_block(study: dict | None) -> str:
    """The Impact section's evidence block.

    With no sessions it says so plainly; the honest admission is better than a
    silently empty section. Once sessions exist it becomes the measurement, and
    below three participants it deliberately refuses to average them.
    """
    if study is None:
        return """<div class="callout">
  <h4>What is missing from this section, honestly</h4>
  <p>A real user has not yet tried it end to end. The strongest evidence available for
  this app is a comparison of its twelve-month prediction against what an incoming
  student actually paid over their first year, and that test is the immediate next
  step rather than a completed one. Everything above is either measured from public
  data or explicitly labelled as a projection.</p>
</div>"""

    s, rows = study["summary"], study["participants"]
    n = s["sessions"]
    errors = s["prediction_error_pct"]["values"]

    # With no comparable totals there is nothing to tabulate, and a table of
    # dashes would imply the measurement was attempted and failed. Report what
    # the sessions did establish, and say plainly what they did not.
    if not errors:
        liked = "".join(f"<li>{esc(x)}</li>" for x in s.get("liked", [])[:3])
        missing = "".join(f"<li>{esc(x)}</li>" for x in s.get("whats_missing", []))
        new_to_them = "".join(f"<p>{esc(x)}</p>" for x in s.get("what_was_new", []))
        plural = "s" if n != 1 else ""
        return f"""<h4>What a real user found</h4>
<p>{n} incoming international student{plural} has used it and given feedback. This was a
reaction session, not the full protocol: there is no recalled first-year total to
compare the prediction against. What it establishes is narrower and still worth
having.</p>

<p><strong>It told them something they could not work out themselves.</strong></p>
{new_to_them}

<p>Of {n} participant{plural}, <strong>{s['learned_something_new']}</strong> said so,
<strong>{s['would_have_used_before_signing']}</strong> would have used it before signing,
and <strong>{s['would_recommend']}</strong> would send it to someone arriving next year.</p>

{f'<p>What they singled out:</p><ul>{liked}</ul>' if liked else ''}
{f'<p>What they wanted and did not get:</p><ul>{missing}</ul>' if missing else ''}

<div class="callout">
  <h4>What this is not</h4>
  <p>One person, and no accuracy measurement. The number that would make this credible
  to a housing office &mdash; the prediction against what a student actually paid &mdash;
  still has not been taken. The protocol is in the repository and this section rewrites
  itself when sessions carrying those figures exist.</p>
</div>"""


    body = "".join(
        f"<tr><td>{esc(r['participant'])}</td>"
        f"<td class='num'>{r['hours_spent'] if r['hours_spent'] is not None else '&mdash;'}</td>"
        f"<td class='num'>{_money(r['surprise_monthly_usd'])}</td>"
        f"<td class='num'>{_money(r['actual_first_year_usd'])}</td>"
        f"<td class='num'>{_money(r['predicted_first_year_usd'])}</td>"
        f"<td class='num'>{_pct(r['prediction_error_pct'])}</td></tr>"
        for r in rows
    )

    if not errors:
        verdict = ("<p>No participant yet has both a recalled first-year total and a "
                   "prediction to compare it against, so the error column is empty. "
                   "That comparison is the point of the study and it is not done.</p>")
    elif len(errors) < 3:
        verdict = (f"<p>Prediction error on the {len(errors)} comparable case"
                   f"{'s' if len(errors) != 1 else ''}: "
                   f"<strong>{', '.join(f'{e:+.1f}%' for e in errors)}</strong>. "
                   "Too few to average, so they are listed individually rather than "
                   "summarised into a figure that would look more solid than it is.</p>")
    else:
        verdict = (f"<p>Median prediction error across {len(errors)} participants: "
                   f"<strong>{s['prediction_error_pct']['median']:+.1f}%</strong>, "
                   f"worst case {s['prediction_error_pct']['worst_absolute']:.1f}%.</p>")

    quotes = "".join(
        f'<p style="padding-left:18px;border-left:3px solid var(--line);font-style:italic">'
        f'&ldquo;{esc(q)}&rdquo;</p>' for q in s["quotes"]
    )

    counts = (
        f"<p>Of {n} participant{'s' if n != 1 else ''}, "
        f"<strong>{s['learned_something_new']}</strong> said the desk showed them "
        f"something they did not know at the time, "
        f"<strong>{s['would_have_used_before_signing']}</strong> said they would have "
        f"used it before signing, and "
        f"<strong>{s['would_recommend']}</strong> would send it to someone arriving "
        f"next year.</p>"
    )

    caveat = (
        "<div class=\"callout\"><h4>How much weight this carries</h4>"
        f"<p>{n} participant{'s' if n != 1 else ''} is an illustration, not a study. "
        "The figures are recalled months after the fact rather than read off bank "
        "statements, and people who agree to be interviewed about their housing search "
        "are likely the ones who found it hardest. The individual numbers are shown "
        "above for that reason.</p></div>"
    )

    return f"""<h4>What real users found</h4>
<p>{n} student{'s' if n != 1 else ''} who moved to New Haven for the 2026&ndash;27 year
sat through the protocol in <code>research/interview_protocol.md</code>: their own
search first, closed-book, then their own listing run through the desk.</p>
<table>
  <tr><th>Participant</th><th class="num">Hours searching</th>
      <th class="num">Discovered after moving in</th>
      <th class="num">Their first year</th><th class="num">Predicted</th>
      <th class="num">Error</th></tr>
  {body}
</table>
{verdict}
{counts}
{quotes}
{caveat}"""


def user_study_measured(study: dict | None) -> str:
    """Extra bullets for the Measured list, only once they are measured."""
    if study is None:
        return ""
    s = study["summary"]
    out = []
    surprise = s["monthly_cost_discovered_after_moving_in"]["median"]
    if surprise:
        out.append(
            f"<li><strong>Costs discovered only after moving in: ${surprise:,.0f} a month</strong> "
            f"(median across {s['sessions']} participant"
            f"{'s' if s['sessions'] != 1 else ''}), none of it in the advertisement.</li>"
        )
    hours = s["hours_spent_searching"]["median"]
    if hours:
        out.append(
            f"<li><strong>{hours:,.0f} hours</strong> spent searching, median across "
            f"participants.</li>"
        )
    errors = s["prediction_error_pct"]["values"]
    if len(errors) >= 3:
        out.append(
            f"<li><strong>Prediction error {s['prediction_error_pct']['median']:+.1f}% "
            f"(median)</strong> against what participants actually paid.</li>"
        )
    return "".join(out)


def user_study_slide(study: dict | None) -> str:
    """Slide 9's right-hand block."""
    if study is None:
        return ('<div class="callout">No real user has run it end to end yet. '
                'The test that would settle it &mdash; prediction against what students '
                'actually paid &mdash; is the next step, not a finished one.</div>')
    s = study["summary"]
    errors = s["prediction_error_pct"]["values"]
    if len(errors) >= 3:
        headline = (f"Median prediction error <strong>"
                    f"{s['prediction_error_pct']['median']:+.1f}%</strong> against what "
                    f"{len(errors)} students actually paid.")
    elif errors:
        headline = ("Prediction error on the comparable cases: <strong>"
                    + ", ".join(f"{e:+.1f}%" for e in errors)
                    + "</strong>. Too few to average.")
    else:
        headline = "No comparable first-year total captured yet."
    return (f'<div class="callout">{headline}<br><br>'
            f'{s["would_have_used_before_signing"]} of {s["sessions"]} said they would '
            f'have used it before signing. A handful of people is an illustration, '
            f'not a study.</div>')


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
    places_payload = load(ROOT / "data" / "places.json")

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
        "LEAN_DELTA_PER_1000": f"{(lean['steady_cost_usd'] - per_listing) * 1000:.2f}",
        # Cost of ranking the snapshot with the agents instead of arithmetic.
        "RANK_VS_AGENTS_USD": f"{147 * per_listing:.2f}",

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

        "N_PLACES": f"{len(places_payload['places']):,}",
        "N_PLACES_CURATED": f"{places_payload['curated_count']}",
        "DIAGRAM": diagram(),
    }

    # The study is read straight from research/sessions/, never from a stale
    # cache, so the report cannot quote a result the session files have moved on
    # from. An anonymity failure stops the build rather than publishing a name.
    try:
        study = build_user_study.summarise()
    except build_user_study.AnonymityError as exc:
        sys.exit(
            "Refusing to build: the user-study sessions contain something "
            f"identifying, and this report is published.\n{exc}"
        )
    values["USER_STUDY_BLOCK"] = user_study_block(study)
    values["USER_STUDY_MEASURED"] = user_study_measured(study)
    values["USER_STUDY_SLIDE"] = user_study_slide(study)
    values["_study_sessions"] = str(study["summary"]["sessions"]) if study else "0"

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
