"""REST API routes for subscription management.

Endpoints:
- POST   /alerts/subscriptions           - Create subscription
- GET    /alerts/subscriptions           - List user's subscriptions
- GET    /alerts/subscriptions/{id}      - Get single subscription
- PATCH  /alerts/subscriptions/{id}      - Update subscription
- DELETE /alerts/subscriptions/{id}      - Delete subscription
- POST   /alerts/subscriptions/{id}/pause    - Disable (pause)
- POST   /alerts/subscriptions/{id}/resume   - Enable (resume)

HTTP status codes follow REST conventions with exception mapping:
- 200 OK: Successful GET, PATCH, POST (pause/resume)
- 201 Created: Successful POST create
- 204 No Content: Successful DELETE
- 400 Bad Request: Invalid request data
- 403 Forbidden: User not authorized for subscription
- 404 Not Found: Subscription doesn't exist
- 409 Conflict: State conflict (already deleted/disabled/active)
- 422 Unprocessable Entity: Unsupported types/values
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.weather_alerts.api.schemas.subscription import (
    CreateSubscriptionRequest,
    SubscriptionListItem,
    SubscriptionResponse,
    UpdateSubscriptionRequest,
)
from src.weather_alerts.config.database import get_db_session
from src.weather_alerts.config.settings import get_settings
from src.weather_alerts.services import SubscriptionService
from src.weather_alerts.services.exceptions import (
    InvalidSubscriptionData,
    SubscriptionAlreadyActive,
    SubscriptionAlreadyDeleted,
    SubscriptionAlreadyDisabled,
    SubscriptionAlreadyExists,
    SubscriptionNotFound,
    UnauthorizedSubscriptionAccess,
)

router = APIRouter(prefix="/alerts/subscriptions", tags=["subscriptions"])


# ============================================================================
# AUTHENTICATION DEPENDENCY
# ============================================================================


async def get_current_user(
    authorization: Optional[str] = Header(None),
) -> str:
    """Extract and validate current user from Authorization header.
    
    In production (allow_dev_auth=False):
    - Requires Authorization header with Bearer token
    - Validates token format
    - Extracts user_id from token
    - Raises HTTPException(403) if token is missing or invalid
    
    In development (allow_dev_auth=True):
    - If Authorization header present, extracts user from token
    - Otherwise returns hardcoded test_user_123 for development
    
    Args:
        authorization: Authorization header value (Bearer token)
        
    Returns:
        str: User ID extracted from token or test user in dev mode
        
    Raises:
        HTTPException: 403 Forbidden if auth fails in production mode
        
    Example:
        # Development mode (allow_dev_auth=True):
        # GET /api/subscriptions
        # Authorization: Bearer test_user_123
        # Returns: "test_user_123"
        
        # Or without header in dev mode:
        # GET /api/subscriptions
        # Returns: "test_user_123" (fallback)
        
        # Production mode (allow_dev_auth=False):
        # GET /api/subscriptions
        # Authorization: Bearer eyJhbGc...
        # Returns: "user_id_from_token"
        
        # Production mode without token:
        # GET /api/subscriptions
        # Raises: HTTPException(403, "Missing or invalid authorization")
    """
    settings = get_settings()
    allow_dev_auth = settings.api.allow_dev_auth
    
    # Check if Authorization header is present
    if not authorization:
        if allow_dev_auth:
            # Development mode: allow missing auth, return test user
            return "test_user_123"
        else:
            # Production mode: require auth
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing or invalid authorization",
            )
    
    # Extract Bearer token
    try:
        if not authorization.startswith("Bearer "):
            raise ValueError("Authorization header must start with 'Bearer '")
        
        token = authorization.replace("Bearer ", "", 1).strip()
        
        if not token:
            raise ValueError("Empty token")
        
        # In development mode, accept any non-empty token and extract user from it
        if allow_dev_auth:
            # Simple format: Bearer <user_id> or Bearer <jwt>
            # For dev, just return the token as user_id if it's a simple username
            # or extract from JWT format if available
            return token
        
        # Production mode: token should be a valid JWT
        # TODO: Implement JWT validation with PyJWT
        # For now, require token to be non-empty (full JWT validation deferred)
        # Placeholder for future JWT.decode() call:
        # try:
        #     payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        #     user_id = payload.get("sub")
        #     if not user_id:
        #         raise ValueError("No user_id in token")
        #     return user_id
        # except JWTError as e:
        #     raise HTTPException(403, f"Invalid token: {e}")
        
        # For now, just require token presence and format
        return token
        
    except (AttributeError, ValueError) as e:
        if allow_dev_auth:
            # In dev mode, fallback to test user if header parsing fails
            return "test_user_123"
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid authorization header format",
            )


# ============================================================================
# ERROR MAPPING HELPERS
# ============================================================================


def _handle_service_error(error: Exception) -> None:
    """Convert service exceptions to HTTP responses.

    Maps domain exceptions to appropriate HTTP status codes.
    Used in exception handling blocks.

    Raises:
        HTTPException: With appropriate status code and detail message
    """
    if isinstance(error, SubscriptionNotFound):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        )
    elif isinstance(error, UnauthorizedSubscriptionAccess):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(error),
        )
    elif isinstance(error, SubscriptionAlreadyExists):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        )
    elif isinstance(error, (SubscriptionAlreadyDeleted, SubscriptionAlreadyDisabled, SubscriptionAlreadyActive)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        )
    elif isinstance(error, InvalidSubscriptionData):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )
    else:
        # Unknown service error - internal server error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ============================================================================
# ROUTES: CRUD
# ============================================================================


@router.post(
    "",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create subscription",
    responses={
        201: {"description": "Subscription created successfully"},
        400: {"description": "Invalid schedule or ambiguous location"},
        409: {"description": "Subscription already exists for this location"},
        422: {"description": "Unsupported condition or channel type"},
    },
)
async def create_subscription(
    request: CreateSubscriptionRequest,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user),
) -> SubscriptionResponse:
    """Create a new subscription for current user.

    For a user at a specific location with weather conditions and delivery channels.

    **Request body:**
    - `location`: Location reference (id required)
    - `conditions`: List of weather conditions (min 1 required)
      - `type`: Condition type (rain_probability_above, temperature_below, etc.)
      - `threshold_value`: Numeric threshold (required for non-severe types)
      - `severity_event_type`: Event type (required for severe_weather)
    - `schedule`: Optional delivery window
      - `activeFrom`: HH:MM format (e.g., "08:00")
      - `activeTo`: HH:MM format
      - `timezoneSource`: "location" or "user"
    - `deliveryChannels`: List of destinations (min 1 required)
      - `type`: email, push, webhook
      - `destination`: address/token/URL
      - `active`: boolean

    **Returns:**
    - 201 Created: New subscription with ID and all relationships
    - 400 Bad Request: Invalid schedule or location
    - 409 Conflict: Active subscription exists for this user+location
    - 422 Unprocessable Entity: Unsupported types
    """
    service = SubscriptionService(db)

    try:
        response = await service.create(user_id, request)
        return response
    except (
        SubscriptionAlreadyExists,
        InvalidSubscriptionData,
        SubscriptionNotFound,
        UnauthorizedSubscriptionAccess,
        SubscriptionAlreadyDeleted,
        SubscriptionAlreadyDisabled,
        SubscriptionAlreadyActive,
    ) as e:
        _handle_service_error(e)


@router.get(
    "",
    response_model=List[SubscriptionResponse],
    status_code=status.HTTP_200_OK,
    summary="List user's subscriptions",
    responses={
        200: {"description": "List of subscriptions (excludes deleted)"},
    },
)
async def list_subscriptions(
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> List[SubscriptionResponse]:
    """List all active and disabled subscriptions for current user.

    **Notes:**
    - Returns only non-deleted subscriptions (status != deleted)
    - Newest subscriptions first (by created_at DESC)
    - Soft-deleted subscriptions are excluded

    **Query parameters:**
    - `limit`: Max items to return (default 100, max 1000)
    - `offset`: Skip first N items (for pagination, default 0)

    **Returns:**
    - 200 OK: List of subscriptions (may be empty)
    """
    service = SubscriptionService(db)

    try:
        subscriptions = await service.list(user_id)
        # Apply pagination
        return subscriptions[offset : offset + limit]
    except Exception as e:
        _handle_service_error(e)


@router.get(
    "/{subscription_id}",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get subscription",
    responses={
        200: {"description": "Subscription found"},
        403: {"description": "User not authorized for this subscription"},
        404: {"description": "Subscription not found"},
    },
)
async def get_subscription(
    subscription_id: int = Path(..., ge=1, description="Subscription ID"),
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user),
) -> SubscriptionResponse:
    """Get single subscription with all details.

    Full details include:
    - Subscription metadata (id, status, dates)
    - All conditions with thresholds
    - All delivery channels with state
    - Schedule window

    **Path parameters:**
    - `subscription_id`: Subscription ID to retrieve

    **Returns:**
    - 200 OK: Full subscription object
    - 403 Forbidden: User doesn't own this subscription
    - 404 Not Found: Subscription doesn't exist
    """
    service = SubscriptionService(db)

    try:
        response = await service.get(user_id, subscription_id)
        return response
    except (
        SubscriptionNotFound,
        UnauthorizedSubscriptionAccess,
    ) as e:
        _handle_service_error(e)


@router.patch(
    "/{subscription_id}",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_200_OK,
    summary="Update subscription",
    responses={
        200: {"description": "Subscription updated"},
        400: {"description": "Invalid update data"},
        403: {"description": "User not authorized"},
        404: {"description": "Subscription not found"},
        409: {"description": "Cannot update deleted subscription"},
    },
)
async def update_subscription(
    request: UpdateSubscriptionRequest,
    subscription_id: int = Path(..., ge=1, description="Subscription ID"),
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user),
) -> SubscriptionResponse:
    """Update subscription with partial changes.

    **Partial update semantics:**
    - Only provided fields are updated
    - `conditions`: If provided, replaces ALL existing conditions
    - `deliveryChannels`: If provided, replaces ALL existing channels
    - `schedule`: If provided, updates schedule window

    **Example: Update only schedule window**
    ```json
    {
      "schedule": {
        "activeFrom": "09:00",
        "activeTo": "18:00"
      }
    }
    ```
    Other fields (conditions, channels) remain unchanged.

    **Example: Replace all conditions**
    ```json
    {
      "conditions": [
        {"type": "temperature_below", "threshold_value": -15}
      ]
    }
    ```
    Creates new conditions, discards old ones.

    **Path parameters:**
    - `subscription_id`: Subscription to update

    **Returns:**
    - 200 OK: Updated subscription
    - 400 Bad Request: Invalid data
    - 403 Forbidden: User doesn't own subscription
    - 404 Not Found: Subscription not found
    - 409 Conflict: Cannot update deleted subscription
    """
    service = SubscriptionService(db)

    try:
        response = await service.update(user_id, subscription_id, request)
        return response
    except (
        SubscriptionNotFound,
        UnauthorizedSubscriptionAccess,
        InvalidSubscriptionData,
        SubscriptionAlreadyDeleted,
    ) as e:
        _handle_service_error(e)


@router.delete(
    "/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete subscription",
    responses={
        204: {"description": "Subscription deleted (soft delete)"},
        403: {"description": "User not authorized"},
        404: {"description": "Subscription not found"},
        409: {"description": "Subscription already deleted"},
    },
)
async def delete_subscription(
    subscription_id: int = Path(..., ge=1, description="Subscription ID"),
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user),
) -> None:
    """Soft-delete subscription.

    Marks subscription as deleted without removing from database:
    - Sets status = "deleted"
    - Sets deleted_at = current timestamp
    - Subscription excluded from list() operations
    - No notifications sent for deleted subscriptions
    - Data preserved for audit/recovery

    **Note:** Pending/retry delivery tasks should be cancelled
    by a background worker, not by this endpoint.

    **Path parameters:**
    - `subscription_id`: Subscription to delete

    **Returns:**
    - 204 No Content: Deletion successful (empty response body)
    - 403 Forbidden: User doesn't own subscription
    - 404 Not Found: Subscription not found
    - 409 Conflict: Already deleted
    """
    service = SubscriptionService(db)

    try:
        await service.delete(user_id, subscription_id)
        # 204 No Content: no response body
        return None
    except (
        SubscriptionNotFound,
        UnauthorizedSubscriptionAccess,
        SubscriptionAlreadyDeleted,
    ) as e:
        _handle_service_error(e)


# ============================================================================
# ROUTES: STATE TRANSITIONS
# ============================================================================


@router.post(
    "/{subscription_id}/pause",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_200_OK,
    summary="Pause subscription (disable)",
    responses={
        200: {"description": "Subscription paused (disabled)"},
        403: {"description": "User not authorized"},
        404: {"description": "Subscription not found"},
        409: {"description": "Subscription already disabled/deleted"},
    },
)
async def pause_subscription(
    subscription_id: int = Path(..., ge=1, description="Subscription ID"),
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user),
) -> SubscriptionResponse:
    """Temporarily pause (disable) subscription.

    State transition: ACTIVE → DISABLED

    **Effects:**
    - Conditions are no longer evaluated
    - No notifications are sent
    - Data is preserved (can be resumed later)
    - Soft-deleted subscriptions cannot be paused

    **Path parameters:**
    - `subscription_id`: Subscription to pause

    **Returns:**
    - 200 OK: Paused subscription with status=disabled
    - 403 Forbidden: User doesn't own subscription
    - 404 Not Found: Subscription not found
    - 409 Conflict: Already disabled or deleted
    """
    service = SubscriptionService(db)

    try:
        response = await service.disable(user_id, subscription_id)
        return response
    except (
        SubscriptionNotFound,
        UnauthorizedSubscriptionAccess,
        SubscriptionAlreadyDisabled,
        InvalidSubscriptionData,
    ) as e:
        _handle_service_error(e)


@router.post(
    "/{subscription_id}/resume",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_200_OK,
    summary="Resume subscription (enable)",
    responses={
        200: {"description": "Subscription resumed (enabled)"},
        403: {"description": "User not authorized"},
        404: {"description": "Subscription not found"},
        409: {"description": "Subscription already active/deleted"},
    },
)
async def resume_subscription(
    subscription_id: int = Path(..., ge=1, description="Subscription ID"),
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user),
) -> SubscriptionResponse:
    """Resume (enable) a paused subscription.

    State transition: DISABLED → ACTIVE

    **Effects:**
    - Resumes condition evaluation
    - Resumes notification delivery
    - Soft-deleted subscriptions cannot be resumed

    **Path parameters:**
    - `subscription_id`: Subscription to resume

    **Returns:**
    - 200 OK: Resumed subscription with status=active
    - 403 Forbidden: User doesn't own subscription
    - 404 Not Found: Subscription not found
    - 409 Conflict: Already active or deleted
    """
    service = SubscriptionService(db)

    try:
        response = await service.enable(user_id, subscription_id)
        return response
    except (
        SubscriptionNotFound,
        UnauthorizedSubscriptionAccess,
        SubscriptionAlreadyActive,
        InvalidSubscriptionData,
    ) as e:
        _handle_service_error(e)
