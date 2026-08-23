# Resume contract fixture

## Scenario

The previous context window ended after a Research handoff proposal.

## Expected outcome

On a **cold restart**, the orchestrator reads the saved state and resumes from `next_action` instead of restarting Grill or inventing missing history.

## Invariants

- Existing intent and domain assets are preserved.
- The current phase and next action remain visible in Markdown.
