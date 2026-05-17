#!/bin/bash
# DZFoot Backend — Scale services on demand
# Usage: ./scale.sh [service=count] ...
# Example: ./scale.sh account=3 session=3 matchmaking=2

set -e

COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml"
SCALE_ARGS=""

for arg in "$@"; do
    if [[ "$arg" =~ ^[a-zA-Z_-]+=[0-9]+$ ]]; then
        SERVICE="${arg%%=*}"
        COUNT="${arg##*=}"
        SCALE_ARGS="$SCALE_ARGS --scale $SERVICE=$COUNT"
        echo "Scaling $SERVICE to $COUNT replicas..."
    else
        echo "Invalid argument: $arg (expected format: service=count)"
        exit 1
    fi
done

if [ -z "$SCALE_ARGS" ]; then
    echo "Usage: ./scale.sh [service=count] ..."
    echo "Available services: account, session, matchmaking, stats, catalog"
    echo "Example: ./scale.sh account=3 session=3"
    exit 0
fi

echo "Applying scale..."
docker-compose $COMPOSE_FILES up -d --no-deps $SCALE_ARGS

echo ""
echo "Current state:"
docker-compose $COMPOSE_FILES ps
