# Flink Docker Setup

Runs a local Flink cluster with the StateMachineExample job for testing real RESTART execution.

---

## Start Flink

```bash
cd docker
docker compose up -d
```

This starts:
- `flink-jobmanager` — Flink master, REST API on http://localhost:8081
- `flink-taskmanager` — Flink worker
- `flink-init` — uploads the StateMachineExample JAR and submits the job, then exits

Wait ~15 seconds for init to complete, then verify:

```bash
# Flink UI
open http://localhost:8081

# Or via curl
curl http://localhost:8081/jobs
```

You should see one job in `RUNNING` state.

---

## Enable real RESTART execution

Add to `self-healing-pipeline-agent/.env`:

```
FLINK_REST_URL=http://localhost:8081
```

Now trigger a `job_failure` incident — the executor will cancel the real Flink job and resubmit it:

```bash
curl -s -X POST http://localhost:8000/incidents \
  -H "Content-Type: application/json" \
  -d @simulator/scenarios/job_failure.json | jq
```

Watch the Flink UI at http://localhost:8081 — you will see the job go from RUNNING → CANCELED → RUNNING.

---

## Run integration tests

```bash
FLINK_REST_URL=http://localhost:8081 uv run pytest tests/integration/ -v
```

These tests are skipped automatically in CI (no `FLINK_REST_URL` set).

---

## Stop Flink

```bash
cd docker
docker compose down
```
