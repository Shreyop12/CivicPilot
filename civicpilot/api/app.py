import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..main import build_orchestrator
from .routes.agencies import router as agencies_router
from .routes.chat import router as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    components = await build_orchestrator()
    app.state.components = components
    app.state.conversations = {}
    try:
        yield
    finally:
        await components.http.aclose()


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    cors_origin = os.environ.get("CORS_ORIGIN", "http://localhost:5173")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[cors_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    app.include_router(agencies_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")

    return app


app = create_app()
