"""Replaceable, file-backed Research phase capabilities.

Research owns discovery and evidence preparation, not scientific adjudication.
Adapters are deliberately tiny duck-typed seams so a configured API, a local
fixture, or a later provider can be substituted without changing the workflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
import hashlib
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from orchestrator import _document, _section_value, _set_section, _split_frontmatter


class CapabilityUnavailable(RuntimeError):
    """An adapter cannot perform its advertised capability."""


class DiscoveryAdapter(Protocol):
    name: str

    def search(self, query: str, path: str) -> Sequence[PaperRecord]: ...


class EntityAdapter(Protocol):
    name: str

    def expand(self, term: str) -> Sequence[str]: ...


class FullTextAdapter(Protocol):
    name: str

    def fetch(self, paper: PaperRecord) -> FullTextResult: ...


class ParserAdapter(Protocol):
    name: str

    def parse(self, full_text: FullTextResult) -> ParsedDocument: ...


@dataclass(frozen=True)
class PaperRecord:
    identifier: str
    title: str
    authors: tuple[str, ...] = ()
    year: int | None = None
    source: str = ""
    layer: str = ""
    abstract: str = ""
    doi: str = ""
    keywords: tuple[str, ...] = ()
    cited_identifiers: tuple[str, ...] = ()


@dataclass(frozen=True)
class FullTextResult:
    paper_id: str
    status: str
    text: str
    source: str
    locator: str = ""
    access_basis: str = ""


@dataclass(frozen=True)
class ParsedDocument:
    paper_id: str
    parser: str
    sections: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    locators: tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class CapabilityIssue:
    capability: str
    provider: str
    reason: str
    recovery: str
    blocking: bool = False


@dataclass(frozen=True)
class ResearchConfig:
    """Adapters supplied by a user, test, or future integration layer."""

    discovery: Sequence[DiscoveryAdapter] = ()
    entities: Sequence[EntityAdapter] = ()
    full_text: Sequence[FullTextAdapter] = ()
    parsers: Sequence[ParserAdapter] = ()


@dataclass(frozen=True)
class ResearchRunResult:
    status: str
    human_action: str
    next_action: str
    handoff: str | None
    handoff_rationale: str
    covered_directions: tuple[str, ...]
    uncovered_directions: tuple[str, ...]
    uncertainties: tuple[str, ...]
    issues: tuple[CapabilityIssue, ...]
    papers: tuple[PaperRecord, ...]
    full_texts: tuple[FullTextResult, ...]
    parsed: tuple[ParsedDocument, ...]
    assets: Mapping[str, str] = field(default_factory=dict)


SEARCH_PATHS = (
    ("synonyms", "alternative names and spelling variants"),
    ("definitions", "definitions and foundational concepts"),
    ("methods/materials", "methods, materials, and system variants"),
    ("key events", "key events and historical turning points"),
    ("citation relations", "backward, forward, and co-citation relations"),
    ("authors/groups", "authors, groups, and competing schools"),
    ("recent developments", "recent developments and emerging directions"),
)

DEFAULT_ROUTES = (
    ("discovery/metadata", "OpenAlex", "search and citation graph discovery"),
    ("discovery/metadata", "Semantic Scholar", "semantic search and related-paper discovery"),
    ("discovery/metadata", "Crossref", "DOI and bibliographic metadata"),
    ("chemistry entity/term", "PubChem", "chemical entities, structures, and synonyms"),
    ("chemistry entity/term", "ChEBI", "chemical ontology terms and identifiers"),
    ("legal full text", "Unpaywall", "open-access location discovery"),
    ("legal full text", "Europe PMC", "legitimate full-text discovery where available"),
    ("legal full text", "CORE", "legitimate repository full-text discovery"),
    ("PDF parsing", "MinerU", "preferred PDF-to-structured-text route"),
    ("PDF parsing", "GROBID", "structure and reference extraction supplement"),
    ("PDF parsing", "Docling", "fallback or comparison parser"),
)
PREFERRED_PARSERS = ("MinerU", "GROBID", "Docling")
PREFERRED_DISCOVERY = ("OpenAlex", "Semantic Scholar", "Crossref")
PREFERRED_ENTITIES = ("PubChem", "ChEBI")
PREFERRED_FULL_TEXT = ("Unpaywall", "Europe PMC", "CORE")
LEGAL_ACCESS_BASES = {"OPEN_ACCESS", "USER_AUTHORIZED", "INSTITUTION_AUTHORIZED"}
EVIDENCE_TRACKED_SECTIONS = (
    "Research question",
    "Project domain context",
    "Search paths",
    "Terms and chemistry entities",
    "Evidence notes",
    "Covered directions",
    "High-impact uncovered areas",
    "Major uncertainties",
    "Tool route",
    "Tool degradation or HUMAN_ACTION_REQUIRED",
    "Research handoff",
)
LITERATURE_TRACKED_SECTIONS = (
    "Anchor/core",
    "Extension",
    "Background/definition",
    "Controversy",
)


class ResearchRunner:
    """Run adaptive paths and persist editable Research assets."""

    def __init__(self, project_root: str | Path, *, today: date | None = None) -> None:
        self.project_root = Path(project_root)
        self.today = today or date.today()

    @property
    def evidence_path(self) -> Path:
        return self.project_root / "research-evidence.md"

    @property
    def literature_path(self) -> Path:
        return self.project_root / "literature-set.md"

    def run(
        self,
        intent_markdown: str,
        domain_markdown: str,
        config: ResearchConfig | None = None,
        *,
        intent_revision: str = "0",
    ) -> ResearchRunResult:
        config = config or ResearchConfig()
        human_edit_detected = any(
            _asset_has_direct_edit(path, titles)
            for path, titles in (
                (self.evidence_path, EVIDENCE_TRACKED_SECTIONS),
                (self.literature_path, LITERATURE_TRACKED_SECTIONS),
            )
        )
        topic = _section_value(intent_markdown, "Research question") or "the confirmed chemistry review topic"
        domain_context = self._domain_context(domain_markdown)
        entity_adapters = _preferred(config.entities, PREFERRED_ENTITIES)
        discovery_adapters = _preferred(config.discovery, PREFERRED_DISCOVERY)
        full_text_adapters = _preferred(config.full_text, PREFERRED_FULL_TEXT)
        parser_adapters = _preferred(config.parsers, PREFERRED_PARSERS)
        terms, issues = self._expand_terms(topic, domain_context, entity_adapters)
        papers, path_queries, discovery_issues = self._discover(
            topic, terms, domain_context, discovery_adapters
        )
        issues.extend(discovery_issues)
        full_texts, parsed, parsing_issues = self._retrieve_and_parse(
            papers, full_text_adapters, parser_adapters
        )
        issues.extend(parsing_issues)
        issues = _dedupe_issues(issues)

        covered = tuple(path for path, _ in SEARCH_PATHS if path_queries.get(path, 0) > 0)
        uncovered = tuple(
            _uncovered_impact(path) for path, _ in SEARCH_PATHS if path_queries.get(path, 0) == 0
        )
        uncertainties = self._uncertainties(papers, parsed, issues, uncovered)
        has_discovery = bool(papers)
        blocking = not has_discovery or any(issue.blocking for issue in issues) or human_edit_detected
        status = "WAITING_FOR_HUMAN" if blocking else "READY_FOR_NEXT_PHASE"
        human_action = "REQUIRED" if blocking else "NONE"
        handoff, handoff_rationale = self._handoff(papers, parsed, uncovered, issues, blocking)
        if human_edit_detected:
            next_action = (
                "Review the preserved human edits and conflicts, confirm the accepted wording, "
                "then rerun Research."
            )
        elif any(issue.blocking for issue in issues):
            next_action = (
                "Provide an open-access or explicitly authorized full-text locator with page/section "
                "locations, then rerun Research."
            )
        elif blocking:
            next_action = (
                "Configure at least one discovery adapter or provide an authorized literature source, "
                "then rerun Research."
            )
        else:
            next_action = (
                "Review the Research evidence package, covered directions, uncovered high-impact areas, "
                "and uncertainties before accepting the Prototype handoff."
            )

        route_summary = self._route_summary(config)
        degradation = self._issue_summary(issues)
        self._persist(
            topic=topic,
            domain_context=domain_context,
            intent_revision=intent_revision,
            status=status,
            human_action=human_action,
            next_action=next_action,
            handoff=handoff,
            handoff_rationale=handoff_rationale,
            terms=terms,
            route_summary=route_summary,
            path_queries=path_queries,
            covered=covered,
            uncovered=uncovered,
            uncertainties=uncertainties,
            papers=papers,
            full_texts=full_texts,
            parsed=parsed,
            issues=issues,
            degradation=degradation,
        )
        return ResearchRunResult(
            status=status,
            human_action=human_action,
            next_action=next_action,
            handoff=handoff,
            handoff_rationale=handoff_rationale,
            covered_directions=covered,
            uncovered_directions=uncovered,
            uncertainties=uncertainties,
            issues=tuple(issues),
            papers=tuple(papers),
            full_texts=tuple(full_texts),
            parsed=tuple(parsed),
            assets={
                "research_handoff": handoff or "NONE",
                "research_handoff_rationale": handoff_rationale,
                "tool_degradation": degradation,
            },
        )

    def _handoff(
        self,
        papers: Sequence[PaperRecord],
        parsed: Sequence[ParsedDocument],
        uncovered: Sequence[str],
        issues: Sequence[CapabilityIssue],
        blocking: bool,
    ) -> tuple[str | None, str]:
        if blocking:
            return None, "No handoff while a required human action or discovery blocker remains."
        prototype_reasons: list[str] = []
        if uncovered:
            prototype_reasons.append("high-impact search paths remain uncovered")
        if papers and not parsed:
            prototype_reasons.append("no candidate has a locator-bearing structured parse")
        if issues:
            prototype_reasons.append("preferred capabilities degraded or were not configured")
        if any(_layer_name(paper.layer) == "controversy" for paper in papers):
            prototype_reasons.append("the candidate set contains a controversy needing small-sample testing")
        if prototype_reasons:
            return "PROTOTYPE", "Prototype is recommended because " + "; ".join(prototype_reasons) + "."
        return (
            "PRD",
            "Direct PRD is proposed because all planned paths produced candidates, locator-bearing parses exist, "
            "and no capability degradation or controversy risk was recorded; the researcher still accepts the handoff.",
        )

    def _domain_context(self, domain_markdown: str) -> dict[str, str]:
        return {
            heading: _section_value(domain_markdown, heading)
            for heading in (
                "Chemical subfield",
                "Core systems",
                "Canonical terms and synonyms",
                "Boundary scenarios",
                "Evidence expectations",
                "Known capability limits",
            )
        }

    def _expand_terms(
        self,
        topic: str,
        domain_context: Mapping[str, str],
        adapters: Sequence[object],
    ) -> tuple[tuple[str, ...], list[CapabilityIssue]]:
        terms = {topic}
        canonical_terms = domain_context.get("Canonical terms and synonyms", "")
        if canonical_terms and not canonical_terms.lower().startswith("open question"):
            terms.update(
                term.strip()
                for term in canonical_terms.replace("Initial topic:", "").replace(";", ",").split(",")
                if term.strip()
            )
        issues: list[CapabilityIssue] = []
        configured = {getattr(adapter, "name", adapter.__class__.__name__) for adapter in adapters}
        for provider in ("PubChem", "ChEBI"):
            if provider not in configured:
                issues.append(
                    CapabilityIssue(
                        "chemistry entity/term",
                        provider,
                        "not configured for this run",
                        "Configure the provider or add verified terms in domain-profile.md.",
                    )
                )
        for adapter in adapters:
            name = getattr(adapter, "name", adapter.__class__.__name__)
            try:
                values = adapter.expand(topic)
                terms.update(str(value).strip() for value in values if str(value).strip())
            except Exception as exc:  # adapter failures are recorded, never hidden
                issues.append(
                    CapabilityIssue(
                        "chemistry entity/term",
                        name,
                        str(exc),
                        "Retry the provider or supply the missing terms in ordinary language.",
                    )
                )
        return tuple(sorted(terms)), issues

    def _discover(
        self,
        topic: str,
        terms: Sequence[str],
        domain_context: Mapping[str, str],
        adapters: Sequence[object],
    ) -> tuple[list[PaperRecord], dict[str, int], list[CapabilityIssue]]:
        papers: dict[str, PaperRecord] = {}
        path_queries = {path: 0 for path, _ in SEARCH_PATHS}
        issues: list[CapabilityIssue] = []
        configured = {getattr(adapter, "name", adapter.__class__.__name__) for adapter in adapters}
        for provider in ("OpenAlex", "Semantic Scholar", "Crossref"):
            if provider not in configured:
                issues.append(
                    CapabilityIssue(
                        "discovery/metadata",
                        provider,
                        "not configured for this run",
                        "Configure this adapter or use another discovery/metadata adapter.",
                    )
                )
        for path, description in SEARCH_PATHS:
            context = "; ".join(
                f"{heading}: {value}"
                for heading, value in domain_context.items()
                if value and not value.lower().startswith("open question")
            )
            query = f"{topic}; {description}; terms: {', '.join(terms)}; domain: {context}"
            for adapter in adapters:
                name = getattr(adapter, "name", adapter.__class__.__name__)
                try:
                    found = adapter.search(query, path)
                    found_any = False
                    for paper in found:
                        if not isinstance(paper, PaperRecord):
                            raise TypeError("discovery adapter returned a non-PaperRecord")
                        found_any = True
                        classified = self._classify(paper, path)
                        papers[paper.identifier] = self._prefer_record(
                            papers.get(paper.identifier), classified
                        )
                    if found_any:
                        path_queries[path] += 1
                except Exception as exc:  # one provider must not stop other paths
                    issues.append(
                        CapabilityIssue(
                            "discovery/metadata",
                            name,
                            str(exc),
                            "Retry the provider or continue with another configured discovery adapter.",
                        )
                    )
        adaptive_queries = self._adaptive_queries(papers.values())
        for query in adaptive_queries:
            for adapter in adapters:
                name = getattr(adapter, "name", adapter.__class__.__name__)
                try:
                    for paper in adapter.search(query, "adaptive follow-up"):
                        if not isinstance(paper, PaperRecord):
                            raise TypeError("discovery adapter returned a non-PaperRecord")
                        classified = self._classify(paper, "adaptive follow-up")
                        papers[paper.identifier] = self._prefer_record(
                            papers.get(paper.identifier), classified
                        )
                except Exception as exc:
                    issues.append(
                        CapabilityIssue(
                            "adaptive discovery",
                            name,
                            str(exc),
                            "Continue from the saved candidates and retry this follow-up path later.",
                        )
                    )
        return list(papers.values()), path_queries, issues

    def _adaptive_queries(self, papers: Sequence[PaperRecord]) -> tuple[str, ...]:
        queries: set[str] = set()
        for paper in papers:
            if paper.authors:
                queries.add(f"related work and competing groups for authors: {', '.join(paper.authors)}")
            if paper.keywords:
                queries.add(f"mechanism, methods, and counterevidence for: {', '.join(paper.keywords)}")
            if paper.cited_identifiers:
                queries.add(f"citation-neighbour expansion for: {', '.join(paper.cited_identifiers)}")
        return tuple(sorted(queries))

    def _classify(self, paper: PaperRecord, path: str) -> PaperRecord:
        if _layer_name(paper.layer, default=""):
            return paper
        text = " ".join((paper.title, paper.abstract, *paper.keywords)).lower()
        if any(term in text for term in ("conflict", "contradict", "controvers", "debate", "challenge")):
            layer = "controversy"
        elif path == "definitions":
            layer = "background/definition"
        elif path in {"key events", "citation relations"}:
            layer = "anchor/core"
        else:
            layer = "extension"
        return replace(paper, layer=layer)

    def _prefer_record(
        self, previous: PaperRecord | None, candidate: PaperRecord
    ) -> PaperRecord:
        if previous is None:
            return candidate
        priority = {"extension": 0, "background/definition": 1, "anchor/core": 2, "controversy": 3}
        if priority[_layer_name(candidate.layer)] > priority[_layer_name(previous.layer)]:
            return candidate
        return previous

    def _retrieve_and_parse(
        self,
        papers: Sequence[PaperRecord],
        full_text_adapters: Sequence[object],
        parser_adapters: Sequence[object],
    ) -> tuple[list[FullTextResult], list[ParsedDocument], list[CapabilityIssue]]:
        accepted_full_texts: list[FullTextResult] = []
        parsed: list[ParsedDocument] = []
        issues: list[CapabilityIssue] = []
        configured_full_text = {getattr(adapter, "name", adapter.__class__.__name__) for adapter in full_text_adapters}
        configured_parsers = {getattr(adapter, "name", adapter.__class__.__name__) for adapter in parser_adapters}
        for provider in ("Unpaywall", "Europe PMC", "CORE"):
            if provider not in configured_full_text:
                issues.append(
                    CapabilityIssue(
                        "legal full text",
                        provider,
                        "not configured for this run",
                        "Configure a legitimate full-text adapter or provide an authorized PDF.",
                    )
                )
        for provider in PREFERRED_PARSERS:
            if provider not in configured_parsers:
                issues.append(
                    CapabilityIssue(
                        "PDF parsing",
                        provider,
                        "not configured for this run",
                        "Configure the preferred parser or use the documented fallback route.",
                    )
                )
        for paper in papers:
            full_text = None
            pending_access_issue_indexes: list[int] = []
            for adapter in full_text_adapters:
                name = getattr(adapter, "name", adapter.__class__.__name__)
                try:
                    candidate = adapter.fetch(paper)
                    if not isinstance(candidate, FullTextResult):
                        raise TypeError("full-text adapter returned a non-FullTextResult")
                    if candidate.status == "FOUND" and candidate.text:
                        if (
                            candidate.access_basis not in LEGAL_ACCESS_BASES
                            or not candidate.locator.strip()
                        ):
                            pending_access_issue_indexes.append(len(issues))
                            issues.append(
                                CapabilityIssue(
                                    "legal full text",
                                    name,
                                    "missing legal access basis or source locator",
                                    "Use open-access or explicitly user/institution-authorized full text and record its locator.",
                                    blocking=True,
                                )
                            )
                            continue
                        full_text = candidate
                        for index in pending_access_issue_indexes:
                            issues[index] = replace(issues[index], blocking=False)
                        break
                    issues.append(
                        CapabilityIssue(
                            "legal full text",
                            name,
                            "no accessible full text returned",
                            "Try another legitimate repository or provide an authorized PDF.",
                        )
                    )
                except Exception as exc:
                    issues.append(
                        CapabilityIssue(
                            "legal full text",
                            name,
                            str(exc),
                            "Retry or use another legitimate full-text route.",
                        )
                    )
            if full_text is None:
                continue
            accepted_full_texts.append(full_text)
            parsed_for_paper = False
            mineru_succeeded = False
            grobid_succeeded = False
            for adapter in parser_adapters:
                name = getattr(adapter, "name", adapter.__class__.__name__)
                if name == "Docling" and grobid_succeeded:
                    continue
                try:
                    document = adapter.parse(full_text)
                    if not isinstance(document, ParsedDocument):
                        raise TypeError("parser returned a non-ParsedDocument")
                    if not document.locators:
                        raise ValueError(
                            "parser returned no page/section locators for the parsed document"
                        )
                    if full_text.locator not in document.locators:
                        document = replace(document, locators=(full_text.locator, *document.locators))
                    parsed.append(document)
                    parsed_for_paper = True
                    if name == "MinerU":
                        mineru_succeeded = True
                        continue
                    if name == "GROBID":
                        grobid_succeeded = True
                        break
                    if not mineru_succeeded:
                        break
                except Exception as exc:
                    issues.append(
                        CapabilityIssue(
                            "PDF parsing",
                            name,
                            str(exc),
                            "Retry MinerU, then use GROBID or Docling; otherwise provide structured text.",
                        )
                    )
            if not parsed_for_paper:
                # Metadata remains useful even when parsing is degraded.
                continue
        return accepted_full_texts, parsed, issues

    def _uncertainties(
        self,
        papers: Sequence[PaperRecord],
        parsed: Sequence[ParsedDocument],
        issues: Sequence[CapabilityIssue],
        uncovered: Sequence[str],
    ) -> tuple[str, ...]:
        uncertainties = [
            "The candidate set is discovery evidence, not a claim of exhaustive retrieval.",
            "Cross-study comparability and mechanism interpretations require Prototype review.",
        ]
        if uncovered:
            uncertainties.append("Uncovered search paths: " + ", ".join(uncovered) + ".")
        if papers and not parsed:
            uncertainties.append("No paper was structurally parsed; verify key claims against authorized full text.")
        if issues:
            uncertainties.append("Some configured or preferred capabilities degraded; inspect the recovery notes.")
        return tuple(uncertainties)

    def _route_summary(self, config: ResearchConfig) -> str:
        configured = {
            getattr(adapter, "name", adapter.__class__.__name__)
            for group in (config.discovery, config.entities, config.full_text, config.parsers)
            for adapter in group
        }
        lines = ["| Role | Provider | Intended use | Run configuration |", "| --- | --- | --- | --- |"]
        for role, provider, use in DEFAULT_ROUTES:
            state = "configured" if provider in configured else "replaceable / replacement route not configured"
            lines.append(f"| {role} | {provider} | {use} | {state} |")
        return "\n".join(lines)

    def _issue_summary(self, issues: Sequence[CapabilityIssue]) -> str:
        if not issues:
            return "None recorded."
        return "\n".join(
            f"- {issue.capability} / {issue.provider}: {issue.reason}; recovery: {issue.recovery}"
            for issue in issues
        )

    def _persist(self, **values: object) -> None:
        metadata = {
            "kind": "research-evidence",
            "schema": "1",
            "intent_revision": str(values["intent_revision"]),
            "status": str(values["status"]),
            "human_action": str(values["human_action"]),
            "research_handoff": str(values["handoff"] or "NONE"),
            "next_action": str(values["next_action"]),
            "updated": self.today.isoformat(),
        }
        evidence_body = (
            "# Research Evidence Package\n\n"
            "## Research question\n\n"
            "## Project domain context\n\n"
            "## Search paths\n\n"
            "## Terms and chemistry entities\n\n"
            "## Evidence notes\n\n"
            "## Covered directions\n\n"
            "## High-impact uncovered areas\n\n"
            "## Major uncertainties\n\n"
            "## Tool route\n\n"
            "## Tool degradation or HUMAN_ACTION_REQUIRED\n\n"
            "## Research handoff\n\n"
            "## Preserved human edits and conflicts\n\n"
            "## Human notes\n"
        )
        evidence = self._load_or_create(self.evidence_path, metadata, evidence_body)
        evidence = _set_tracked_section(evidence, "Research question", str(values["topic"]))
        domain_lines = "\n".join(
            f"- {heading}: {value}" for heading, value in values["domain_context"].items() if value
        )
        evidence = _set_tracked_section(
            evidence, "Project domain context", domain_lines or "No domain context recorded."
        )
        paths = "\n".join(f"- {path}: {description}" for path, description in SEARCH_PATHS)
        evidence = _set_tracked_section(evidence, "Search paths", paths)
        terms = _merge_lines(
            _section_value(evidence, "Terms and chemistry entities"),
            "\n".join(f"- {term}" for term in values["terms"]),
        )
        evidence = _set_tracked_section(evidence, "Terms and chemistry entities", terms)
        notes = _merge_lines(
            _section_value(evidence, "Evidence notes"),
            self._evidence_notes(values["papers"], values["full_texts"], values["parsed"]),
            placeholders=("No papers discovered; metadata evidence is unavailable until a route is configured.",),
        )
        evidence = _set_tracked_section(evidence, "Evidence notes", notes)
        evidence = _set_tracked_section(
            evidence,
            "Covered directions",
            "\n".join(f"- {item}" for item in values["covered"]) or "- None yet",
        )
        evidence = _set_tracked_section(
            evidence,
            "High-impact uncovered areas",
            "\n".join(f"- {item}" for item in values["uncovered"]) or "- None identified",
        )
        evidence = _set_tracked_section(
            evidence,
            "Major uncertainties",
            "\n".join(f"- {item}" for item in values["uncertainties"]),
        )
        evidence = _set_tracked_section(evidence, "Tool route", str(values["route_summary"]))
        evidence = _set_tracked_section(
            evidence, "Tool degradation or HUMAN_ACTION_REQUIRED", str(values["degradation"])
        )
        handoff = values["handoff"] or "No handoff proposed until a usable discovery route is available."
        evidence = _set_tracked_section(
            evidence,
            "Research handoff",
            f"Proposed next phase: {handoff}\n\n"
            f"Rationale: {values['handoff_rationale']}\n\n"
            f"Next action: {values['next_action']}",
        )
        self.evidence_path.write_text(evidence.rstrip() + "\n", encoding="utf-8")

        literature_metadata = {
            "kind": "layered-literature-set",
            "schema": "1",
            "intent_revision": str(values["intent_revision"]),
            "updated": self.today.isoformat(),
        }
        literature_body = (
            "# Layered Literature Set\n\n"
            "## Anchor/core\n\n"
            "## Extension\n\n"
            "## Background/definition\n\n"
            "## Controversy\n\n"
            "## Preserved human edits and conflicts\n\n"
            "## Human notes\n"
        )
        literature = self._load_or_create(self.literature_path, literature_metadata, literature_body)
        for layer, heading in (
            ("anchor/core", "Anchor/core"),
            ("extension", "Extension"),
            ("background/definition", "Background/definition"),
            ("controversy", "Controversy"),
        ):
            layer_papers = [paper for paper in values["papers"] if _layer_name(paper.layer) == layer]
            entries = _merge_lines(
                _section_value(literature, heading),
                "\n".join(_paper_line(paper) for paper in layer_papers),
                placeholders=("No candidates recorded yet.",),
            ) or "No candidates recorded yet."
            literature = _set_tracked_section(literature, heading, entries)
        self.literature_path.write_text(literature.rstrip() + "\n", encoding="utf-8")

    def _load_or_create(self, path: Path, metadata: Mapping[str, str], body: str) -> str:
        if not path.exists():
            return _document(metadata, body)
        current = path.read_text(encoding="utf-8")
        existing, current_body = _split_frontmatter(current)
        existing.update(metadata)
        return _document(existing, current_body)

    def _evidence_notes(
        self,
        papers: Sequence[PaperRecord],
        full_texts: Sequence[FullTextResult],
        parsed: Sequence[ParsedDocument],
    ) -> str:
        full_text_by_id = {full_text.paper_id: full_text for full_text in full_texts}
        parsed_by_id: dict[str, list[ParsedDocument]] = {}
        for document in parsed:
            parsed_by_id.setdefault(document.paper_id, []).append(document)
        if not papers:
            return "No papers discovered; metadata evidence is unavailable until a route is configured."
        lines: list[str] = []
        for paper in papers:
            full_text = full_text_by_id.get(paper.identifier)
            documents = parsed_by_id.get(paper.identifier, [])
            parsers = ", ".join(document.parser for document in documents) or "none"
            locators = ", ".join(
                locator for document in documents for locator in document.locators
            ) or "not available"
            lines.append(
                f"- {paper.identifier}: {paper.title} ({paper.source or 'unknown source'}); "
                f"full text: {full_text.source if full_text else 'not available'}; "
                f"access basis: {full_text.access_basis if full_text else 'not available'}; "
                f"source locator: {full_text.locator if full_text else 'not available'}; "
                f"structured parse: {'yes' if documents else 'no'}; parsers: {parsers}; "
                f"locators: {locators}"
            )
        return "\n".join(lines)


def _preferred(adapters: Sequence[object], providers: Sequence[str]) -> tuple[object, ...]:
    order = {provider: index for index, provider in enumerate(providers)}
    return tuple(
        sorted(
            adapters,
            key=lambda adapter: order.get(
                getattr(adapter, "name", adapter.__class__.__name__), len(order)
            ),
        )
    )


def _layer_name(layer: str, *, default: str = "extension") -> str:
    normalized = layer.strip().lower().replace(" ", "/")
    aliases = {
        "anchor/core": "anchor/core",
        "anchor": "anchor/core",
        "core": "anchor/core",
        "background": "background/definition",
        "definition": "background/definition",
        "background/definition": "background/definition",
        "controversy": "controversy",
        "extension": "extension",
    }
    return aliases.get(normalized, default)


def _paper_line(paper: PaperRecord) -> str:
    year = f", {paper.year}" if paper.year else ""
    doi = f"; DOI: {paper.doi}" if paper.doi else ""
    return f"- {paper.identifier}: {paper.title}{year}{doi} [source: {paper.source or 'unknown'}]"


def _dedupe_issues(issues: Sequence[CapabilityIssue]) -> list[CapabilityIssue]:
    unique: list[CapabilityIssue] = []
    seen: set[tuple[str, str, str, str, bool]] = set()
    for issue in issues:
        key = (
            issue.capability,
            issue.provider,
            issue.reason,
            issue.recovery,
            issue.blocking,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    return unique


def _uncovered_impact(path: str) -> str:
    reasons = {
        "synonyms": "HIGH - unresolved vocabulary can hide relevant chemistry",
        "definitions": "HIGH - unresolved definitions can invalidate comparisons",
        "methods/materials": "HIGH - missing conditions and systems limit comparability",
        "key events": "MEDIUM - historical turning points may be absent",
        "citation relations": "HIGH - anchor and counterevidence coverage may be weak",
        "authors/groups": "MEDIUM - competing schools or independent replication may be absent",
        "recent developments": "HIGH - the candidate set may not reflect the current frontier",
    }
    return f"{path}: {reasons[path]}"


def _merge_lines(
    existing: str, generated: str, *, placeholders: Sequence[str] = ()
) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for line in (*existing.splitlines(), *generated.splitlines()):
        stripped = line.strip()
        if not stripped or stripped in placeholders or stripped in seen:
            continue
        seen.add(stripped)
        lines.append(line)
    return "\n".join(lines)


def _set_tracked_section(text: str, title: str, value: str) -> str:
    metadata, _ = _split_frontmatter(text)
    old_value = _section_value(text, title)
    hash_key = "generated_" + "".join(
        character if character.isalnum() else "_" for character in title.lower()
    ).strip("_") + "_sha256"
    expected_hash = metadata.get(hash_key)
    actual_hash = _content_hash(old_value)
    if expected_hash and actual_hash != expected_hash and old_value.strip():
        conflicts = _section_value(text, "Preserved human edits and conflicts")
        conflict = (
            f"### Preserved edit from {title}\n\n"
            f"The generated section changed after its last run. Its edited content was preserved:\n\n"
            f"```md\n{old_value.rstrip()}\n```"
        )
        if conflict not in conflicts:
            conflicts = (conflicts.rstrip() + "\n\n" + conflict).strip()
        text = _set_section(text, "Preserved human edits and conflicts", conflicts)
    text = _set_section(text, title, value)
    metadata, body = _split_frontmatter(text)
    metadata[hash_key] = _content_hash(value)
    return _document(metadata, body)


def _content_hash(value: str) -> str:
    normalized = value.strip().replace("\r\n", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _asset_has_direct_edit(path: Path, titles: Sequence[str]) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    metadata, _ = _split_frontmatter(text)
    for title in titles:
        hash_key = "generated_" + "".join(
            character if character.isalnum() else "_" for character in title.lower()
        ).strip("_") + "_sha256"
        expected = metadata.get(hash_key)
        if expected and _content_hash(_section_value(text, title)) != expected:
            return True
    return False
