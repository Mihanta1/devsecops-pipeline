from fastapi import FastAPI

from routers import health, tasks

app = FastAPI(title="Task API")

app.include_router(health.router)
app.include_router(tasks.router)