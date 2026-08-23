# Blueprint revision after new evidence contract fixture

## Scenario

New Research evidence changes a comparison dimension after the first review
blueprint has been saved.

## Expected outcome

Only the affected blueprint sections change, `blueprint_revision` increments,
and the evidence/reasoning note plus previous content remain in Revision history.

## Invariants

- The blueprint remains `ADAPTABLE` and does not freeze every sentence or paper.
- Existing Research and Prototype assets are preserved for cold restart.
- A direct human edit to a revised section is detected and retained in history.
