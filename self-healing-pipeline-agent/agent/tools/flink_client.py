"""
Flink REST API client.

FlinkRestClient  — real HTTP calls to a running Flink cluster.

FLINK_REST_URL is mandatory for RESTART strategy.
If not set and RESTART is attempted, a RuntimeError is raised immediately.
"""
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

FLINK_REST_URL = os.getenv("FLINK_REST_URL")
REQUEST_TIMEOUT = 10  # seconds


# ---------------------------------------------------------------------------
# Return type — structured so verification can use new_job_id
# ---------------------------------------------------------------------------

@dataclass
class RestartResult:
    action_taken: str
    new_job_id: str


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class FlinkClient(ABC):

    @abstractmethod
    def restart_job(self, job_id: str, pipeline_id: str) -> RestartResult:
        """Cancel the job and resubmit from the uploaded JAR. Returns RestartResult."""

    @abstractmethod
    def get_job_status(self, job_id: str) -> str:
        """Return the current status of a job (RUNNING, FAILED, CANCELED, etc.)."""


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
            "Run: docker compose up inside the docker/ folder."
        )

    def restart_job(self, job_id: str, pipeline_id: str) -> RestartResult:
        logger.info("[FLINK] restarting job  job_id=%s  pipeline=%s", job_id, pipeline_id)

        # Step 1 — cancel the job (Flink 1.18: PATCH /jobs/{id}?mode=cancel, no body)
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

        return RestartResult(
            action_taken=f"Restarted job {job_id} on pipeline {pipeline_id} — new job_id={new_job_id}",
            new_job_id=new_job_id,
        )

    def get_job_status(self, job_id: str) -> str:
        """Return the current Flink job status string."""
        data = self._get(f"/jobs/{job_id}")
        return data.get("state", "UNKNOWN")


# ---------------------------------------------------------------------------
# Factory — fails hard if FLINK_REST_URL not set (RESTART requires real Flink)
# ---------------------------------------------------------------------------

def get_flink_client() -> FlinkRestClient:
    """
    Return FlinkRestClient.
    Raises RuntimeError if FLINK_REST_URL is not set — RESTART requires a real Flink cluster.
    Set FLINK_REST_URL in .env and run: cd docker && docker compose up
    """
    if not FLINK_REST_URL:
        raise RuntimeError(
            "FLINK_REST_URL is not set. RESTART strategy requires a real Flink cluster. "
            "Add FLINK_REST_URL=http://localhost:8081 to .env and run: cd docker && docker compose up"
        )
    logger.info("[FLINK] using FlinkRestClient  url=%s", FLINK_REST_URL)
    return FlinkRestClient(base_url=FLINK_REST_URL)
