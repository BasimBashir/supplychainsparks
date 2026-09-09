"""JudgeService: tier selection, api->local fallback, unscored marking."""
from __future__ import annotations

import logging

from sparks.config import Settings
from sparks.context import story_context
from sparks.db import Database
from sparks.judge.api import ApiJudge
from sparks.judge.local import OllamaJudge
from sparks.judge.schema import PROMPT_VERSION, JudgeError

log = logging.getLogger(__name__)


class JudgeService:
    def __init__(self, settings: Settings, db: Database,
                 api_judge: ApiJudge | None = None,
                 local_judge: OllamaJudge | None = None):
        self.settings = settings
        self.db = db
        self.api_judge = api_judge or ApiJudge(settings.judge.api)
        self.local_judge = local_judge or OllamaJudge(settings.judge.local)

    def _context_for(self, story):
        return story_context(self.db, story)

    def _tier_order(self) -> list[tuple[str, object]]:
        order = []
        default, other = "api", "local"
        if self.settings.judge.default_tier == "local":
            default, other = "local", "api"
        order.append((default, getattr(self, f"{default}_judge")))
        if self.settings.judge.local.enabled:
            order.append((other, getattr(self, f"{other}_judge")))
        seen: set[str] = set()
        unique = []
        for tier, judge in order:
            if tier not in seen and judge is not None:
                unique.append((tier, judge))
                seen.add(tier)
        return unique

    def judge_story(self, story_id: int) -> str:
        pending = [s for s in self.db.pending_stories() if s.id == story_id]
        if not pending:
            story_row = self.db.queue_stories(10_000)
            pending = [s for s in story_row if s.id == story_id]
        if not pending:
            return "unscored"
        try:
            ctx = self._context_for(pending[0])
        except ValueError as exc:
            log.warning("story %s cannot be judged: %s", story_id, exc)
            self.db.set_story_judge_status(story_id, "unscored")
            return "unscored"
        for tier, judge in self._tier_order():
            try:
                output = judge.judge(ctx, settings=self.settings)
            except JudgeError as exc:
                log.warning("story %s judge failed on %s tier: %s", story_id, tier, exc)
                continue
            self.db.save_judge_score(story_id, tier=tier, model=self._model_for(tier),
                                     prompt_version=PROMPT_VERSION, output=output)
            self.db.set_story_judge_status(story_id, tier)
            return tier
        log.warning("story %s left unscored: no judge tier succeeded "
                    "(check api key / ollama model)", story_id)
        self.db.set_story_judge_status(story_id, "unscored")
        return "unscored"

    def _model_for(self, tier: str) -> str:
        if tier == "api":
            return self.settings.judge.api.model
        return self.settings.judge.local.model

    def judge_pending(self, limit: int | None = None) -> tuple[int, int]:
        judged = unscored = 0
        for story in self.db.pending_stories(limit=limit):
            try:
                result = self.judge_story(story.id)
            except Exception:
                # one broken story must never kill the cycle for all others
                log.exception("story %s judge raised unexpectedly", story.id)
                self.db.set_story_judge_status(story.id, "unscored")
                result = "unscored"
            if result == "unscored":
                unscored += 1
            else:
                judged += 1
        return judged, unscored
