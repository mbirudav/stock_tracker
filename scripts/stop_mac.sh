#!/usr/bin/env bash
CONTAINER_NAME="finally-app"
docker stop "$CONTAINER_NAME" 2>/dev/null && docker rm "$CONTAINER_NAME" 2>/dev/null || true
echo "FinAlly stopped. Your data is preserved in db/finally.db"
