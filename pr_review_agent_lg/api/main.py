"""
FastAPI application entry point.
"""
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from api.routes.reviews import router as reviews_router
from models.db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)

app = FastAPI(title="PR Review Agent — LangGraph Edition")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

app.include_router(reviews_router)

init_db()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")
