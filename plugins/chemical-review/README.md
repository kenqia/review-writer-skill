# Chemical Review v2 plugin

This plugin packages four independently invocable skills:

`chemical-review-intent → chemical-review-research → chemical-review-synthesis → chemical-review-qa`

They exchange explicit Markdown artifacts. Intent owns `review-brief.md`; Research owns `research/` (including the authorized PDF inbox and download requests); Synthesis owns the single `draft.md`; QA owns independent reports and revision plans. There is no central orchestrator, v1 payload, Prototype/PRD/Issues/Implement workflow, or second content authority.

Research implements configurable OpenAlex, Semantic Scholar, Crossref, PubChem, ChEBI, Unpaywall, Europe PMC, CORE, and MinerU routes. Restricted or authorization-ambiguous papers produce a legal download URL and instructions. Place the downloaded PDF in `research/inbox/authorized-pdfs/` and rerun Research. `pdftotext` is a clearly degraded local fallback; the original PDF remains authoritative.

QA prepares four clean contexts: evidence/locator, chemistry comparability/mechanism, synthesis novelty/rebuttal, and overclaim/counterexample. An arbiter preserves conflicts and advises the human scientific editor; it never accepts scientific validity by vote.

Invoke the stages explicitly with `$chemical-review-intent`, `$chemical-review-research`, `$chemical-review-synthesis`, and `$chemical-review-qa`. Configure credentials only through environment variables or an untracked local env file (see the repository `.env.example`); never place real values in this plugin or its Markdown handoffs.
