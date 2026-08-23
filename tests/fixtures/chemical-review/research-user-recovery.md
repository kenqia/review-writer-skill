# Research user-recovery contract fixture

## Scenario

The researcher uses a user-assisted path to configure a missing adapter or provide an authorized source
after a blocked Research run, then asks the orchestrator to rerun.

## Expected outcome

The rerun uses the new route, preserves the prior evidence package and human
notes (preserved), and records the recovered capability in the next state.
