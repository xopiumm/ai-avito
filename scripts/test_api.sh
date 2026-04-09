#!/usr/bin/env bash
# curl examples for testing Weather Alerts API

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

BASE_URL="http://localhost:8000"
USER_ID="test_user_123"

echo -e "${BLUE}Weather Alerts API - Testing Examples${NC}\n"

# ============================================================================
# HEALTH CHECK
# ============================================================================

echo -e "${YELLOW}1. Health Check${NC}"
echo "GET /health"
curl -s -X GET "$BASE_URL/health" | jq .
echo ""

# ============================================================================
# CREATE SUBSCRIPTION
# ============================================================================

echo -e "${YELLOW}2. Create Subscription${NC}"
echo "POST /alerts/subscriptions"
SUBSCRIPTION=$(curl -s -X POST "$BASE_URL/alerts/subscriptions" \
  -H "Content-Type: application/json" \
  -d '{
    "location": {
      "id": 1,
      "display_name": "Moscow"
    },
    "conditions": [
      {
        "type": "rain_probability_above",
        "threshold_value": 70
      }
    ],
    "schedule": {
      "timezone_source": "location",
      "active_from": "08:00",
      "active_to": "20:00"
    },
    "delivery_channels": [
      {
        "type": "email",
        "destination": "user@example.com",
        "active": true
      }
    ]
  }')
echo "$SUBSCRIPTION" | jq .

# Extract subscription ID from response
SUBSCRIPTION_ID=$(echo "$SUBSCRIPTION" | jq -r '.id')
echo -e "${GREEN}Created subscription ID: $SUBSCRIPTION_ID${NC}\n"

# ============================================================================
# LIST SUBSCRIPTIONS
# ============================================================================

echo -e "${YELLOW}3. List Subscriptions${NC}"
echo "GET /alerts/subscriptions?limit=10&offset=0"
curl -s -X GET "$BASE_URL/alerts/subscriptions?limit=10&offset=0" | jq .
echo ""

# ============================================================================
# GET SINGLE SUBSCRIPTION
# ============================================================================

echo -e "${YELLOW}4. Get Single Subscription${NC}"
echo "GET /alerts/subscriptions/$SUBSCRIPTION_ID"
curl -s -X GET "$BASE_URL/alerts/subscriptions/$SUBSCRIPTION_ID" | jq .
echo ""

# ============================================================================
# UPDATE SUBSCRIPTION (partial - only schedule)
# ============================================================================

echo -e "${YELLOW}5. Update Subscription (partial - schedule only)${NC}"
echo "PATCH /alerts/subscriptions/$SUBSCRIPTION_ID"
curl -s -X PATCH "$BASE_URL/alerts/subscriptions/$SUBSCRIPTION_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "schedule": {
      "timezone_source": "location",
      "active_from": "09:00",
      "active_to": "18:00"
    }
  }' | jq .
echo ""

# ============================================================================
# PAUSE SUBSCRIPTION
# ============================================================================

echo -e "${YELLOW}6. Pause Subscription (disable)${NC}"
echo "POST /alerts/subscriptions/$SUBSCRIPTION_ID/pause"
curl -s -X POST "$BASE_URL/alerts/subscriptions/$SUBSCRIPTION_ID/pause" | jq .
echo ""

# ============================================================================
# RESUME SUBSCRIPTION
# ============================================================================

echo -e "${YELLOW}7. Resume Subscription (enable)${NC}"
echo "POST /alerts/subscriptions/$SUBSCRIPTION_ID/resume"
curl -s -X POST "$BASE_URL/alerts/subscriptions/$SUBSCRIPTION_ID/resume" | jq .
echo ""

# ============================================================================
# DELETE SUBSCRIPTION
# ============================================================================

echo -e "${YELLOW}8. Delete Subscription${NC}"
echo "DELETE /alerts/subscriptions/$SUBSCRIPTION_ID"
curl -s -X DELETE "$BASE_URL/alerts/subscriptions/$SUBSCRIPTION_ID" -w "\nStatus: %{http_code}\n"
echo ""

# ============================================================================
# ERROR EXAMPLES
# ============================================================================

echo -e "${YELLOW}9. Error Examples${NC}\n"

echo -e "${YELLOW}9a. Get non-existent subscription (404)${NC}"
curl -s -X GET "$BASE_URL/alerts/subscriptions/9999" -w "\nStatus: %{http_code}\n" | jq .
echo ""

echo -e "${YELLOW}9b. Invalid condition type (422)${NC}"
curl -s -X POST "$BASE_URL/alerts/subscriptions" \
  -H "Content-Type: application/json" \
  -d '{
    "location": {"id": 1},
    "conditions": [{"type": "invalid_type", "threshold_value": 70}],
    "delivery_channels": [{"type": "email", "destination": "user@example.com"}]
  }' -w "\nStatus: %{http_code}\n" | jq .
echo ""

echo -e "${YELLOW}9c. Missing required fields (422)${NC}"
curl -s -X POST "$BASE_URL/alerts/subscriptions" \
  -H "Content-Type: application/json" \
  -d '{
    "location": {"id": 1}
  }' -w "\nStatus: %{http_code}\n" | jq .
echo ""

echo -e "${GREEN}Testing complete!${NC}\n"
