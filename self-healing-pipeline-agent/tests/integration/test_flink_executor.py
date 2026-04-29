"""
Integration tests for the Flink executor.

These tests hit a REAL Flink cluster running in Docker.
They are skipped automatically when FLINK_REST_URL is not set.

To run:
  cd docker && docker compose up -d
  cd ..
  FLINK_REST_URL=http://localhost:8081 uv run pytest tests/integration/ -v
"""
import os
import pytest
from agent.tools.flink_client import FlinkRestClient, FlinkSimClient, get_flink_client

FLINK_REST_URL = os.getenv("FLINK_REST_URL")

# Skip all tests in this file if Flink is not running
pytestmark = pytest.mark.skipif(
    not FLINK_REST_URL,
    reason="FLINK_REST_URL not set — start Flink with: cd docker && docker compose up -d",
)


# ---------------------------------------------------------------------------
# FlinkRestClient unit tests (real HTTP, no agent state needed)
# ---------------------------------------------------------------------------

def test_flink_is_reachable():
    """Flink REST API responds to /config."""
    import httpx
    response = httpx.get(f"{FLINK_REST_URL}/config", timeout=5)
    assert response.status_code == 200


def test_jar_is_uploaded():
    """StateMachineExample JAR is present after docker compose up."""
    import httpx
    response = httpx.get(f"{FLINK_REST_URL}/jars", timeout=5)
    jars = response.json().get("files", [])
    names = [j.get("name", "") for j in jars]
    assert any("StateMachine" in name for name in names), (
        f"StateMachineExample JAR not found. Available: {names}"
    )


def test_job_is_running():
    """At least one job is in RUNNING state after docker compose up."""
    import httpx
    response = httpx.get(f"{FLINK_REST_URL}/jobs", timeout=5)
    jobs = response.json().get("jobs", [])
    running = [j for j in jobs if j.get("status") == "RUNNING"]
    assert len(running) > 0, f"No running jobs found. Jobs: {jobs}"


def test_restart_job_calls_flink():
    """FlinkRestClient.restart_job cancels and resubmits the job successfully."""
    import httpx

    # Get a running job to restart
    response = httpx.get(f"{FLINK_REST_URL}/jobs", timeout=5)
    jobs = response.json().get("jobs", [])
    running = [j for j in jobs if j.get("status") == "RUNNING"]
    assert running, "No running jobs to restart — run docker compose up first"

    job_id = running[0]["id"]
    client = FlinkRestClient(base_url=FLINK_REST_URL)

    action = client.restart_job(job_id=job_id, pipeline_id="test-pipeline")

    assert "Restarted job" in action
    assert job_id in action
    assert "new_job_id=" in action


# ---------------------------------------------------------------------------
# Factory test
# ---------------------------------------------------------------------------

def test_get_flink_client_returns_rest_client_when_url_set():
    """get_flink_client() returns FlinkRestClient when FLINK_REST_URL is set."""
    client = get_flink_client()
    assert isinstance(client, FlinkRestClient)
