# Research tool-failure contract fixture

## Scenario

All configured discovery adapters fail because an API is missing or unavailable.

## Expected outcome

The state becomes `HUMAN_ACTION_REQUIRED` / `WAITING_FOR_HUMAN`, naming the
affected capability, minimum recovery action, and a legal degradation route.

## Invariants

- No credential, cookie, or paywall bypass is attempted.
- The saved intent and domain assets remain recoverable.
