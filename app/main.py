from contextlib import asynccontextmanager

from fastapi import FastAPI

import storage
from routers import health, tasks


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.init_db()
    yield


app = FastAPI(
    title="Task API",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(tasks.router)