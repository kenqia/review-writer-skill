# Fresh-start contract fixture

## Scenario

A **topic-only start** has no prior project state.

## Expected outcome

The orchestrator enters Grill, asks only the frontier questions needed to clarify the research question, and proposes `review-intent.md` and `domain-profile.md` as the first human-readable assets. It records a next action in `workflow-state.md`.

## Invariants

- No internal JSON or full form is required.
- A missing answer remains an open question instead of a guessed fact.
