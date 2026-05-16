from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from atm10_helper.api.routes import health, next_steps, progress


def create_app() -> FastAPI:
    app = FastAPI(
        title="ATM10 Helper API",
        version="0.2.0",
        description="Read-only local API for ATM10 quest and progression helper data.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:8021",
            "http://localhost:8021",
            "http://192.168.0.155:8021",
        ],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(progress.router)
    app.include_router(next_steps.router)

    return app