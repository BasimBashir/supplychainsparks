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
            "id": s.id, "title": s.title, "priority": s.priority, "band": s.band,
            "category": s.category, "status": s.status, "n_sources": s.n_sources,
            "judge": {"gist": judge.gist, "category": judge.suggested_category,
                      "rationale": judge.rationale_market_impact,
                      "scores": {"sc": judge.supply_chain_relevance,
                                 "saudi": judge.saudi_gcc_relevance,
                                 "impact": judge.market_impact,
                                 "novelty": judge.novelty}} if judge else None,
        })
    return {"stories": out}


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
    return {"sources": [{"name": s.name, "kind": s.kind, "url": s.url,
                         "healthy": s.healthy, "enabled": s.enabled,
                         "credibility": s.credibility}
                        for s in _db(request).all_sources(enabled_only=False)]}


@router.post("/fetch-now")
def fetch_now(request: Request):
    settings = _settings(request)
    runner = request.app.state.job_runner
    job_id = runner.submit("fetch", run_cycle, settings)
    return {"job_id": job_id}


@router.get("/jobs/{job_id}")
def job_status(request: Request, job_id: str):
    return request.app.state.job_runner.status(job_id)


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
            "schedule_hours": settings.fetch.schedule_hours}


@router.post("/settings")
def post_settings(request: Request, body: dict):
    from sparks.config import write_secrets
    settings = _settings(request)
    secrets = {}
    if "api_key" in body:
        secrets["api_key"] = body["api_key"]
    if "repo_url" in body:
        secrets["repo_url"] = body["repo_url"]
    if "git_token" in body:
        secrets["git_token"] = body["git_token"]
    if secrets:
        write_secrets(settings.settings_path, secrets)
    return {"status": "saved"}
