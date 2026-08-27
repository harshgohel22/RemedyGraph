from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.ingest import router as ingest_router
from app.db.base import Base
from app.db.session import engine


def create_app(*, init_db: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if init_db:
            Base.metadata.create_all(bind=engine)
        yield

    application = FastAPI(title="RemedyGraph", lifespan=lifespan)
    application.include_router(ingest_router)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
