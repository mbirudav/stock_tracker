#!/usr/bin/env bash
set -e
CONTAINER_NAME="finally-app"
IMAGE_NAME="finally"

if [ "$1" = "--build" ] || ! docker image inspect "$IMAGE_NAME" &>/dev/null; then
  echo "Building FinAlly..."
  docker build -t "$IMAGE_NAME" .
fi

if docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
  echo "FinAlly is already running at http://localhost:8000"
  exit 0
fi

docker run -d \
  --name "$CONTAINER_NAME" \
  -p 8000:8000 \
  -v "$(pwd)/db:/app/db" \
  --env-file .env \
  "$IMAGE_NAME"

echo "FinAlly started at http://localhost:8000"
