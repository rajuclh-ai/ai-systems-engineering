"""
Flask app — PR Review Agent
Routes:
  GET  /          → input form
  POST /review    → run pipeline, render results
"""

import asyncio
import logging
import os
from flask import Flask, render_template, request
from dotenv import load_dotenv, find_dotenv

from utils.github import fetch_pr_diff
from supervisor.pipeline import run_pipeline

load_dotenv(find_dotenv())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/review", methods=["POST"])
def review():
    pr_url = request.form.get("pr_url", "").strip()
    raw_diff = request.form.get("raw_diff", "").strip()
    error = None
    diff = None

    if pr_url:
        logger.info(f"Fetching diff for PR: {pr_url}")
        try:
            diff = fetch_pr_diff(pr_url)
            logger.info(f"Diff fetched — {len(diff)} chars")
        except ValueError as e:
            error = str(e)
    elif raw_diff:
        diff = raw_diff
        logger.info(f"Using raw diff — {len(diff)} chars")
    else:
        error = "Please provide a GitHub PR URL or paste a diff."

    if error:
        return render_template("index.html", error=error)

    try:
        agent_results, critic_report, total_tokens = asyncio.run(run_pipeline(diff))
    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        return render_template("index.html", error=f"Pipeline error: {str(e)}")

    agents_map = {r.agent: r for r in agent_results}

    return render_template(
        "index.html",
        report=critic_report,
        agents_map=agents_map,
        pr_url=pr_url or None,
        total_tokens=total_tokens,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5002)
