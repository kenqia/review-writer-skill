# Changelog

## Unreleased — review hardening

- Fail closed on mismatched source-fact content, non-PDF downloads, ambiguous
  inbox identities, parser timeouts, and provider error credential leakage.
- Bound user download requests to a finite priority queue and preserve deferred
  research gaps; generate synchronized reader and research draft views.
- Require explicit `VERIFIED_SOURCE_FACT` evidence markers, select download
  requests by claim relevance/non-substitutability instead of a fixed count,
  and redact constructor-supplied provider credentials from failures.
- Populate candidate claim relevance from the confirmed brief on live provider
  discovery so restricted core-paper URLs can enter the user download route.
- Withhold credential-bearing signed full-text URLs from Research Markdown and
  cache while preserving an explicit `WITHHELD_CREDENTIAL_BEARING_URL`
  degradation and recovery action for a fresh legal route.

## 0.2.0-beta.1 — v2 implementation candidate

- Replace the v1 seven-stage orchestrator with four independently invocable
  Intent, Research, Synthesis, and QA skills using explicit Markdown handoffs.
- Add configurable OpenAlex, Semantic Scholar, Crossref, PubChem, ChEBI,
  Unpaywall, Europe PMC, CORE, and MinerU adapters plus an authorized-PDF wait
  and resume path.
- Add evidence-bounded Synthesis and four isolated QA roles with
  conflict-preserving aggregation.
- Remove the v1 runtime and generated projection from the supported package.

## 0.1.0-beta.1 — release candidate

- Package Chemical Review as a Codex plugin with a versioned manifest.
- Keep `.agents/skills/chemical-review/` as the canonical editable source and
  verify the generated plugin projection in CI.
- Include deterministic plugin packaging and SHA-256 checksums.
- Document the experimental boundary: a candidate review still requires human
  scientific editing and does not imply journal acceptance.
