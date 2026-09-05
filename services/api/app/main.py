from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.audit import router as audit_router
from app.api.routes.claims import router as claims_router
from app.api.routes.demo import router as demo_router
from app.api.routes.evaluate import router as evaluate_router
from app.api.routes.ingest import router as ingest_router
from app.api.routes.ledger import router as ledger_router
from app.api.routes.linkage import router as linkage_router
from app.api.routes.refunds import router as refunds_router
from app.api.routes.retrieval import router as retrieval_router
from app.api.routes.webhooks import router as webhooks_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine


def create_app(*, init_db: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if init_db:
            Base.metadata.create_all(bind=engine)
        yield

    application = FastAPI(title="RemedyGraph", lifespan=lifespan)
    origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(ingest_router)
    application.include_router(claims_router)
    application.include_router(retrieval_router)
    application.include_router(linkage_router)
    application.include_router(evaluate_router)
    application.include_router(ledger_router)
    application.include_router(refunds_router)
    application.include_router(webhooks_router)
    application.include_router(audit_router)
    application.include_router(demo_router)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
