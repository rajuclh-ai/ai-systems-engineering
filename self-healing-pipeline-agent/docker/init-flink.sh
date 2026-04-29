#!/bin/sh
# Uploads the StateMachineExample JAR to Flink on startup.
# The returned jarId is written to /tmp/flink-jar-id so the REST client can read it.
# This runs once — subsequent docker-compose up reuses the same Flink state.

FLINK_URL="http://jobmanager:8081"
JAR_PATH="/flink-examples/StateMachineExample.jar"

echo "Waiting for Flink REST API..."
until curl -sf "$FLINK_URL/config" > /dev/null; do
  sleep 2
done

echo "Uploading StateMachineExample JAR..."

# Copy JAR from jobmanager container via the REST upload endpoint
RESPONSE=$(curl -sf -X POST \
  "$FLINK_URL/jars/upload" \
  -H "Expect:" \
  -F "jarfile=@$JAR_PATH;type=application/java-archive")

if [ $? -ne 0 ]; then
  echo "ERROR: JAR upload failed — is the JAR present at $JAR_PATH?"
  exit 1
fi

JAR_ID=$(echo "$RESPONSE" | grep -o '"filename":"[^"]*"' | grep -o '[^/]*$' | tr -d '"')

if [ -z "$JAR_ID" ]; then
  echo "ERROR: Could not parse jarId from response: $RESPONSE"
  exit 1
fi

echo "JAR uploaded — jarId=$JAR_ID"

# Submit the StateMachineExample job so there is a running job to restart
echo "Submitting StateMachineExample job..."
curl -sf -X POST \
  "$FLINK_URL/jars/$JAR_ID/run" \
  -H "Content-Type: application/json" \
  -d '{}'

echo "Done — Flink is ready with a running StateMachineExample job."
echo "jarId: $JAR_ID"
