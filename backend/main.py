import os
from dotenv import load_dotenv

load_dotenv() 

import asyncio
import logging
from contextlib         import asynccontextmanager
from fastapi            import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .db.database       import init_db
from .api               import traces, evals, datasets, projects, alerts, metrics, agent
from .worker.eval_worker import EvalWorker

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s  %(name)s  %(levelname)s  %(message)s"
)
logger = logging.getLogger(__name__)


class ConnectionManager:

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, project_id: str, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(project_id, []).append(ws)
        logger.info(f"WS connected: project={project_id} "
                    f"total={len(self._connections[project_id])}")

    def disconnect(self, project_id: str, ws: WebSocket):
        conns = self._connections.get(project_id, [])
        if ws in conns:
            conns.remove(ws)
        logger.info(f"WS disconnected: project={project_id} "
                    f"remaining={len(conns)}")

    async def broadcast(self, project_id: str, message: dict):
        import json
        conns   = self._connections.get(project_id, [])
        dead    = []
        payload = json.dumps(message)

        for ws in conns:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(project_id, ws)

    async def broadcast_all(self, message: dict):
        for project_id in list(self._connections.keys()):
            await self.broadcast(project_id, message)


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("TraceMind starting up...")
    await init_db()

    worker = EvalWorker()
    worker_task = asyncio.create_task(worker.run())

    worker.ws_manager = manager

    logger.info("TraceMind ready")
    yield

    logger.info("TraceMind shutting down...")
    await worker.stop()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass



app = FastAPI(
    title       = "TraceMind",
    description = "AI Evaluation-as-a-Service — know if your LLM app is working",
    version     = "0.1.0",
    lifespan    = lifespan
)

origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://tracemind.vercel.app",
    "https://tracemind-1kf0h2tak-aayush-s-projects.vercel.app",
    os.getenv("FRONTEND_URL", ""),
]
origins = [o for o in origins if o]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(traces.router,   prefix="/api/traces",   tags=["traces"])
app.include_router(evals.router,    prefix="/api/evals",    tags=["evals"])
app.include_router(datasets.router, prefix="/api/datasets", tags=["datasets"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(alerts.router,   prefix="/api/alerts",   tags=["alerts"])
app.include_router(metrics.router,  prefix="/api/metrics",  tags=["metrics"])
app.include_router(agent.router,    prefix="/api/agent",    tags=["agent"])



@app.websocket("/ws/{project_id}")
async def websocket_endpoint(ws: WebSocket, project_id: str):
    await manager.connect(project_id, ws)

    try:
        await _push_metrics_update(project_id, ws)

        while True:
            await asyncio.sleep(30)
            try:
                await ws.send_text('{"type":"ping"}')
            except Exception:
                break

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(project_id, ws)


async def _push_metrics_update(project_id: str, ws: WebSocket):
    import time
    from sqlalchemy import func, and_
    from .db.database import AsyncSessionLocal
    from .db.models   import Span

    try:
        async with AsyncSessionLocal() as db:
            since = time.time() - 86400

            result = await db.execute(
                __import__("sqlalchemy").select(
                    func.avg(Span.judge_score).label("avg_score"),
                    func.count(Span.id).label("total"),
                ).where(
                    and_(
                        Span.project_id == project_id,
                        Span.timestamp  >= since
                    )
                )
            )
            row = result.one()

            await ws.send_text(__import__("json").dumps({
                "type": "metrics_update",
                "stats": {
                    "avg_score":   round(float(row.avg_score  or 0), 2),
                    "total_calls": row.total or 0,
                    "pass_rate":   0,
                }
            }))
    except Exception:
        pass  


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "0.1.0"}