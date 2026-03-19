# agents.md

## Project Overview
This project follows the repository's existing architecture. Agents working on this codebase should first inspect the current implementation and then reuse the same patterns instead of introducing new abstractions.

## General Rules
- Read the existing code before proposing changes
- Prefer minimal diffs
- Do not modify unrelated files
- Reuse current naming conventions
- Reuse current error handling conventions
- Explicitly state uncertainty instead of guessing
- Keep changes easy to review

## API Rules
- Add routes in the existing routing layer only
- Validate all input parameters
- Keep HTTP-specific logic in handlers/controllers
- Keep business logic in services/use cases
- Keep persistence logic in repositories/data access
- Reuse existing DTOs, presenters, and serializers when possible
- Return status codes consistent with the current API style
- Handle at least:
  - success
  - invalid input
  - not found
  - internal error

## Testing Rules
- Add or update tests for each new behavior
- Follow the repository's current test framework and style
- Cover both positive and negative cases
- For API changes, include HTTP-level behavior tests when appropriate
- For service logic, include unit tests
- Reuse existing test helpers and fixtures when possible
- Document any important missing case that was not implemented

## Architecture Constraints
- Do not place business logic in handlers/controllers
- Do not let repositories contain HTTP concerns
- Avoid leaking persistence entities into external API responses if the project uses DTOs
- Avoid creating duplicate abstractions when an existing extension point is available
- Prefer consistency with the current repository over theoretical ideal structure

## Code Change Policy
- Change only what is required for the task
- Avoid broad refactors unless explicitly requested
- Avoid adding dependencies unless justified
- Preserve backward-compatible behavior unless the task requires contract changes
- Keep generated code aligned with the repository's real patterns

## Review Checklist
Before considering a task complete, verify:
- routes are connected correctly
- handlers/controllers validate input correctly
- services/use cases encapsulate business logic
- repositories/data access perform the required data operations
- errors are mapped consistently
- tests exist and are meaningful
- manual verification steps are available

## Definition of Done
A task is complete only when:
- implementation is consistent with repository conventions
- required tests are added or updated
- behavior is manually verifiable
- documentation or reflection is updated when needed