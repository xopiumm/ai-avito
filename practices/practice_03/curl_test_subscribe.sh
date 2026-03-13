#!/usr/bin/env bash
set -e
BASE="http://127.0.0.1:8000"

echo "=== 1. Happy Path: valid email + real city (expect 201) ==="
curl -s -XPOST "$BASE/subscribe" \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com","city":"Helsinki"}' | python3 -m json.tool
echo ""

echo "=== 2. Duplicate subscription (expect 409) ==="
curl -s -o /dev/null -w "HTTP %{http_code}\n" -XPOST "$BASE/subscribe" \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com","city":"Helsinki"}'
echo ""

echo "=== 3. City not found (expect 404) ==="
curl -s -o /dev/null -w "HTTP %{http_code}\n" -XPOST "$BASE/subscribe" \
  -H 'Content-Type: application/json' \
  -d '{"email":"user2@example.com","city":"NoSuchCity_99999"}'
echo ""

echo "=== 4. Invalid email (expect 422) ==="
curl -s -o /dev/null -w "HTTP %{http_code}\n" -XPOST "$BASE/subscribe" \
  -H 'Content-Type: application/json' \
  -d '{"email":"notanemail","city":"Helsinki"}'
echo ""

echo "=== 5. Empty city (expect 422) ==="
curl -s -o /dev/null -w "HTTP %{http_code}\n" -XPOST "$BASE/subscribe" \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com","city":"   "}'
echo ""

echo "=== 6. Missing required field (expect 422) ==="
curl -s -o /dev/null -w "HTTP %{http_code}\n" -XPOST "$BASE/subscribe" \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com"}'
echo ""

echo "=== 7. Same email, different city (expect 201) ==="
curl -s -o /dev/null -w "HTTP %{http_code}\n" -XPOST "$BASE/subscribe" \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com","city":"Oslo"}'
echo ""

echo "=== 8. City with extra spaces, normalized (expect 201) ==="
curl -s -o /dev/null -w "HTTP %{http_code}\n" -XPOST "$BASE/subscribe" \
  -H 'Content-Type: application/json' \
  -d '{"email":"user3@example.com","city":"New  York"}'
echo ""

echo "=== Done ==="
