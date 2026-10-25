"""FastAPI app.

Serves a static front end and three JSON endpoints. No build step, no node,
no database - the whole thing starts with one command and reads committed
JSON from data/.
"""
from __future__ import annotations

import traceback
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import data_store as store
from . import recommend as rec
from . import viewer_store
from . import tools
from .config import MAX_AD_TEXT_CHARS, ROOT, key_status
from .models import (
    Evaluation,
    RecommendationResult,
    RenterProfile,
    ViewerApplication,
)
from .orchestrator import evaluate

STATIC_DIR = ROOT / "static"

app = FastAPI(title="New Haven Rent Desk", version="1.0")


class EvaluateRequest(BaseModel):
    ad_text: str = Field("", max_length=MAX_AD_TEXT_CHARS * 2)
    listing_id: int | None = None
    image_data_url: str | None = None
    profile: RenterProfile = Field(default_factory=RenterProfile)


@app.get("/api/status")
def status() -> dict:
    out = {"keys": key_status()}
    try:
        out["dataset"] = store.dataset_summary()
        out["ready"] = out["keys"]["has_portkey_key"] or out["keys"]["has_openai_key"]
    except FileNotFoundError as exc:
        out["dataset_error"] = str(exc)
        out["ready"] = False
    return out


@app.get("/api/listings")
def listings(
    max_rent: int | None = None,
    min_bedrooms: int | None = None,
    max_walk_minutes: int | None = None,
    limit: int = 60,
) -> dict:
    rows = tools.search_listings(
        max_rent=max_rent,
        min_bedrooms=min_bedrooms,
        max_walk_minutes=max_walk_minutes,
        limit=min(limit, 200),
    )
    slim = [{
        "id": r["id"],
        "address": r["address"],
        "rent_min": r.get("rent_min"),
        "rent_max": r.get("rent_max"),
        "bed_min": r.get("bed_min"),
        "bed_max": r.get("bed_max"),
        "walk_minutes_to_campus": r.get("walk_minutes_to_campus"),
        "utilities_included": r.get("utilities_included") or [],
        "census_tract": r.get("census_tract"),
        "unknown_count": sum(
            1 for key in ("sq_footage", "security_deposit", "available_date")
            if not any((fp or {}).get(key) for fp in r.get("floorplans") or [])
        ),
    } for r in rows]
    return {"count": len(slim), "listings": slim}


class RecommendRequest(BaseModel):
    destination: str = Field("", max_length=300)
    profile: RenterProfile = Field(default_factory=RenterProfile)
    max_rent: int | None = None
    min_bedrooms: int | None = None
    limit: int = 12


@app.get("/api/guide")
def guide() -> dict:
    """Content for the intro dialogue. Data, so it can be corrected without a deploy."""
    return store.guide()


@app.get("/api/viewers")
def viewers(service: str = "", language: str = "", max_price: int | None = None) -> dict:
    """Who will go and look at the apartment for you.

    Sample profiles for now. Real providers would replace data/viewers.json;
    nothing about them is hard-coded here.
    """
    payload = store.viewers()
    # Curated profiles first, then whatever the form has received. An
    # application never outranks a reviewed profile.
    people = payload["viewers"] + viewer_store.applications()

    if service:
        people = [v for v in people if any(s["code"] == service for s in v["services"])]
    if language:
        want = language.strip().lower()
        people = [v for v in people
                  if any(want == lang.lower() for lang in v["languages"])]
    if max_price is not None:
        # The price filter has to apply to the service being asked for. Checking
        # it against any service lets a $140 lease review through because the
        # same person also does a $55 walkthrough.
        people = [
            v for v in people
            if any(s["price_usd"] <= max_price
                   for s in v["services"]
                   if not service or s["code"] == service)
        ]

    def cheapest(v):
        relevant = [s for s in v["services"] if not service or s["code"] == service]
        return min(s["price_usd"] for s in relevant or v["services"])

    people = sorted(
        people,
        key=lambda v: (v.get("pending", False), -(v.get("rating") or 0), cheapest(v)),
    )
    languages = sorted({lang for v in payload["viewers"] for lang in v["languages"]})

    return {
        "status": payload["status"],
        "note": payload["note"],
        "disclosure": payload["disclosure"],
        "service_types": payload["service_types"],
        "languages": languages,
        "count": len(people),
        "total": len(payload["viewers"]) + len(viewer_store.applications()),
        "pending": sum(1 for v in people if v.get("pending")),
        "viewers": people,
    }


@app.post("/api/viewers/apply")
def apply_as_viewer(application: ViewerApplication) -> dict:
    """List yourself as someone who will view apartments for other people.

    Stored apart from the curated profiles and shown as pending. Nothing here
    claims a rating, a job count or a verification - those are outputs of a
    review process, not of a form.
    """
    record = viewer_store.add(application)
    return {
        "ok": True,
        "id": record["id"],
        "status": "pending review",
        "message": (
            "Saved. Your profile is listed as pending, below the reviewed ones, "
            "until someone checks it. Nothing was published on your behalf."
        ),
    }


@app.get("/api/destinations")
def destinations(q: str = "", limit: int = 10) -> dict:
    """Type-ahead over the committed gazetteer. No network call, no key.

    With no query it returns the handful of places most people want, so the box
    is useful before anyone types.
    """
    if q.strip():
        hits = rec.search_places(q, limit=max(1, min(limit, 25)))
    else:
        hits = [p for p in rec.places() if p["source"] == "curated"][:limit]
    return {
        "total_known": len(rec.places()),
        "destinations": [
            {"label": p["label"], "address": p.get("address"), "category": p["category"]}
            for p in hits
        ],
    }


@app.post("/api/recommend", response_model=RecommendationResult)
def recommend(req: RecommendRequest) -> RecommendationResult:
    """Rank the whole snapshot against one person's constraints.

    No model call, by design: see the note in app/recommend.py. The expensive
    analysis is spent on the listing the person then chooses to open.
    """
    return rec.recommend(
        profile=req.profile,
        destination_text=req.destination,
        limit=max(1, min(req.limit, 50)),
        max_rent=req.max_rent,
        min_bedrooms=req.min_bedrooms,
    )


@app.get("/api/listings/{listing_id}")
def listing_detail(listing_id: int) -> dict:
    for r in store.listings():
        if r.get("id") == listing_id:
            return r
    raise HTTPException(status_code=404, detail="No listing with that id in the snapshot")


@app.post("/api/evaluate", response_model=Evaluation)
def run_evaluation(req: EvaluateRequest) -> Evaluation:
    ad_text = req.ad_text or ""

    if req.listing_id is not None and not ad_text.strip():
        row = next((r for r in store.listings() if r.get("id") == req.listing_id), None)
        if row is None:
            raise HTTPException(status_code=404, detail="No listing with that id in the snapshot")
        ad_text = row.get("raw_ad_text") or ""

    if not ad_text.strip() and not req.image_data_url:
        raise HTTPException(
            status_code=400,
            detail="Paste the listing text, pick one from the snapshot, or upload a screenshot.",
        )

    try:
        return evaluate(
            ad_text=ad_text,
            profile=req.profile,
            listing_id=req.listing_id,
            image_data_url=req.image_data_url,
        )
    except RuntimeError as exc:
        # Missing key: the most likely failure on someone else's machine.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc


@app.exception_handler(404)
def spa_fallback(request, exc):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    return FileResponse(STATIC_DIR / "index.html")


if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
