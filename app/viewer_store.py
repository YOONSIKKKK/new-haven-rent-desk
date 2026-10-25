"""Applications from people who want to be listed as viewers.

Kept apart from data/viewers.json on purpose. That file is curated sample data
and is committed; this one is whatever the form received, is written at runtime,
and is not. Mixing the two would mean an unvetted submission looked exactly like
a reviewed profile, which is the one thing a marketplace must not do.

Everything here arrives as `pending`, is shown with a badge saying so, and sorts
below reviewed profiles. Nothing promotes itself.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT
from .models import ViewerApplication

STORE = ROOT / "output" / "viewer_applications.json"

# A local demo, but a form that writes to disk still gets a ceiling.
MAX_STORED = 200


def _read() -> dict:
    if not STORE.is_file():
        return {"applications": []}
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"applications": []}


def _initials(name: str) -> str:
    parts = [p for p in re.split(r"\s+", name.strip()) if p]
    letters = "".join(p[0] for p in parts[:2])
    return (letters or name[:2]).upper()


def applications() -> list[dict]:
    """Stored applications, newest first, shaped like a viewer profile."""
    return list(reversed(_read().get("applications", [])))


def add(application: ViewerApplication) -> dict:
    data = _read()
    existing = data.setdefault("applications", [])

    record = {
        "id": f"p-{len(existing) + 1:03d}",
        "name": application.name.strip(),
        "initials": _initials(application.name),
        "headline": application.headline.strip(),
        "about": application.about.strip(),
        "languages": [lang.strip() for lang in application.languages if lang.strip()],
        "based_in": application.based_in.strip(),
        "years_in_new_haven": application.years_in_new_haven,
        "affiliation": application.affiliation.strip(),
        "availability": application.availability.strip(),
        "responds_in": application.responds_in.strip() or "not stated",
        "contact": application.contact.strip(),
        # Nothing is claimed on anyone's behalf. No rating, no job count, no
        # verification - those are things a review process produces, not a form.
        "verified": {"identity": False, "yale_email": False, "background_check": False},
        "rating": None,
        "reviews": 0,
        "jobs_done": 0,
        "pending": True,
        "submitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "services": [s.model_dump() for s in application.services],
    }

    existing.append(record)
    data["applications"] = existing[-MAX_STORED:]
    data["note"] = (
        "Submitted through the app's own form. Unreviewed: shown with a pending "
        "badge and sorted below the curated profiles. Not committed to the repo."
    )
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return record
