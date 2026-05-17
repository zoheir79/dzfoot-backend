#!/bin/bash
# Health check all backend services

set -e

echo "=== Backend Health Check ==="
echo ""

SERVICES="account session matchmaking stats catalog"

echo "Docker containers:"
docker-compose ps

echo ""
echo "Service endpoints:"
for svc in $SERVICES; do
    URL="http://localhost:8000"
    case $svc in
        account) URL="http://localhost:8001" ;;
        session) URL="http://localhost:8002" ;;
        matchmaking) URL="http://localhost:8003" ;;
        stats) URL="http://localhost:8004" ;;
        catalog) URL="http://localhost:8005" ;;
    esac
    
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$URL/health" 2>/dev/null || echo "DOWN")
    if [ "$STATUS" = "200" ]; then
        echo "  $svc: OK"
    else
        echo "  $svc: FAIL ($STATUS)"
    fi
done

echo ""
echo "Nginx gateway:"
curl -s -o /dev/null -w "%{http_code}" "http://localhost:8080/health" || echo "DOWN"

echo ""
echo "Redis:"
docker-compose exec -T redis redis-cli ping 2>/dev/null || echo "DOWN"

echo ""
echo "PostgreSQL:"
docker-compose exec -T postgres pg_isready -U dzfoot 2>/dev/null || echo "DOWN"
