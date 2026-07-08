import json
import asyncio
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from bot.config.settings import settings
from bot.database.db import database
from bot.deployment.engine import deployment_engine
from railway.token_manager import token_manager

logger = logging.getLogger(__name__)

active_connections: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.connect()
    logger.info("API server started")
    yield
    await database.close()
    logger.info("API server stopped")


app = FastAPI(
    title="Python Bot Cloud API",
    version=settings.BOT_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "name": "Python Bot Cloud",
        "version": settings.BOT_VERSION,
        "status": "running",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "database": "connected",
        "deployments_active": await database.count_active_deployments(),
        "total_users": await database.count_users(),
    }


@app.get("/stats")
async def stats():
    return {
        "total_users": await database.count_users(),
        "active_deployments": await database.count_active_deployments(),
        "total_deployments": await database.count_total_deployments(),
        "active_tokens": await database.count_active_tokens(),
    }


@app.get("/deployments/{user_id}")
async def get_user_deployment(user_id: int):
    dep = await database.get_user_deployment(user_id)
    if not dep:
        return {"deployment": None}
    return {
        "deployment": {
            "id": dep.get("deployment_id"),
            "status": dep.get("status"),
            "framework": dep.get("framework"),
            "url": dep.get("url"),
            "created_at": dep.get("created_at"),
        }
    }


@app.websocket("/ws/{deployment_id}")
async def websocket_endpoint(websocket: WebSocket, deployment_id: str):
    await websocket.accept()
    active_connections[deployment_id] = websocket

    terminal = deployment_engine.get_terminal(deployment_id)
    terminal.subscribe(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
            elif data == "logs":
                logs = await deployment_engine.get_deployment_logs(deployment_id)
                await websocket.send_text(json.dumps({"type": "logs", "data": logs}))
            elif data == "stats":
                dep = await database.get_deployment(deployment_id)
                if dep:
                    import time
                    stats = {
                        "type": "stats",
                        "status": dep.get("status"),
                        "uptime": time.time() - dep.get("created_at", time.time()),
                        "url": dep.get("url", ""),
                        "restart_count": dep.get("restart_count", 0),
                    }
                    await websocket.send_text(json.dumps(stats))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        terminal.unsubscribe(websocket)
        active_connections.pop(deployment_id, None)


@app.get("/terminal/{deployment_id}")
async def get_terminal_logs(deployment_id: str):
    terminal = deployment_engine.get_terminal(deployment_id)
    return {"logs": terminal.get_recent(200)}
