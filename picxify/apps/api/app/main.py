from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import SERVICE_VERSION, settings
from app.routers import dashboards, datasets, health, jobs, shares, uploads, users, workspaces

app = FastAPI(
    title="Picxify API",
    version=SERVICE_VERSION,
    docs_url="/docs" if settings.app_env != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboards.router)
app.include_router(datasets.router)
app.include_router(health.router)
app.include_router(jobs.router)
app.include_router(shares.router)
app.include_router(uploads.router)
app.include_router(users.router)
app.include_router(workspaces.router)
