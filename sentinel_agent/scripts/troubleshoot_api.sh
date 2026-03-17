#!/bin/bash
# Troubleshoot the Sentinel Agent API
# Run from sentinel_agent directory: bash scripts/troubleshoot_api.sh

set -e
BASE="${1:-http://127.0.0.1:8001}"
echo "=== Troubleshooting Sentinel Agent API at $BASE ==="
echo ""

echo "1. Testing health endpoint..."
if curl -s -f --connect-timeout 3 "$BASE/v1/health" > /dev/null; then
  echo "   OK: Health endpoint responded"
  curl -s "$BASE/v1/health" | head -1
else
  echo "   FAIL: Could not reach health endpoint"
  echo "   - Is the server running? (python -m src.api)"
  echo "   - Try: curl $BASE/v1/health"
  exit 1
fi
echo ""

echo "2. Testing six_satellite status..."
if curl -s -f --connect-timeout 3 "$BASE/v1/simulation/stream/six_satellite/status" > /dev/null; then
  echo "   OK: Six-satellite endpoint available"
  curl -s "$BASE/v1/simulation/stream/six_satellite/status"
else
  echo "   FAIL: Six-satellite status endpoint not reachable"
fi
echo ""

echo "3. Checking if server is listening on port 8001..."
if lsof -i :8001 2>/dev/null | grep -q LISTEN; then
  echo "   OK: Something is listening on port 8001"
else
  echo "   WARN: Nothing listening on 8001. Start with: python -m src.api"
fi
echo ""

echo "4. To stream six_satellite (Ctrl+C to stop):"
echo "   curl -N \"$BASE/v1/simulation/stream/six_satellite\""
echo ""
