from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.payments import router as payments_router
from app.core.db import engine

SERVICE_NAME = "Payments Service"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


app = FastAPI(title=SERVICE_NAME, version="0.1.0", lifespan=lifespan)
app.include_router(payments_router)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": SERVICE_NAME}