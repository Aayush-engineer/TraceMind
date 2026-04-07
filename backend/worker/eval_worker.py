import asyncio
import logging
from datetime import datetime

from ..db.database      import get_sync_db
from ..db.models        import EvalRun, Span, Alert
from ..core.regression_detector import RegressionDetector

logger   = logging.getLogger(__name__)
detector = RegressionDetector()


class EvalWorker:

    POLL_INTERVAL       = 10   
    SCORE_BATCH_SIZE    = 20   
    MAX_RETRIES         = 3    

    def __init__(self):
        self._running  = False
        self._task     = None

    async def _broadcast(self, project_id: str, message: dict):
        if self.ws_manager:
            await self.ws_manager.broadcast(project_id, message)

    async def run(self):
        self._running = True
        logger.info("EvalWorker started")

        while self._running:
            try:
                await self._tick()
            except Exception:
                logger.exception("EvalWorker tick failed")

            await asyncio.sleep(self.POLL_INTERVAL)

    async def stop(self):
        self._running = False
        logger.info("EvalWorker stopped")


    async def _tick(self):
        await self._process_pending_runs()
        await self._score_unscored_spans()
        await self._check_regressions()

    async def _process_pending_runs(self):
        loop = asyncio.get_running_loop()

        def _find_pending():
            db = get_sync_db()
            try:
                return db.query(EvalRun).filter(
                    EvalRun.status == "pending"
                ).limit(5).all()
            finally:
                db.close()

        pending = await loop.run_in_executor(None, _find_pending)

        for run in pending:
            logger.info(f"Worker picking up pending run {run.id}")
            await loop.run_in_executor(None, self._mark_run_running, run.id)

    def _mark_run_running(self, run_id: str):
        db = get_sync_db()
        try:
            run = db.query(EvalRun).filter_by(id=run_id).first()
            if run and run.status == "pending":
                run.status     = "running"
                run.started_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()


    async def _score_unscored_spans(self):
        loop = asyncio.get_running_loop()

        def _fetch_unscored():
            db = get_sync_db()
            try:
                return db.query(Span).filter(
                    Span.judge_score == None,  # noqa: E711
                    Span.output      != "",
                    Span.input       != "",
                    Span.error       == ""
                ).limit(self.SCORE_BATCH_SIZE).all()
            finally:
                db.close()

        spans = await loop.run_in_executor(None, _fetch_unscored)

        if not spans:
            return

        logger.info(f"Worker scoring {len(spans)} unscored spans")

        for span in spans:
            try:
                score = await self._score_span(span.input, span.output)
                await loop.run_in_executor(
                    None, self._save_score, span.id, score
                )
            except Exception:
                logger.exception(f"Failed to score span {span.id}")

    async def _score_span(self, input_text: str, output: str) -> float:
        from ..core.llm import chat
        loop = asyncio.get_running_loop()

        def _call():
            result = chat(
                messages = [{"role": "user", "content":
                    f"Input: {input_text[:300]}\nOutput: {output[:300]}\n"
                    f"Rate the quality of this AI response from 1-10. "
                    f"Return ONLY a single number."}],
                system     = "You rate AI response quality. Return ONLY a number 1-10.",
                model      = "fast",
                max_tokens = 5
            )
            return min(10.0, max(0.0, float(result.strip())))

        return await loop.run_in_executor(None, _call)

    def _save_score(self, span_id: str, score: float):
        db = get_sync_db()
        try:
            span = db.query(Span).filter_by(id=span_id).first()
            if span:
                span.judge_score = score
                db.commit()
        finally:
            db.close()

    async def _check_regressions(self):
        loop = asyncio.get_running_loop()

        def _get_metrics():
            import time
            db = get_sync_db()
            try:
                now      = time.time()
                hour_ago = now - 3600
                week_ago = now - 604800

                from sqlalchemy import func
                recent = db.query(
                    func.avg(Span.judge_score).label("avg_score"),
                    func.count(Span.id).label("count"),
                    func.avg(Span.duration_ms).label("avg_latency_ms"),
                ).filter(
                    Span.timestamp   >= hour_ago,
                    Span.judge_score != None  
                ).one()

                baseline = db.query(
                    func.avg(Span.judge_score).label("avg_score"),
                    func.avg(Span.duration_ms).label("avg_latency_ms"),
                ).filter(
                    Span.timestamp   >= week_ago,
                    Span.timestamp   <  hour_ago,
                    Span.judge_score != None  
                ).one()

                error_count = db.query(func.count(Span.id)).filter(
                    Span.timestamp != "",
                    Span.timestamp >= hour_ago,
                    Span.error     != ""
                ).scalar() or 0

                total_count = recent.count or 0
                error_rate  = error_count / total_count if total_count > 0 else 0

                return {
                    "recent": {
                        "avg_score":      float(recent.avg_score    or 0),
                        "avg_latency_ms": float(recent.avg_latency_ms or 0),
                        "error_rate":     error_rate,
                        "count":          total_count,
                    },
                    "baseline": {
                        "avg_score":      float(baseline.avg_score    or 0),
                        "avg_latency_ms": float(baseline.avg_latency_ms or 0),
                    }
                }
            finally:
                db.close()

        metrics = await loop.run_in_executor(None, _get_metrics)

        if metrics["recent"]["count"] < 10:
            return

        regressions = await detector.check_all(
            metrics["recent"],
            metrics["baseline"]
        )

        if regressions:
            await loop.run_in_executor(
                None, self._save_alerts, regressions
            )

    def _save_alerts(self, regressions):
        db = get_sync_db()
        try:
            for reg in regressions:
                existing = db.query(Alert).filter(
                    Alert.type     == reg.type,
                    Alert.resolved == False  
                ).first()

                if not existing:
                    alert = Alert(
                        project_id   = "system",
                        type         = reg.type,
                        severity     = reg.severity,
                        message      = reg.message,
                        metric_value = reg.metric,
                        threshold    = reg.baseline,
                    )
                    db.add(alert)
                    logger.warning(f"Alert fired: [{reg.severity}] {reg.message}")

            db.commit()
            import asyncio
            for reg in regressions:
                asyncio.create_task(self._broadcast("system", {
                    "type":    "new_alert",
                    "alert": {
                        "type":     reg.type,
                        "severity": reg.severity,
                        "message":  reg.message,
                    }
                }))
        finally:
            db.close()