"""
FastAPI application entry point.
Mounts incident and approval routes.
"""
from dotenv import load_dotenv
load_dotenv()  # Load .env before any LLM clients are instantiated

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s — %(message)s")

from fastapi import FastAPI
from api.routes.incidents import router as incidents_router
from api.routes.approval import router as approval_router

app = FastAPI(
    title="Self-Healing Pipeline Agent",
    description="Autonomous pipeline failure diagnosis and remediation",
    version="0.1.0",
)

app.include_router(incidents_router)
app.include_router(approval_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
