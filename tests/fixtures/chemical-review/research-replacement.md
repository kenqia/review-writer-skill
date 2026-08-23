# Research replacement contract fixture

## Scenario

The preferred discovery or parsing provider is unavailable, so a configured
replaceable replacement route is used with explicit degradation.

## Expected outcome

The run completes with a documented fallback and records which capability was
degraded; the provider name is not hard-coded into the scientific conclusion.

## Invariants

- Replacement and fallback are explicit in the research evidence asset.
- A partial tool failure does not erase successful results from another route.
