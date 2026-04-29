"""
Flink REST API client.

FlinkRestClient  — real HTTP calls to a running Flink cluster.
FlinkSimClient   — simulation fallback when FLINK_REST_URL is not set.

The executor injects the right client based on the FLINK_REST_URL env var.
"""
import logging
import os
from abc import ABC, abstractmethod

import httpx

logger = logging.getLogger(__name__)

FLINK_REST_URL = os.getenv("FLINK_REST_URL")
REQUEST_TIMEOUT = 10  # seconds


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class FlinkClient(ABC):

    @abstractmethod
    def restart_job(self, job_id: str, pipeline_id: str) -> str:
        """Cancel the job and resubmit from the uploaded JAR. Returns action description."""


# ---------------------------------------------------------------------------
# Real HTTP client
# ---------------------------------------------------------------------------

class FlinkRestClient(FlinkClient):
    """Calls the Flink REST API at FLINK_REST_URL."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def _get(self, path: str) -> dict:
        response = httpx.get(f"{self.base_url}{path}", timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()

    def _patch(self, path: str, body: dict) -> None:
        response = httpx.patch(f"{self.base_url}{path}", json=body, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

    def _delete(self, path: str) -> None:
        response = httpx.delete(f"{self.base_url}{path}", timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

    def _post(self, path: str, body: dict) -> dict:
        response = httpx.post(f"{self.base_url}{path}", json=body, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()

    def _find_jar_id(self) -> str:
        """Discover the uploaded StateMachineExample JAR id at runtime."""
        data = self._get("/jars")
        for jar in data.get("files", []):
            if "StateMachine" in jar.get("name", ""):
                jar_id = jar["id"]
                logger.info("[FLINK] found JAR  id=%s", jar_id)
                return jar_id
        raise RuntimeError(
            "StateMachineExample JAR not found in Flink. "
            "Run: docker compose up  inside the docker/ folder."
        )

    def restart_job(self, job_id: str, pipeline_id: str) -> str:
        logger.info("[FLINK] restarting job  job_id=%s  pipeline=%s", job_id, pipeline_id)

        # Step 1 — cancel the job using the real Flink job ID from metrics
        # Flink 1.18: PATCH /jobs/{id}?mode=cancel  (no body)
        logger.info("[FLINK] cancelling job %s ...", job_id)
        self._patch(f"/jobs/{job_id}?mode=cancel", {})
        logger.info("[FLINK] job %s cancelled", job_id)

        # Step 2 — discover JAR id
        jar_id = self._find_jar_id()

        # Step 3 — resubmit
        logger.info("[FLINK] resubmitting from JAR %s ...", jar_id)
        result = self._post(f"/jars/{jar_id}/run", {})
        new_job_id = result.get("jobid", "unknown")
        logger.info("[FLINK] job resubmitted  new_job_id=%s", new_job_id)

        return (
            f"Restarted job {job_id} on pipeline {pipeline_id} — "
            f"new job_id={new_job_id}"
        )


# ---------------------------------------------------------------------------
# Simulation fallback
# ---------------------------------------------------------------------------

class FlinkSimClient(FlinkClient):
    """Returns a descriptive string — no real API calls. Used when FLINK_REST_URL is not set."""

    def restart_job(self, job_id: str, pipeline_id: str) -> str:
        logger.info("[FLINK] simulation mode — FLINK_REST_URL not set")
        return f"Restarted job {job_id} on pipeline {pipeline_id} (simulated)"


# ---------------------------------------------------------------------------
# Factory — called by executor
# ---------------------------------------------------------------------------

def get_flink_client() -> FlinkClient:
    """Return the appropriate client based on environment configuration."""
    if FLINK_REST_URL:
        logger.info("[FLINK] using FlinkRestClient  url=%s", FLINK_REST_URL)
        return FlinkRestClient(base_url=FLINK_REST_URL)
    logger.info("[FLINK] FLINK_REST_URL not set — using FlinkSimClient")
    return FlinkSimClient()
