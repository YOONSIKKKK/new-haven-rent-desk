"""Assemble slides.html from the template, the measured results and the screenshots.

Imports collect_values() from build_report.py, so the deck and the report quote the
same numbers from the same source. reveal.js loads from a CDN; the screenshots and
the diagram are base64-embedded, so the file survives being emailed.

    .venv/Scripts/python.exe scripts/build_slides.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_report import collect_values, embed  # noqa: E402

TEMPLATE = ROOT / "scripts" / "slides_template.html"
OUT = ROOT / "slides.html"
MAX_SLIDES = 10


def main() -> None:
    values = collect_values()
    html = TEMPLATE.read_text(encoding="utf-8")

    html = re.sub(r"\{\{IMG:([a-z0-9\-]+)\}\}", lambda m: embed(m.group(1)), html)
    for key, value in values.items():
        html = html.replace("{{" + key + "}}", str(value))

    leftover = sorted(set(re.findall(r"\{\{([A-Z_:a-z0-9\-]+)\}\}", html)))
    if leftover:
        sys.exit(f"Unfilled placeholders in the slide template: {leftover}")

    slides = len(re.findall(r"<section", html))
    if slides > MAX_SLIDES:
        sys.exit(f"{slides} slides - the brief allows {MAX_SLIDES}.")

    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.name}  ({OUT.stat().st_size / 1_048_576:.1f} MB)")
    print(f"  {slides} slides (limit {MAX_SLIDES})")
    print("  reveal.js from CDN; images embedded")
    if "YOUR-GITHUB-USERNAME" in values["REPO_URL"]:
        print()
        print("  !! REPO_URL is still a placeholder - set it in build_report.py.")


if __name__ == "__main__":
    main()
