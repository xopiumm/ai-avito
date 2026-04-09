"""Integration tests for Weather Alerts API.

Integration tests verify the complete flow through multiple service layers:
- Subscription lifecycle (create, read, update, delete, pause, resume)
- Event delivery pipeline (subscription → condition evaluation → delivery)
- Channel isolation and error handling

These tests use:
- Real FastAPI app and test client
- Real database (SQLite in-memory or test database)
- Mocked external adapters (weather provider, email sender, etc.)
- Clear fixtures and setup/teardown for reproducibility

Key principles:
- Tests are independent and can run in any order
- Setup and teardown are explicit and documented
- Mocks replace external services (no actual email/webhook calls)
- Each test is focused on one scenario/flow
- Minimal helper logic (keep tests readable)
"""
