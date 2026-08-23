# Confirmed-intent-change contract fixture

## Scenario

The model proposes changing the review scope after a new insight.

## Expected outcome

The proposal is held for **explicit confirmation**. Until the researcher accepts it, downstream assets are not regenerated. After acceptance, `intent_revision` increments and the workflow resumes from the earliest affected phase.

## Invariants

- The original intent remains recoverable.
- Human edits are not silently overwritten.
