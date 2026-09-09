"""API routes for the dashboard."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from sparks.pipeline import run_cycle

router = APIRouter(prefix="/api")


def _db(request: Request):
    return request.app.state.db


def _settings(request: Request):
    return request.app.state.settings


@router.get("/queue")
def queue(request: Request, band: str | None = None, n: int = 50):
    db = _db(request)
    stories = db.queue_stories(limit=n, band=band)
    out = []
    for s in stories:
        judge = db.latest_judge(s.id)
        out.append({
            "id": s.id, "title": s.title, "priority": s.priority,
            "band": s.band or ("unscored" if band == "unscored" else s.band),
            "category": s.category, "status": s.status, "n_sources": s.n_sources,
            "judge": {"gist": judge.gist, "category": judge.suggested_category,
                      "rationale": judge.rationale_market_impact,
                      "scores": {"sc": judge.supply_chain_relevance,
                                 "saudi": judge.saudi_gcc_relevance,
                                 "impact": judge.market_impact,
                                 "novelty": judge.novelty}} if judge else None,
        })
    return {"stories": out, "unscored_count": db.count_unscored()}


@router.get("/stories/{story_id}")
def story_detail(request: Request, story_id: int):
    db = _db(request)
    story = db.get_story(story_id)
    if not story:
        raise HTTPException(404, "story not found")
    sources = [{"name": db.get_source(m.source_id).name,
                "url": m.url,  # LOCAL-ONLY: shown in dashboard, never published
                "local_only": True}
               for m in db.story_members(story_id)]
    judge = db.latest_judge(story_id)
    return {"story": {"id": story.id, "title": story.title, "status": story.status,
                      "priority": story.priority, "band": story.band,
                      "category": story.category, "judge_status": story.judge_status},
            "sources": sources,
            "judge": judge.__dict__ if judge else None,
            "generations": db.generations_for(story_id),
            "open_flags": db.open_flags(story_id)}


@router.post("/stories/{story_id}/select")
def select_story(request: Request, story_id: int):
    db = _db(request)
    if not db.get_story(story_id):
        raise HTTPException(404, "story not found")
    db.set_story_status(story_id, "selected")
    return {"status": "selected"}


@router.get("/sources")
def sources(request: Request):
    return {"sources": [{"id": s.id, "name": s.name, "kind": s.kind, "url": s.url,
                         "healthy": s.healthy, "enabled": s.enabled,
                         "credibility": s.credibility,
                         "category_hint": s.category_hint}
                        for s in _db(request).all_sources(enabled_only=False)]}


@router.post("/sources")
def add_source(request: Request, body: dict):
    """Add a source (or update it when the same URL already exists).
    Search sources take a free-text topic instead of a URL."""
    from sparks.models import Source
    name, kind = body.get("name"), body.get("kind")
    if not name:
        raise HTTPException(400, "name required")
    if kind not in ("rss", "html", "search"):
        raise HTTPException(400, "kind must be rss|html|search")
    if kind == "search":
        url = (body.get("topic") or body.get("url") or "").strip()
        if not url:
            raise HTTPException(400, "topic required for search sources")
    else:
        url = (body.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            raise HTTPException(400, "url must start with http:// or https://")
    db = _db(request)
    existing = db.all_sources(enabled_only=False)
    db.upsert_source(Source(
        name=name.strip(), kind=kind, url=url,
        credibility=float(body.get("credibility", 0.5) or 0.5),
        category_hint=body.get("category_hint") or None,
        link_pattern=body.get("link_pattern") or None))
    verb = "updated" if any(s.url == url for s in existing) else "added"
    return {"status": verb}


@router.post("/sources/{source_id}/toggle")
def toggle_source(request: Request, source_id: int, body: dict):
    enabled = body.get("enabled")
    if enabled is None:
        raise HTTPException(400, "enabled (bool) required")
    db = _db(request)
    if not db.get_source(source_id):
        raise HTTPException(404, "source not found")
    db.set_source_enabled(source_id, bool(enabled))
    return {"status": "enabled" if enabled else "disabled"}


@router.post("/fetch-now")
def fetch_now(request: Request):
    settings = _settings(request)
    runner = request.app.state.job_runner
    job_id = runner.submit("fetch", run_cycle, settings)
    return {"job_id": job_id}


@router.get("/jobs/{job_id}")
def job_status(request: Request, job_id: str):
    return request.app.state.job_runner.status(job_id)


@router.post("/show")
def show_window(request: Request):
    """Second app launch asks the running instance to reveal its window."""
    fn = getattr(request.app.state, "show_window", None)
    if fn is None:
        raise HTTPException(503, "no window (running outside the desktop app)")
    fn()
    return {"status": "shown"}


@router.post("/stories/{story_id}/generate")
def generate(request: Request, story_id: int, body: dict = None):
    from sparks.generate.service import GenerationService
    db = _db(request)
    if not db.get_story(story_id):
        raise HTTPException(404, "story not found")
    body = body or {}
    service = GenerationService(_settings(request), db)
    formats = tuple(body.get("formats", ["article", "linkedin"]))
    job_id = request.app.state.job_runner.submit("generate", service.generate_for_story,
                                                 story_id, formats)
    return {"job_id": job_id}


@router.post("/generations/{generation_id}/fact-check")
def fact_check(request: Request, generation_id: int):
    from sparks.factcheck.service import FactCheckService
    service = FactCheckService(_settings(request), _db(request))
    job_id = request.app.state.job_runner.submit("factcheck", service.check_generation,
                                                 generation_id)
    return {"job_id": job_id}


@router.post("/flags/{flag_id}/resolve")
def resolve_flag(request: Request, flag_id: int, body: dict):
    resolution = body.get("resolution")
    if resolution not in ("resolved_edit", "resolved_confirm"):
        raise HTTPException(400, "resolution must be resolved_edit|resolved_confirm")
    _db(request).resolve_flag(flag_id, resolution)
    return {"status": resolution}


@router.post("/stories/{story_id}/approve")
def approve(request: Request, story_id: int):
    db = _db(request)
    if not db.get_story(story_id):
        raise HTTPException(404, "story not found")
    if not db.generations_for(story_id):
        raise HTTPException(409, "no generations")
    if db.open_flags(story_id):
        raise HTTPException(409, "open flags")
    db.set_story_status(story_id, "approved")
    return {"status": "approved"}


def _first_line(text: str) -> str:
    return text.strip().split("\n", 1)[0]


@router.post("/generations/{generation_id}")
def edit_generation(request: Request, generation_id: int, body: dict):
    content = body.get("content")
    if content is None:
        raise HTTPException(400, "content required")
    _db(request).update_generation_content(generation_id, content)
    return {"status": "updated"}


@router.post("/stories/{story_id}/publish")
def publish(request: Request, story_id: int, body: dict):
    from sparks.publish.content import build_post_files, slugify
    from sparks.publish.git import GitPublisher
    db = _db(request)
    settings = _settings(request)
    story = db.get_story(story_id)
    if not story:
        raise HTTPException(404, "story not found")
    if story.status != "approved":
        raise HTTPException(409, f"story is {story.status}, must be approved")
    gens = {(g["format"], g["language"]): g for g in db.generations_for(story_id)}
    result: dict = {"destinations": {}}
    destinations = body.get("destinations", ["site"])
    if "site" in destinations:
        en = gens.get(("article", "en"))
        ar = gens.get(("article", "ar"))
        if not en:
            raise HTTPException(409, "no english article to publish")
        slug = en["seo_slug"] or slugify(story.title)
        meta = {"slug": slug,
                "title": story.title,
                "titleAr": _first_line(ar["content"]) if ar else "",
                "description": en["seo_description"] or "",
                "descriptionAr": (ar["seo_description"] or "") if ar else "",
                "category": story.category or "other",
                "tags": json.loads(en["seo_tags"] or "[]"),
                "publishedAt": datetime.now(timezone.utc).isoformat(),
                "priority": story.priority}
        publisher = GitPublisher(settings)
        sha = publisher.publish(build_post_files(meta, en["content"],
                                                 ar["content"] if ar else None),
                                f"publish: {slug}")
        url = publisher.build_url(slug)
        db.create_publication(story_id, "site", url=url, commit_sha=sha, detail="en+ar")
        db.set_story_status(story_id, "published")
        result["destinations"]["site"] = {"url": url, "commit_sha": sha}
        result["url"] = url
        result["commit_sha"] = sha
    if "linkedin" in destinations:
        db.create_publication(story_id, "linkedin", url=None, commit_sha=None,
                              detail="copied")
        result["destinations"]["linkedin"] = {"status": "copied"}
    return result


@router.get("/publications")
def publications(request: Request):
    return {"publications": _db(request).list_publications()}


@router.get("/settings-status")
def settings_status(request: Request):
    import httpx
    from sparks.config import read_secrets
    settings = _settings(request)
    secrets = read_secrets(settings.settings_path)
    ollama = False
    try:
        ollama = httpx.get(f"{settings.judge.local.ollama_url}/api/version",
                           timeout=1.5).status_code == 200
    except Exception:
        pass
    return {"has_api_key": bool(secrets.get("api_key") or settings.judge.api.api_key),
            "has_repo": bool(secrets.get("repo_url") or settings.publish.repo_url),
            "ollama": ollama,
            "schedule_hours": settings.fetch.schedule_hours,
            "default_tier": settings.judge.default_tier,
            "api_model": settings.judge.api.model,
            "local_model": settings.judge.local.model}


@router.post("/settings")
def post_settings(request: Request, body: dict):
    from sparks.config import write_secrets
    settings = _settings(request)
    allowed = ("api_key", "repo_url", "git_token", "default_tier", "api_model",
               "local_model", "schedule_hours")
    secrets = {k: body[k] for k in allowed if k in body and body[k] is not None}
    if secrets.get("default_tier") not in (None, "api", "local"):
        raise HTTPException(400, "default_tier must be api|local")
    if secrets:
        write_secrets(settings.settings_path, secrets)
        # apply immediately to the running app's settings object
        _apply_settings(settings, secrets)
    return {"status": "saved"}


def _apply_settings(settings, values: dict) -> None:
    if "api_key" in values:
        settings.judge.api.api_key = values["api_key"]
    if "repo_url" in values:
        settings.publish.repo_url = values["repo_url"]
    if "git_token" in values:
        settings.publish.token = values["git_token"]
    if values.get("default_tier") in ("api", "local"):
        settings.judge.default_tier = values["default_tier"]
    if values.get("api_model"):
        settings.judge.api.model = values["api_model"]
    if values.get("local_model"):
        settings.judge.local.model = values["local_model"]
    if values.get("schedule_hours") is not None:
        try:
            settings.fetch.schedule_hours = float(values["schedule_hours"])
        except (TypeError, ValueError):
            pass
