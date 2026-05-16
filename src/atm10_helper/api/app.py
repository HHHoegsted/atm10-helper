from __future__ import annotations

from fastapi import FastAPI

from atm10_helper.api.routes import health, next_steps, progress


def create_app() -> FastAPI:
    app = FastAPI(
        title="ATM10 Helper API",
        version="0.2.0",
        description="Read-only local API for ATM10 quest and progression helper data.",
    )

    app.include_router(health.router)
    app.include_router(progress.router)
    app.include_router(next_steps.router)

    return app