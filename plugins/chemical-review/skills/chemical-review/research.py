"""Replaceable, file-backed Research phase capabilities.

Research owns discovery and evidence preparation, not scientific adjudication.
Adapters are deliberately tiny duck-typed seams so a configured API, a local
fixture, or a later provider can be substituted without changing the workflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable, Mapping, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from orchestrator import _document, _section_value, _set_section, _split_frontmatter


class CapabilityUnavailable(RuntimeError):
    """An adapter cannot perform its advertised capability."""


READINESS_LEVELS = ("DISCOVERY_READY", "EVIDENCE_READY", "CLAIM_READY")
_DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)


def canonical_evidence_id(value: str) -> str:
    """Return a stable, non-lossy identity for a DOI or source URL."""

    raw = str(value).strip().strip("<>[]{}\"'")
    if not raw:
        raise ValueError("Evidence identity cannot be blank.")
    raw = raw.replace("\u200b", "")

    if raw.lower().startswith(("http://", "https://")):
        parsed = urlsplit(raw)
        host = (parsed.hostname or "").lower()
        if host in {"doi.org", "dx.doi.org", "www.doi.org"}:
            doi = unquote(parsed.path).lstrip("/").rstrip(".,;)")
            if _DOI_PATTERN.fullmatch(doi):
                return "doi:" + doi.lower()
        if not host:
            return raw
        netloc = host
        try:
            port = parsed.port
        except ValueError:
            port = None
        if port is not None and not (
            (parsed.scheme.lower() == "http" and port == 80)
            or (parsed.scheme.lower() == "https" and port == 443)
        ):
            netloc = f"{netloc}:{port}"
        path = unquote(parsed.path) or "/"
        if path != "/":
            path = path.rstrip("/")
        return urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))

    candidate = raw[4:].strip() if raw.lower().startswith("doi:") else raw
    candidate = candidate.rstrip(".,;)")
    if _DOI_PATTERN.fullmatch(candidate):
        return "doi:" + candidate.lower()
    return raw


canonical_source_identity = canonical_evidence_id


class OpenAlexDiscoveryAdapter:
    """Real OpenAlex Works search adapter with explicit, injectable HTTP I/O."""

    name = "OpenAlex"

    def __init__(
        self,
        *,
        base_url: str = "https://api.openalex.org/works",
        api_key: str = "",
        mailto: str = "",
        per_page: int = 10,
        timeout: float = 20.0,
        requester: Callable[..., bytes] | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("OpenAlex base_url cannot be blank.")
        if per_page < 1 or per_page > 200:
            raise ValueError("OpenAlex per_page must be between 1 and 200.")
        if timeout <= 0:
            raise ValueError("OpenAlex timeout must be positive.")
        self.base_url = base_url.rstrip("?")
        self.api_key = api_key.strip()
        self.mailto = mailto.strip()
        self.per_page = per_page
        self.timeout = timeout
        self.requester = requester or self._request

    @classmethod
    def from_environment(cls) -> "OpenAlexDiscoveryAdapter":
        """Build the adapter from optional environment configuration.

        Values are read but never emitted into research assets or error messages.
        """

        return cls(
            api_key=os.environ.get("OPENALEX_API_KEY", ""),
            mailto=os.environ.get("OPENALEX_MAILTO", ""),
        )

    def search(self, query: str, path: str) -> Sequence[PaperRecord]:
        query = query.strip()
        if not query:
            raise ValueError("OpenAlex search query cannot be blank.")
        parameters = {"search": query, "per-page": str(self.per_page)}
        if self.api_key:
            parameters["api_key"] = self.api_key
        if self.mailto:
            parameters["mailto"] = self.mailto
        request_url = f"{self.base_url}?{urlencode(parameters)}"
        request = Request(
            request_url,
            headers={"Accept": "application/json", "User-Agent": "chemical-review-skill/1.0"},
        )
        try:
            payload = json.loads(self.requester(request, self.timeout).decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            # Never copy the request URL into a persisted issue: it may contain
            # api_key/mailto query parameters supplied by the environment.
            raise CapabilityUnavailable("OpenAlex request failed; retry the configured route.") from exc
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            raise CapabilityUnavailable("OpenAlex returned an unreadable JSON response.") from exc
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            raise CapabilityUnavailable("OpenAlex response did not contain a results list.")
        return tuple(_paper_from_openalex(record) for record in results if isinstance(record, dict))

    @staticmethod
    def _request(request: Request, timeout: float) -> bytes:
        with urlopen(request, timeout=timeout) as response:
            return response.read()


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
    local_path: str = ""


@dataclass(frozen=True)
class FullTextResult:
    paper_id: str
    status: str
    text: str
    source: str
    locator: str = ""
    access_basis: str = ""
    local_path: str = ""


@dataclass(frozen=True)
class ParsedMedia:
    asset_id: str
    asset_type: str
    source_path: str
    locator: str
    caption: str
    page: str = ""
    bbox: tuple[int, int, int, int] | str = ""
    provenance: str = "Extracted from the source paper."
    transform_history: str = "None"


@dataclass(frozen=True)
class ParsedDocument:
    paper_id: str
    parser: str
    sections: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    locators: tuple[str, ...] = ()
    note: str = ""
    media: tuple[ParsedMedia, ...] = ()


@dataclass(frozen=True)
class CapabilityIssue:
    capability: str
    provider: str
    reason: str
    recovery: str
    blocking: bool = False


@dataclass(frozen=True)
class CapabilityStatus:
    """A non-invasive capability probe result.

    Probing only reports the configured adapter surface and local executable
    availability. It never reads or prints credentials and never mutates shell
    or Codex configuration.
    """

    capability: str
    provider: str
    available: bool
    configured: bool
    recommended: bool
    reason: str
    setup_action: str


@dataclass(frozen=True)
class ResearchBudget:
    """Adjustable run limits; ``None`` means this limit is not imposed."""

    max_queries: int | None = None
    max_requests: int | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    max_parser_pages: int | None = None
    max_retries: int | None = None
    max_concurrency: int = 1
    max_no_new_rounds: int | None = None
    min_marginal_gain: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "max_queries",
            "max_requests",
            "max_input_tokens",
            "max_output_tokens",
            "max_parser_pages",
            "max_retries",
            "max_no_new_rounds",
        ):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, int) or value < 0):
                raise ValueError(f"{field_name} must be a non-negative integer or None")
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be positive")
        if self.min_marginal_gain < 0:
            raise ValueError("min_marginal_gain must be non-negative")


# Public spelling used by callers that think in terms of a per-run ledger.
RunBudget = ResearchBudget


@dataclass(frozen=True)
class SourceRecord:
    """Project-local identity and provenance record for one source route."""

    source_id: str
    identity: str
    title: str
    source_kind: str
    provider: str
    access_basis: str
    local_path: str = ""
    content_digest: str = ""
    metadata_status: str = "UNKNOWN"
    full_text_status: str = "UNKNOWN"
    parser_status: str = "UNKNOWN"
    locators: tuple[str, ...] = ()
    media_ids: tuple[str, ...] = ()
    priority: str = "NORMAL"
    failure_reason: str = ""


@dataclass(frozen=True)
class ResearchConfig:
    """Adapters supplied by a user, test, or future integration layer."""

    discovery: Sequence[DiscoveryAdapter] = ()
    entities: Sequence[EntityAdapter] = ()
    full_text: Sequence[FullTextAdapter] = ()
    parsers: Sequence[ParserAdapter] = ()
    user_pdfs: Sequence[str | Path] = ()
    authorized_pdf_dir: str | Path | None = None
    cloud_parser_consent: bool = False
    allow_no_key_fallback: bool = False
    budget: ResearchBudget = field(default_factory=ResearchBudget)
    cache_enabled: bool = True
    run_id: str = ""

    @classmethod
    def default(cls) -> "ResearchConfig":
        """Return the smallest real route; other capabilities remain replaceable fallbacks."""

        return cls(discovery=(OpenAlexDiscoveryAdapter.from_environment(),))

    @classmethod
    def no_key_fallback(cls, **kwargs: object) -> "ResearchConfig":
        """Return a bounded, credential-free configuration.

        The fallback intentionally has no network adapter. Existing local
        PDFs, explicit metadata and later user-provided adapters can still be
        added through keyword arguments.
        """

        kwargs["allow_no_key_fallback"] = True
        kwargs.setdefault("discovery", ())
        return cls(**kwargs)  # type: ignore[arg-type]


class _LocalPdfFullTextAdapter:
    """Expose explicitly supplied PDFs through the normal full-text/parser seam."""

    name = "UserAuthorizedPDF"

    def __init__(self, papers: Sequence[PaperRecord]) -> None:
        self._papers = {paper.identifier: paper for paper in papers}

    def supports(self, paper: PaperRecord) -> bool:
        return paper.identifier in self._papers

    def fetch(self, paper: PaperRecord) -> FullTextResult:
        path = Path(paper.local_path)
        try:
            completed = subprocess.run(
                ["pdftotext", "-layout", str(path), "-"],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return FullTextResult(
                paper.identifier,
                "UNAVAILABLE",
                "",
                self.name,
                locator=f"{path.name}#local-pdf",
                access_basis="USER_AUTHORIZED",
                local_path=str(path),
            )
        if completed.returncode != 0 or not completed.stdout.strip():
            return FullTextResult(
                paper.identifier,
                "UNAVAILABLE",
                "",
                self.name,
                locator=f"{path.name}#local-pdf",
                access_basis="USER_AUTHORIZED",
                local_path=str(path),
            )
        return FullTextResult(
            paper.identifier,
            "FOUND",
            completed.stdout,
            self.name,
            locator=f"{path.name}#local-pdf",
            access_basis="USER_AUTHORIZED",
            local_path=str(path),
        )


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
    readiness: str
    readiness_reason: str
    readiness_missing: tuple[str, ...]
    assets: Mapping[str, str] = field(default_factory=dict)
    coverage: tuple[Mapping[str, object], ...] = ()
    stopping_reason: str = ""
    budget_ledger: Mapping[str, object] = field(default_factory=dict)
    source_registry: tuple[SourceRecord, ...] = ()


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
    "Readiness",
    "Search paths",
    "Terms and chemistry entities",
    "Evidence notes",
    "Covered directions",
    "High-impact uncovered areas",
    "Major uncertainties",
    "Tool route",
    "Tool degradation or HUMAN_ACTION_REQUIRED",
    "Coverage and stopping",
    "Research handoff",
)
LITERATURE_TRACKED_SECTIONS = (
    "Anchor/core",
    "Extension",
    "Background/definition",
    "Controversy",
)

LEDGER_SCHEMA = 1
CACHE_SCHEMA = 1
REGISTRY_SCHEMA = 1


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

    @property
    def registry_path(self) -> Path:
        return self.project_root / "source-registry.md"

    @property
    def coverage_path(self) -> Path:
        return self.project_root / "coverage-matrix.md"

    @property
    def ledger_path(self) -> Path:
        return self.project_root / "run-budget.json"

    @property
    def cache_path(self) -> Path:
        return self.project_root / "research-cache.json"

    @property
    def setup_wizard_path(self) -> Path:
        return self.project_root / "research-setup-wizard.md"

    def run(
        self,
        intent_markdown: str,
        domain_markdown: str,
        config: ResearchConfig | None = None,
        *,
        intent_revision: str = "0",
    ) -> ResearchRunResult:
        config = config or ResearchConfig()
        config = replace(config, user_pdfs=self._authorized_pdf_paths(config))
        budget = config.budget
        ledger = self._load_ledger()
        cache = self._load_cache() if config.cache_enabled else _empty_cache()
        previous_snapshot = {
            key: ledger.get(key, 0)
            for key in (
                "query_count",
                "request_count",
                "input_tokens",
                "output_tokens",
                "concurrency",
                "retries",
                "cache_hits",
                "parser_pages",
            )
        }
        history = ledger.setdefault("run_history", [])
        if isinstance(history, list) and any(value for value in previous_snapshot.values()):
            history.append(previous_snapshot)
        for key in (
            "query_count",
            "request_count",
            "input_tokens",
            "output_tokens",
            "retries",
            "cache_hits",
            "parser_pages",
        ):
            ledger[key] = 0
        # This runner is deliberately sequential; record observed concurrency,
        # while the configured ceiling remains in ledger["budget"].
        ledger["concurrency"] = 1
        ledger["runs_started"] = int(ledger.get("runs_started", 0)) + 1
        ledger["last_run_id"] = config.run_id or self._run_id(intent_markdown, domain_markdown)
        ledger["budget"] = _budget_dict(budget)
        # Persist the reset boundary before any external adapter call so an
        # interrupted run is distinguishable from the previous completed run.
        self._persist_ledger(ledger)
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
        papers, path_queries, discovery_issues, coverage, stopping_reason = self._discover(
            topic,
            terms,
            domain_context,
            discovery_adapters,
            budget=budget,
            cache=cache,
            ledger=ledger,
        )
        issues.extend(discovery_issues)
        local_papers = self._local_pdf_records(config.user_pdfs)
        if local_papers:
            papers.extend(local_papers)
            full_text_adapters = (
                _LocalPdfFullTextAdapter(local_papers),
                *full_text_adapters,
            )
        full_texts, parsed, parsing_issues = self._retrieve_and_parse(
            papers,
            full_text_adapters,
            parser_adapters,
            config=config,
            budget=budget,
            cache=cache,
            ledger=ledger,
        )
        issues.extend(parsing_issues)
        if config.allow_no_key_fallback and not discovery_adapters:
            issues.append(
                CapabilityIssue(
                    "discovery/metadata",
                    "no-key fallback",
                    "NO_KEY_FALLBACK: credential-free bounded discovery selected; external discovery adapters were not configured",
                    "Add a user DOI/题录/PDF or configure an adapter later; rerun resumes from the saved ledger and cache.",
                )
            )
        issues = _dedupe_issues(issues)

        covered = tuple(path for path, _ in SEARCH_PATHS if path_queries.get(path, 0) > 0)
        uncovered = tuple(
            _uncovered_impact(path) for path, _ in SEARCH_PATHS if path_queries.get(path, 0) == 0
        )
        uncertainties = self._uncertainties(papers, parsed, issues, uncovered)
        has_discovery = bool(papers)
        blocking = (
            (not has_discovery and not config.allow_no_key_fallback)
            or any(issue.blocking for issue in issues)
            or human_edit_detected
        )
        status = "WAITING_FOR_HUMAN" if blocking else "READY_FOR_NEXT_PHASE"
        human_action = "REQUIRED" if blocking else "NONE"
        handoff, handoff_rationale = self._handoff(
            papers,
            parsed,
            uncovered,
            issues,
            blocking,
            allow_no_key_fallback=config.allow_no_key_fallback,
        )
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
        elif config.allow_no_key_fallback and not papers:
            next_action = (
                "Review the bounded no-key discovery scope and add DOI, metadata, or authorized PDFs "
                "only where the uncovered directions matter."
            )
        elif config.user_pdfs and not parsed:
            next_action = (
                "Review the registered authorized PDFs and configure a local parser, or explicitly "
                "authorize a cloud parser, to obtain stable page/section locators."
            )
        else:
            next_action = (
                "Review the Research evidence package, covered directions, uncovered high-impact areas, "
                "and uncertainties before accepting the Prototype handoff."
            )

        route_summary = self._route_summary(config)
        degradation = self._issue_summary(issues)
        source_registry = self._source_registry(
            papers,
            full_texts,
            parsed,
            config.user_pdfs,
            issues,
        )
        readiness = "EVIDENCE_READY" if parsed else "DISCOVERY_READY"
        readiness_missing, readiness_reason = self._readiness_details(
            papers, full_texts, parsed, issues, config
        )
        self._persist_ledger(ledger)
        self._persist_cache(cache)
        self._persist_parsed_media(parsed)
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
            coverage=coverage,
            stopping_reason=stopping_reason,
            budget_ledger=ledger,
            source_registry=source_registry,
            setup_wizard=self.setup_wizard(config),
            readiness=readiness,
            readiness_reason=readiness_reason,
            readiness_missing=readiness_missing,
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
                "coverage": json.dumps(coverage, ensure_ascii=False, sort_keys=True),
                "stopping_reason": stopping_reason,
                "source_registry": str(self.registry_path),
                "run_budget": str(self.ledger_path),
                "setup_wizard": str(self.setup_wizard_path),
                "readiness": readiness,
            },
            coverage=tuple(coverage),
            stopping_reason=stopping_reason,
            budget_ledger=dict(ledger),
            source_registry=tuple(source_registry),
            readiness=readiness,
            readiness_reason=readiness_reason,
            readiness_missing=tuple(readiness_missing),
        )

    def _persist_parsed_media(self, parsed: Sequence[ParsedDocument]) -> None:
        media = tuple(item for document in parsed for item in document.media)
        if not media:
            return
        from delivery import FigureAsset, FigureInventory

        inventory = FigureInventory.load(self.project_root)
        for document in parsed:
            for item in document.media:
                if item.asset_id in inventory.assets:
                    continue
                inventory.register_source_asset(
                    FigureAsset(
                        asset_id=item.asset_id,
                        asset_type=item.asset_type,
                        source_id=_source_registry_id(document.paper_id),
                        source_path=item.source_path,
                        locator=item.locator,
                        page=item.page,
                        bbox=item.bbox,
                        caption=item.caption,
                        provenance=item.provenance,
                        transform_history=item.transform_history,
                    )
                )
        inventory.persist()

    def _local_pdf_records(self, paths: Sequence[str | Path]) -> list[PaperRecord]:
        records: list[PaperRecord] = []
        for raw_path in paths:
            path = Path(raw_path)
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except (OSError, PermissionError):
                digest = ""
            identity = f"local-pdf:{digest or path.name}"
            records.append(
                PaperRecord(
                    identifier=identity,
                    title=path.name,
                    source="local project folder",
                    layer="extension",
                    local_path=str(path),
                )
            )
        return records

    def _authorized_pdf_paths(self, config: ResearchConfig) -> tuple[str | Path, ...]:
        paths: list[str | Path] = list(config.user_pdfs)
        if config.authorized_pdf_dir is None:
            return tuple(paths)
        root = Path(config.authorized_pdf_dir)
        if not root.is_dir():
            return tuple(paths)
        # The folder is an explicit user-authorized read set; do not recurse
        # into unrelated project files or follow symlinked directories.
        paths.extend(path for path in sorted(root.glob("*.pdf")) if path.is_file())
        return tuple(dict.fromkeys(paths))

    def _handoff(
        self,
        papers: Sequence[PaperRecord],
        parsed: Sequence[ParsedDocument],
        uncovered: Sequence[str],
        issues: Sequence[CapabilityIssue],
        blocking: bool,
        *,
        allow_no_key_fallback: bool = False,
    ) -> tuple[str | None, str]:
        if blocking:
            return None, "No handoff while a required human action or discovery blocker remains."
        if allow_no_key_fallback and not papers:
            return (
                "PROTOTYPE",
                "A bounded no-key discovery handoff is available: the intent and seven search paths are "
                "saved, while source facts and full-text evidence remain unavailable until the researcher "
                "adds a DOI, metadata record, or authorized PDF.",
            )
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

    def _readiness_details(
        self,
        papers: Sequence[PaperRecord],
        full_texts: Sequence[FullTextResult],
        parsed: Sequence[ParsedDocument],
        issues: Sequence[CapabilityIssue],
        config: ResearchConfig,
    ) -> tuple[tuple[str, ...], str]:
        missing: list[str] = []
        if not papers:
            missing.append("stable source identities")
        if papers and not full_texts:
            missing.append("legal full text with access basis and locator")
        if full_texts and not parsed:
            missing.append("page/section locator-bearing parser output")
        if config.allow_no_key_fallback and not papers:
            return tuple(missing), (
                "DISCOVERY_READY only: no-key fallback preserved the intent and search coverage, "
                "but no source identity or source-fact evidence was supplied."
            )
        if parsed:
            return tuple(missing), (
                "EVIDENCE_READY: legal full text and locator-bearing parser output are available; "
                "claim-level binding and chemical comparability still require downstream review."
            )
        return tuple(missing), "DISCOVERY_READY: metadata discovery is not sufficient for source-fact claims."

    def detect_capabilities(
        self, config: ResearchConfig | None = None
    ) -> tuple[CapabilityStatus, ...]:
        """Probe configured routes without network calls or credential access."""

        config = config or ResearchConfig()
        configured = {
            getattr(adapter, "name", adapter.__class__.__name__)
            for group in (config.discovery, config.entities, config.full_text, config.parsers)
            for adapter in group
        }
        statuses: list[CapabilityStatus] = []
        for capability, provider, _use in DEFAULT_ROUTES:
            is_configured = provider in configured
            local_name = provider.lower().replace(" ", "")
            local_available = bool(shutil.which(local_name)) if capability == "PDF parsing" else False
            available = is_configured or local_available
            if is_configured:
                reason = "adapter configured for this run"
                setup_action = "No setup required; inspect the recorded route and degradation notes."
            elif local_available:
                reason = "a local executable with the provider name is available"
                setup_action = "Connect the local executable through a replaceable adapter."
            else:
                reason = "not configured or locally detected; no external probe was attempted"
                setup_action = f"Configure a {provider} adapter or choose the documented fallback route."
            statuses.append(
                CapabilityStatus(
                    capability=capability,
                    provider=provider,
                    available=available,
                    configured=is_configured,
                    recommended=provider
                    in (*PREFERRED_DISCOVERY, *PREFERRED_ENTITIES, *PREFERRED_FULL_TEXT, *PREFERRED_PARSERS),
                    reason=reason,
                    setup_action=setup_action,
                )
            )
        return tuple(statuses)

    capability_probe = detect_capabilities

    def setup_wizard(self, config: ResearchConfig | None = None) -> str:
        """Render a human-executable setup guide; never edits user configuration."""

        statuses = self.detect_capabilities(config)
        lines = [
            "# Research Setup Wizard",
            "",
            "This is a manual checklist. It does not edit shell startup files, auth files, environment variables, or Codex configuration.",
            "",
            "## Recommended route",
            "",
            "1. Confirm the project scope and authorized source folders.",
            "2. Configure only the adapters needed for the uncovered directions.",
            "3. Rerun Research; the project cache and run ledger will reuse unchanged work.",
            "4. If configuration is declined, use `ResearchConfig.no_key_fallback()` or provide DOI/题录/PDF inputs.",
            "",
            "## Capability probe",
            "",
            "| Capability | Provider | Available | Configured | Recovery/setup action |",
            "| --- | --- | --- | --- | --- |",
        ]
        for status in statuses:
            lines.append(
                f"| {status.capability} | {status.provider} | "
                f"{'yes' if status.available else 'no'} | "
                f"{'yes' if status.configured else 'no'} | {status.setup_action} |"
            )
        lines.extend(
            [
                "",
                "## Project PDF authorization",
                "",
                "User PDFs remain local and are registered with `USER_AUTHORIZED` access basis. A cloud parser may receive them only after explicit project-level consent; otherwise the local or no-key fallback is retained.",
                "",
            ]
        )
        return "\n".join(lines)

    def _run_id(self, intent_markdown: str, domain_markdown: str) -> str:
        digest = hashlib.sha256(
            (intent_markdown + "\n" + domain_markdown).encode("utf-8")
        ).hexdigest()[:12]
        return f"{self.today.isoformat()}-{digest}"

    def _load_ledger(self) -> dict[str, object]:
        if not self.ledger_path.exists():
            return _empty_ledger()
        try:
            value = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return _empty_ledger()
        if not isinstance(value, dict) or value.get("schema") != LEDGER_SCHEMA:
            return _empty_ledger()
        return value

    def _persist_ledger(self, ledger: Mapping[str, object]) -> None:
        self._atomic_write_json(self.ledger_path, ledger)

    def _load_cache(self) -> dict[str, object]:
        if not self.cache_path.exists():
            return _empty_cache()
        try:
            value = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return _empty_cache()
        if not isinstance(value, dict) or value.get("schema") != CACHE_SCHEMA:
            return _empty_cache()
        for key in ("discovery", "full_text", "parsed"):
            if not isinstance(value.get(key), dict):
                value[key] = {}
        return value

    def _persist_cache(self, cache: Mapping[str, object]) -> None:
        self._atomic_write_json(self.cache_path, cache)

    @staticmethod
    def _atomic_write_json(path: Path, value: Mapping[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(dict(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def _source_registry(
        self,
        papers: Sequence[PaperRecord],
        full_texts: Sequence[FullTextResult],
        parsed: Sequence[ParsedDocument],
        user_pdfs: Sequence[str | Path],
        issues: Sequence[CapabilityIssue],
    ) -> tuple[SourceRecord, ...]:
        full_text_by_id = {item.paper_id: item for item in full_texts}
        parsed_by_id: dict[str, list[ParsedDocument]] = {}
        for document in parsed:
            parsed_by_id.setdefault(document.paper_id, []).append(document)
        registry: list[SourceRecord] = []
        for paper in papers:
            if paper.local_path:
                continue
            full_text = full_text_by_id.get(paper.identifier)
            documents = parsed_by_id.get(paper.identifier, [])
            identity = _canonical_identity(paper.doi or paper.identifier)
            registry.append(
                SourceRecord(
                    source_id=_source_registry_id(identity),
                    identity=identity,
                    title=paper.title,
                    source_kind="DISCOVERED_METADATA",
                    provider=paper.source or "unknown",
                    access_basis=full_text.access_basis if full_text else "METADATA_ONLY",
                    metadata_status="DISCOVERED",
                    full_text_status="FOUND" if full_text else "NOT_FOUND",
                    parser_status="PARSED" if documents else "NOT_PARSED",
                    locators=tuple(
                        locator for document in documents for locator in document.locators
                    )
                    or ((full_text.locator,) if full_text and full_text.locator else ()),
                    media_ids=tuple(
                        media.asset_id for document in documents for media in document.media
                    ),
                    priority="NORMAL",
                    failure_reason="" if full_text else "metadata-only; full text not available",
                )
            )
        for raw_path in user_pdfs:
            path = Path(raw_path)
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                status = "REGISTERED"
                failure_reason = ""
            except (OSError, PermissionError) as exc:
                digest = ""
                status = "UNREADABLE"
                failure_reason = _safe_exception(exc)
            identity = f"local-pdf:{digest or path.name}"
            full_text = full_text_by_id.get(identity)
            documents = parsed_by_id.get(identity, [])
            registry.append(
                SourceRecord(
                    source_id=f"user-pdf:{_stable_id(identity)}",
                    identity=identity,
                    title=path.name,
                    source_kind="USER_PDF",
                    provider="local project folder",
                    access_basis="USER_AUTHORIZED",
                    local_path=str(path),
                    content_digest=digest,
                    metadata_status=status,
                    full_text_status="FOUND" if full_text else "LOCAL_FILE",
                    parser_status=(
                        "PARSED"
                        if documents
                        else "PENDING_LOCAL_OR_CONSENTED_CLOUD_PARSE"
                    ),
                    locators=tuple(
                        locator for document in documents for locator in document.locators
                    ) or ((full_text.locator,) if full_text and full_text.locator else ()),
                    media_ids=tuple(
                        media.asset_id for document in documents for media in document.media
                    ),
                    priority="PREFERRED",
                    failure_reason=failure_reason,
                )
            )
        cloud_without_consent = [
            issue.provider
            for issue in issues
            if issue.capability == "PDF parsing" and "consent" in issue.reason.lower()
        ]
        if cloud_without_consent:
            for index, record in enumerate(registry):
                if record.source_kind == "USER_PDF":
                    registry[index] = replace(
                        record,
                        failure_reason=(
                            record.failure_reason + "; " if record.failure_reason else ""
                        )
                        + "cloud parser skipped until project-level consent",
                    )
            for provider in cloud_without_consent:
                registry.append(
                    SourceRecord(
                        source_id=f"parser:{_stable_id(provider)}",
                        identity="cloud-parser-route",
                        title="Project-level PDF upload authorization",
                        source_kind="PARSER_ROUTE",
                        provider=provider,
                        access_basis="USER_AUTHORIZED",
                        parser_status="SKIPPED_NO_CONSENT",
                        priority="BLOCKED",
                        failure_reason="cloud parser skipped until explicit project-level consent",
                    )
                )
        self._write_registry(registry)
        return tuple(registry)

    def _write_registry(self, records: Sequence[SourceRecord]) -> None:
        lines = [
            "---",
            "kind: research-source-registry",
            f"schema: {REGISTRY_SCHEMA}",
            f"updated: {self.today.isoformat()}",
            "---",
            "",
            "# Research Source Registry",
            "",
            "Each route keeps an independent identity. Metadata-only records are discovery evidence, not source facts.",
            "",
            "| Source ID | Title | Identity | Kind | Provider | Local path | Access basis | Priority | Metadata | Full text | Parser | Locator(s) | Media IDs | Digest | Failure/recovery |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for record in records:
            locators = "; ".join(record.locators) or "none"
            failure = record.failure_reason.replace("\n", " ") or "none"
            lines.append(
                "| "
                + " | ".join(
                    (
                        record.source_id,
                        record.title,
                        record.identity,
                        record.source_kind,
                        record.provider,
                        record.local_path or "none",
                        record.access_basis,
                        record.priority,
                        record.metadata_status,
                        record.full_text_status,
                        record.parser_status,
                        locators,
                        "; ".join(record.media_ids) or "none",
                        record.content_digest or "none",
                        failure,
                    )
                )
                + " |"
            )
        if not records:
            lines.extend(("", "No source records yet; add a DOI,题录, or authorized PDF.",))
        self.registry_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

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
                        _safe_exception(exc),
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
        *,
        budget: ResearchBudget | None = None,
        cache: dict[str, object] | None = None,
        ledger: dict[str, object] | None = None,
    ) -> tuple[
        list[PaperRecord],
        dict[str, int],
        list[CapabilityIssue],
        tuple[Mapping[str, object], ...],
        str,
    ]:
        budget = budget or ResearchBudget()
        cache = cache if cache is not None else _empty_cache()
        ledger = ledger if ledger is not None else _empty_ledger()
        papers: dict[str, PaperRecord] = {}
        path_queries = {path: 0 for path, _ in SEARCH_PATHS}
        issues: list[CapabilityIssue] = []
        coverage: list[dict[str, object]] = []
        stopping_reason = "All configured search paths evaluated; stopping remains coverage-based rather than paper-count based."
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
        no_new_rounds = 0
        for path, description in SEARCH_PATHS:
            context = "; ".join(
                f"{heading}: {value}"
                for heading, value in domain_context.items()
                if value and not value.lower().startswith("open question")
            )
            query = f"{topic}; {description}; terms: {', '.join(terms)}; domain: {context}"
            query_tokens = _estimate_tokens(query)
            if _budget_exhausted(ledger, "query_count", budget.max_queries) or _budget_would_exceed(
                ledger, "input_tokens", budget.max_input_tokens, query_tokens
            ):
                stopping_reason = f"Run budget stopped discovery before path '{path}' (max_queries)."
                break
            _ledger_increment(ledger, "query_count")
            path_before = set(papers)
            path_requests = 0
            for adapter in adapters:
                name = getattr(adapter, "name", adapter.__class__.__name__)
                cache_key = _cache_key("discovery", name, path, query)
                cached = _cache_get(cache, "discovery", cache_key)
                if cached is not None:
                    found = tuple(_paper_from_cache(item) for item in cached)
                    _ledger_increment(ledger, "cache_hits")
                    _ledger_event(ledger, "discovery-cache-hit", path=path, provider=name)
                else:
                    if _budget_exhausted(ledger, "request_count", budget.max_requests) or _retry_budget_exhausted(
                        ledger, budget.max_retries
                    ) or _budget_would_exceed(
                        ledger, "input_tokens", budget.max_input_tokens, query_tokens
                    ):
                        stopping_reason = (
                            f"Run budget stopped discovery while querying path '{path}' "
                            "(max_requests)."
                        )
                        break
                    _ledger_increment(ledger, "request_count")
                    _ledger_increment(ledger, "input_tokens", query_tokens)
                    path_requests += 1
                    try:
                        found = tuple(adapter.search(query, path))
                        _cache_put(
                            cache,
                            "discovery",
                            cache_key,
                            [_paper_to_cache(paper) for paper in found if isinstance(paper, PaperRecord)],
                        )
                        output_tokens = sum(
                            _estimate_tokens(paper.title + " " + paper.abstract)
                            for paper in found
                            if isinstance(paper, PaperRecord)
                        )
                        if _budget_would_exceed(
                            ledger, "output_tokens", budget.max_output_tokens, output_tokens
                        ):
                            stopping_reason = (
                                f"Run budget stopped discovery while querying path '{path}' "
                                "(max_output_tokens)."
                            )
                            found = ()
                        else:
                            _ledger_increment(ledger, "output_tokens", output_tokens)
                    except Exception as exc:  # one provider must not stop other paths
                        _ledger_increment(ledger, "retries")
                        issues.append(
                            CapabilityIssue(
                                "discovery/metadata",
                                name,
                                _safe_exception(exc),
                                "Retry the provider or continue with another configured discovery adapter.",
                            )
                        )
                        continue
                try:
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
                            _safe_exception(exc),
                            "Retry the provider or continue with another configured discovery adapter.",
                        )
                    )
            path_new = len(set(papers) - path_before)
            if path_new == 0:
                no_new_rounds += 1
            else:
                no_new_rounds = 0
            coverage.append(
                {
                    "path": path,
                    "description": description,
                    "query_count": 1,
                    "request_count": path_requests,
                    "covered": bool(path_queries[path]),
                    "new_source_count": path_new,
                    "marginal_gain": path_new,
                    "consecutive_no_new_rounds": no_new_rounds,
                }
            )
            self._persist_ledger(ledger)
            self._persist_cache(cache)
            if (
                budget.max_no_new_rounds is not None
                and no_new_rounds >= budget.max_no_new_rounds
                and path_new <= budget.min_marginal_gain
            ):
                stopping_reason = (
                    f"Adaptive stopping after {no_new_rounds} consecutive search paths without "
                    "a new important source; uncovered paths remain listed."
                )
                break
        adaptive_queries = self._adaptive_queries(papers.values())
        for query in adaptive_queries:
            query_tokens = _estimate_tokens(query)
            if _budget_exhausted(ledger, "query_count", budget.max_queries) or _budget_would_exceed(
                ledger, "input_tokens", budget.max_input_tokens, query_tokens
            ):
                stopping_reason = "Run budget stopped adaptive follow-up discovery (max_queries)."
                break
            _ledger_increment(ledger, "query_count")
            for adapter in adapters:
                name = getattr(adapter, "name", adapter.__class__.__name__)
                cache_key = _cache_key("discovery", name, "adaptive follow-up", query)
                cached = _cache_get(cache, "discovery", cache_key)
                if cached is not None:
                    found = tuple(_paper_from_cache(item) for item in cached)
                    _ledger_increment(ledger, "cache_hits")
                else:
                    if _budget_exhausted(ledger, "request_count", budget.max_requests) or _retry_budget_exhausted(
                        ledger, budget.max_retries
                    ) or _budget_would_exceed(
                        ledger, "input_tokens", budget.max_input_tokens, query_tokens
                    ):
                        stopping_reason = "Run budget stopped adaptive follow-up discovery (max_requests)."
                        break
                    _ledger_increment(ledger, "request_count")
                    _ledger_increment(ledger, "input_tokens", query_tokens)
                    try:
                        found = tuple(adapter.search(query, "adaptive follow-up"))
                        output_tokens = sum(
                            _estimate_tokens(paper.title + " " + paper.abstract)
                            for paper in found
                            if isinstance(paper, PaperRecord)
                        )
                        if _budget_would_exceed(
                            ledger, "output_tokens", budget.max_output_tokens, output_tokens
                        ):
                            stopping_reason = (
                                "Run budget stopped adaptive follow-up discovery (max_output_tokens)."
                            )
                            found = ()
                        else:
                            _ledger_increment(ledger, "output_tokens", output_tokens)
                        _cache_put(
                            cache,
                            "discovery",
                            cache_key,
                            [_paper_to_cache(paper) for paper in found if isinstance(paper, PaperRecord)],
                        )
                    except Exception as exc:
                        _ledger_increment(ledger, "retries")
                        issues.append(
                            CapabilityIssue(
                                "adaptive discovery",
                                name,
                                _safe_exception(exc),
                                "Continue from the saved candidates and retry this follow-up path later.",
                            )
                        )
                        continue
                try:
                    for paper in found:
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
                            _safe_exception(exc),
                            "Continue from the saved candidates and retry this follow-up path later.",
                        )
                    )
        self._persist_ledger(ledger)
        self._persist_cache(cache)
        return list(papers.values()), path_queries, issues, tuple(coverage), stopping_reason

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
        *,
        config: ResearchConfig | None = None,
        budget: ResearchBudget | None = None,
        cache: dict[str, object] | None = None,
        ledger: dict[str, object] | None = None,
    ) -> tuple[list[FullTextResult], list[ParsedDocument], list[CapabilityIssue]]:
        config = config or ResearchConfig()
        budget = budget or ResearchBudget()
        cache = cache if cache is not None else _empty_cache()
        ledger = ledger if ledger is not None else _empty_ledger()
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
                supports = getattr(adapter, "supports", None)
                if supports is not None and not supports(paper):
                    continue
                name = getattr(adapter, "name", adapter.__class__.__name__)
                cache_key = _cache_key("full_text", name, paper.identifier, paper.doi)
                cached = _cache_get(cache, "full_text", cache_key)
                if cached is not None:
                    candidate = _full_text_from_cache(cached)
                    _ledger_increment(ledger, "cache_hits")
                else:
                    if _budget_exhausted(ledger, "request_count", budget.max_requests) or _retry_budget_exhausted(
                        ledger, budget.max_retries
                    ):
                        issues.append(
                            CapabilityIssue(
                                "legal full text",
                                name,
                                "run budget exhausted before full-text retrieval",
                                "Resume with a larger request budget or use the saved source registry.",
                            )
                        )
                        break
                    _ledger_increment(ledger, "request_count")
                    try:
                        candidate = adapter.fetch(paper)
                    except Exception as exc:
                        _ledger_increment(ledger, "retries")
                        issues.append(
                            CapabilityIssue(
                                "legal full text",
                                name,
                                _safe_exception(exc),
                                "Retry or use another legitimate full-text route.",
                            )
                        )
                        continue
                    if isinstance(candidate, FullTextResult):
                        _cache_put(cache, "full_text", cache_key, _full_text_to_cache(candidate))
                        _ledger_increment(ledger, "input_tokens", _estimate_tokens(paper.title))
                        candidate_tokens = _estimate_tokens(candidate.text)
                        if _budget_would_exceed(
                            ledger,
                            "output_tokens",
                            budget.max_output_tokens,
                            candidate_tokens,
                        ):
                            issues.append(
                                CapabilityIssue(
                                    "legal full text",
                                    name,
                                    "run budget exhausted before retaining full-text content",
                                    "Resume with a larger output-token budget or inspect the authorized source manually.",
                                )
                            )
                            continue
                        _ledger_increment(ledger, "output_tokens", candidate_tokens)
                try:
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
                    _ledger_increment(ledger, "retries")
                    issues.append(
                        CapabilityIssue(
                            "legal full text",
                            name,
                            _safe_exception(exc),
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
                if _is_cloud_parser(adapter) and not config.cloud_parser_consent:
                    issues.append(
                        CapabilityIssue(
                            "PDF parsing",
                            name,
                            "project-level consent is required before sending a PDF to a cloud parser",
                            "Keep the PDF local, configure a local parser, or record explicit project-level consent and rerun.",
                        )
                    )
                    continue
                cache_key = _cache_key("parsed", name, full_text.paper_id, full_text.locator)
                cached = _cache_get(cache, "parsed", cache_key)
                if cached is not None:
                    document = _parsed_from_cache(cached)
                    _ledger_increment(ledger, "cache_hits")
                    try:
                        if not document.locators or not any(
                            _stable_document_locator(locator) for locator in document.locators
                        ):
                            raise ValueError(
                                "parser returned no page/section locators for the parsed document"
                            )
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
                                _safe_exception(exc),
                                "Retry MinerU, then use GROBID or Docling; otherwise provide structured text.",
                            )
                        )
                    continue
                try:
                    if _budget_exhausted(ledger, "parser_pages", budget.max_parser_pages) or _retry_budget_exhausted(
                        ledger, budget.max_retries
                    ) or _budget_would_exceed(
                        ledger,
                        "input_tokens",
                        budget.max_input_tokens,
                        _estimate_tokens(full_text.text),
                    ):
                        issues.append(
                            CapabilityIssue(
                                "PDF parsing",
                                name,
                                "run budget exhausted before parsing this document",
                                "Resume with a larger parser-page budget or inspect the authorized PDF manually.",
                            )
                        )
                        break
                    _ledger_increment(ledger, "request_count")
                    document = adapter.parse(full_text)
                    if not isinstance(document, ParsedDocument):
                        raise TypeError("parser returned a non-ParsedDocument")
                    if not document.locators or not any(
                        _stable_document_locator(locator) for locator in document.locators
                    ):
                        raise ValueError(
                            "parser returned no page/section locators for the parsed document"
                        )
                    if full_text.locator not in document.locators:
                        document = replace(document, locators=(full_text.locator, *document.locators))
                    parsed.append(document)
                    _cache_put(cache, "parsed", cache_key, _parsed_to_cache(document))
                    _ledger_increment(ledger, "parser_pages", max(1, len(document.locators)))
                    _ledger_increment(
                        ledger,
                        "input_tokens",
                        _estimate_tokens(full_text.text),
                    )
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
                    _ledger_increment(ledger, "retries")
                    issues.append(
                        CapabilityIssue(
                            "PDF parsing",
                            name,
                            _safe_exception(exc),
                            "Retry MinerU, then use GROBID or Docling; otherwise provide structured text.",
                        )
                    )
            if not parsed_for_paper:
                # Metadata remains useful even when parsing is degraded.
                self._persist_ledger(ledger)
                self._persist_cache(cache)
                continue
            self._persist_ledger(ledger)
            self._persist_cache(cache)
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
            "## Readiness\n\n"
            "## Search paths\n\n"
            "## Terms and chemistry entities\n\n"
            "## Evidence notes\n\n"
            "## Covered directions\n\n"
            "## High-impact uncovered areas\n\n"
            "## Major uncertainties\n\n"
            "## Tool route\n\n"
            "## Tool degradation or HUMAN_ACTION_REQUIRED\n\n"
            "## Coverage and stopping\n\n"
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
        evidence = _set_tracked_section(
            evidence,
            "Readiness",
            f"Level: {values.get('readiness', 'DISCOVERY_READY')}\n"
            f"Reason: {values.get('readiness_reason', 'Not recorded.')}\n"
            f"Missing: {', '.join(values.get('readiness_missing', ())) or 'None recorded.'}",
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
        coverage_text = _coverage_text(values.get("coverage", ()), str(values.get("stopping_reason", "")))
        evidence = _set_tracked_section(evidence, "Coverage and stopping", coverage_text)
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
            parsed_ids = {
                canonical_evidence_id(item.paper_id)
                for item in values["parsed"]
            }
            entries = _merge_lines(
                _section_value(literature, heading),
                "\n".join(
                    _paper_line(
                        paper,
                        readiness=(
                            "EVIDENCE_READY"
                            if canonical_evidence_id(paper.identifier) in parsed_ids
                            else "DISCOVERY_READY"
                        ),
                    )
                    for paper in layer_papers
                ),
                placeholders=("No candidates recorded yet.",),
            ) or "No candidates recorded yet."
            literature = _set_tracked_section(literature, heading, entries)
        self.literature_path.write_text(literature.rstrip() + "\n", encoding="utf-8")
        self._write_coverage_matrix(values.get("coverage", ()), str(values.get("stopping_reason", "")))
        self._write_ledger_projection(values.get("budget_ledger", {}))
        self.setup_wizard_path.write_text(
            str(values.get("setup_wizard", self.setup_wizard())), encoding="utf-8"
        )

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

    def _write_coverage_matrix(
        self, coverage: Sequence[Mapping[str, object]], stopping_reason: str
    ) -> None:
        lines = [
            "---",
            "kind: research-coverage-matrix",
            "schema: 1",
            f"updated: {self.today.isoformat()}",
            "---",
            "",
            "# Research Coverage Matrix",
            "",
            "Coverage is a bounded research signal; paper count is not a stopping criterion.",
            "",
            "| Path | Covered | Queries | Requests | New sources | Marginal gain | Consecutive no-new rounds |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for item in coverage:
            lines.append(
                "| "
                + " | ".join(
                    (
                        str(item.get("path", "")),
                        "yes" if item.get("covered") else "no",
                        str(item.get("query_count", 0)),
                        str(item.get("request_count", 0)),
                        str(item.get("new_source_count", 0)),
                        str(item.get("marginal_gain", 0)),
                        str(item.get("consecutive_no_new_rounds", 0)),
                    )
                )
                + " |"
            )
        lines.extend(("", "## Stopping reason", stopping_reason or "Not recorded."))
        self.coverage_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    def _write_ledger_projection(self, ledger: Mapping[str, object]) -> None:
        lines = [
            "# Research Run Ledger",
            "",
            "The JSON run budget is the machine-readable ledger; this is its human-readable projection.",
            "",
        ]
        for key in (
            "query_count",
            "request_count",
            "input_tokens",
            "output_tokens",
            "concurrency",
            "retries",
            "cache_hits",
            "parser_pages",
            "runs_started",
            "last_run_id",
        ):
            lines.append(f"- {key}: {ledger.get(key, 0)}")
        lines.extend(("", "## Budget", "", "```json", json.dumps(ledger.get("budget", {}), ensure_ascii=False, sort_keys=True), "```"))
        (self.project_root / "run-ledger.md").write_text(
            "\n".join(lines).rstrip() + "\n", encoding="utf-8"
        )


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


def _paper_from_openalex(record: Mapping[str, object]) -> PaperRecord:
    identifier = str(record.get("id") or record.get("doi") or "").strip()
    title = str(record.get("title") or "").strip()
    if not identifier or not title:
        raise CapabilityUnavailable("OpenAlex returned a work without an identifier or title.")
    authorships = record.get("authorships") or ()
    authors = tuple(
        str((authorship.get("author") or {}).get("display_name") or "").strip()
        for authorship in authorships
        if isinstance(authorship, Mapping)
        and isinstance(authorship.get("author"), Mapping)
        and str((authorship.get("author") or {}).get("display_name") or "").strip()
    )
    keywords = tuple(
        str(keyword.get("display_name") or "").strip()
        for keyword in (record.get("keywords") or ())
        if isinstance(keyword, Mapping) and str(keyword.get("display_name") or "").strip()
    )
    referenced = tuple(
        str(value).strip()
        for value in (record.get("referenced_works") or ())
        if str(value).strip()
    )
    year = record.get("publication_year")
    publication_year = year if isinstance(year, int) else None
    return PaperRecord(
        identifier=identifier,
        title=title,
        authors=authors,
        year=publication_year,
        source="OpenAlex",
        abstract=_abstract_from_inverted_index(record.get("abstract_inverted_index")),
        doi=str(record.get("doi") or "").strip(),
        keywords=keywords,
        cited_identifiers=referenced,
    )


def _abstract_from_inverted_index(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    tokens: list[tuple[int, str]] = []
    for word, positions in value.items():
        if not isinstance(word, str) or not isinstance(positions, Sequence):
            continue
        for position in positions:
            if isinstance(position, int):
                tokens.append((position, word))
    return " ".join(word for _, word in sorted(tokens))


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


def _paper_line(paper: PaperRecord, *, readiness: str = "DISCOVERY_READY") -> str:
    year = f", {paper.year}" if paper.year else ""
    doi = f"; DOI: {paper.doi}" if paper.doi else ""
    return (
        f"- {paper.identifier}: {paper.title}{year}{doi} "
        f"[source: {paper.source or 'unknown'}; readiness: {readiness}]"
    )


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


def _empty_ledger() -> dict[str, object]:
    return {
        "schema": LEDGER_SCHEMA,
        "query_count": 0,
        "request_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "concurrency": 1,
        "retries": 0,
        "cache_hits": 0,
        "parser_pages": 0,
        "runs_started": 0,
        "last_run_id": "",
        "budget": {},
        "events": [],
    }


def _empty_cache() -> dict[str, object]:
    return {"schema": CACHE_SCHEMA, "discovery": {}, "full_text": {}, "parsed": {}}


def _budget_dict(budget: ResearchBudget) -> dict[str, object]:
    return {
        "max_queries": budget.max_queries,
        "max_requests": budget.max_requests,
        "max_input_tokens": budget.max_input_tokens,
        "max_output_tokens": budget.max_output_tokens,
        "max_parser_pages": budget.max_parser_pages,
        "max_retries": budget.max_retries,
        "max_concurrency": budget.max_concurrency,
        "max_no_new_rounds": budget.max_no_new_rounds,
        "min_marginal_gain": budget.min_marginal_gain,
    }


def _ledger_increment(ledger: dict[str, object], key: str, amount: int = 1) -> None:
    ledger[key] = int(ledger.get(key, 0)) + amount


def _ledger_event(ledger: dict[str, object], event: str, **details: object) -> None:
    events = ledger.setdefault("events", [])
    if not isinstance(events, list):
        events = []
        ledger["events"] = events
    events.append({"event": event, **details})


def _budget_exhausted(ledger: Mapping[str, object], counter: str, limit: int | None) -> bool:
    return limit is not None and int(ledger.get(counter, 0)) >= limit


def _budget_would_exceed(
    ledger: Mapping[str, object],
    counter: str,
    limit: int | None,
    amount: int,
) -> bool:
    """Return whether recording ``amount`` would cross a configured budget."""

    return limit is not None and int(ledger.get(counter, 0)) + amount > limit


def _retry_budget_exhausted(ledger: Mapping[str, object], limit: int | None) -> bool:
    """Allow the initial attempt; stop only after the retry allowance is used."""

    return limit is not None and int(ledger.get("retries", 0)) > limit


def _estimate_tokens(value: str) -> int:
    return max(1, (len(value.strip()) + 3) // 4) if value.strip() else 0


def _safe_exception(exc: BaseException) -> str:
    """Return a non-sensitive adapter failure summary for project assets."""

    message = str(exc).strip()
    safe_fragments = (
        "parser returned no page/section locators",
        "parse failed",
        "no accessible full text returned",
        "run budget exhausted",
    )
    lowered = message.lower()
    for fragment in safe_fragments:
        if fragment in lowered:
            return fragment
    return f"{exc.__class__.__name__} (details redacted)"


def _stable_document_locator(value: str) -> bool:
    normalized = str(value).lower()
    if re.search(r"#\s*local-pdf\b", normalized):
        return False
    return bool(
        re.search(
            r"(?:#|\bp(?:age)?\.?\s*\d+|\bsection\s*[:#]?\s*\w+|\b(?:figure|scheme|table)\s*\d+)",
            normalized,
        )
    )


def _cache_key(kind: str, provider: str, identity: str, context: str = "") -> str:
    raw = "|".join((kind, provider, identity, context))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(cache: Mapping[str, object], kind: str, key: str) -> object | None:
    group = cache.get(kind)
    if not isinstance(group, Mapping):
        return None
    return group.get(key)


def _cache_put(cache: dict[str, object], kind: str, key: str, value: object) -> None:
    group = cache.setdefault(kind, {})
    if not isinstance(group, dict):
        group = {}
        cache[kind] = group
    group[key] = value


def _paper_to_cache(paper: PaperRecord) -> dict[str, object]:
    return {
        "identifier": paper.identifier,
        "title": paper.title,
        "authors": list(paper.authors),
        "year": paper.year,
        "source": paper.source,
        "layer": paper.layer,
        "abstract": paper.abstract,
        "doi": paper.doi,
        "keywords": list(paper.keywords),
        "cited_identifiers": list(paper.cited_identifiers),
        "local_path": paper.local_path,
    }


def _paper_from_cache(value: object) -> PaperRecord:
    if not isinstance(value, Mapping):
        raise ValueError("research cache contains an invalid paper record")
    return PaperRecord(
        identifier=str(value.get("identifier", "")),
        title=str(value.get("title", "")),
        authors=tuple(str(item) for item in value.get("authors", ()) or ()),
        year=value.get("year") if isinstance(value.get("year"), int) else None,
        source=str(value.get("source", "")),
        layer=str(value.get("layer", "")),
        abstract=str(value.get("abstract", "")),
        doi=str(value.get("doi", "")),
        keywords=tuple(str(item) for item in value.get("keywords", ()) or ()),
        cited_identifiers=tuple(
            str(item) for item in value.get("cited_identifiers", ()) or ()
        ),
        local_path=str(value.get("local_path", "")),
    )


def _full_text_to_cache(value: FullTextResult) -> dict[str, str]:
    return {
        "paper_id": value.paper_id,
        "status": value.status,
        "text": value.text,
        "source": value.source,
        "locator": value.locator,
        "access_basis": value.access_basis,
        "local_path": value.local_path,
    }


def _full_text_from_cache(value: object) -> FullTextResult:
    if not isinstance(value, Mapping):
        raise ValueError("research cache contains an invalid full-text record")
    return FullTextResult(
        paper_id=str(value.get("paper_id", "")),
        status=str(value.get("status", "")),
        text=str(value.get("text", "")),
        source=str(value.get("source", "")),
        locator=str(value.get("locator", "")),
        access_basis=str(value.get("access_basis", "")),
        local_path=str(value.get("local_path", "")),
    )


def _parsed_to_cache(value: ParsedDocument) -> dict[str, object]:
    return {
        "paper_id": value.paper_id,
        "parser": value.parser,
        "sections": list(value.sections),
        "references": list(value.references),
        "locators": list(value.locators),
        "note": value.note,
        "media": [
            {
                "asset_id": item.asset_id,
                "asset_type": item.asset_type,
                "source_path": item.source_path,
                "locator": item.locator,
                "caption": item.caption,
                "page": item.page,
                "bbox": list(item.bbox) if isinstance(item.bbox, tuple) else item.bbox,
                "provenance": item.provenance,
                "transform_history": item.transform_history,
            }
            for item in value.media
        ],
    }


def _parsed_from_cache(value: object) -> ParsedDocument:
    if not isinstance(value, Mapping):
        raise ValueError("research cache contains an invalid parsed record")
    media_values = value.get("media", ()) or ()
    media = tuple(
        ParsedMedia(
            asset_id=str(item.get("asset_id", "")),
            asset_type=str(item.get("asset_type", "FIGURE")),
            source_path=str(item.get("source_path", "")),
            locator=str(item.get("locator", "")),
            caption=str(item.get("caption", "")),
            page=str(item.get("page", "")),
            bbox=(
                tuple(int(coordinate) for coordinate in item.get("bbox", ()))
                if isinstance(item.get("bbox"), list)
                else str(item.get("bbox", ""))
            ),
            provenance=str(item.get("provenance", "Extracted from the source paper.")),
            transform_history=str(item.get("transform_history", "None")),
        )
        for item in media_values
        if isinstance(item, Mapping)
    )
    return ParsedDocument(
        paper_id=str(value.get("paper_id", "")),
        parser=str(value.get("parser", "")),
        sections=tuple(str(item) for item in value.get("sections", ()) or ()),
        references=tuple(str(item) for item in value.get("references", ()) or ()),
        locators=tuple(str(item) for item in value.get("locators", ()) or ()),
        note=str(value.get("note", "")),
        media=media,
    )


def _is_cloud_parser(adapter: object) -> bool:
    if bool(getattr(adapter, "cloud", False)):
        return True
    name = getattr(adapter, "name", adapter.__class__.__name__).lower()
    return any(term in name for term in ("cloud", "remote", "upload"))


def _canonical_identity(value: str) -> str:
    identity = value.strip().lower()
    identity = identity.removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    identity = identity.rstrip("/.")
    return identity or "unknown"


def _source_registry_id(paper_id: str) -> str:
    identity = _canonical_identity(paper_id)
    prefix = "user-pdf" if identity.startswith("local-pdf:") else "paper"
    return f"{prefix}:{_stable_id(identity)}"


def _stable_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _coverage_text(coverage: Sequence[Mapping[str, object]], stopping_reason: str) -> str:
    if not coverage:
        return "No search path completed yet.\n\nStopping reason: " + (stopping_reason or "Not recorded.")
    lines = [
        "| Path | Covered | New sources | Marginal gain | No-new rounds |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for item in coverage:
        lines.append(
            f"| {item.get('path', '')} | {'yes' if item.get('covered') else 'no'} | "
            f"{item.get('new_source_count', 0)} | {item.get('marginal_gain', 0)} | "
            f"{item.get('consecutive_no_new_rounds', 0)} |"
        )
    lines.extend(("", "Stopping reason: " + (stopping_reason or "Not recorded.")))
    return "\n".join(lines)
