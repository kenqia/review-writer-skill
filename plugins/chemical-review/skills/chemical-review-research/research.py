"""Chemical Review v2 Research stage.

This module is a document-boundary runner, not an orchestrator.  It owns the
``research/`` directory, exposes real provider adapters with injectable HTTP
transport, and stops at the first missing legal/full-text or binding decision.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, replace
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


STAGE_RESULTS = ("READY_FOR_SYNTHESIS", "WAITING_FOR_USER", "RESEARCH_GAP")
LEGAL_BASES = {"OPEN_ACCESS", "USER_AUTHORIZED", "INSTITUTION_AUTHORIZED"}
SEARCH_PATHS = (
    "synonyms", "definitions", "methods/materials", "key events",
    "citation relations", "authors/groups", "recent developments",
)
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)


class ProviderUnavailable(RuntimeError):
    """A configured provider failed or is not configured."""


class BindingRequired(RuntimeError):
    """A user PDF cannot be bound deterministically."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: Any


class UrllibTransport:
    def request(self, method: str, url: str, *, headers: Mapping[str, str], body: bytes | None = None, timeout: float = 20.0) -> HttpResponse:
        request = Request(url, data=body, headers=dict(headers), method=method.upper())
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read()
                content_type = response.headers.get("content-type", "")
                if "json" in content_type:
                    try:
                        raw_body: Any = json.loads(raw.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        raw_body = raw
                else:
                    raw_body = raw
                return HttpResponse(response.status, dict(response.headers.items()), raw_body)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise ProviderUnavailable("provider request failed; inspect the recorded degradation and retry") from exc


def _json_body(response: HttpResponse) -> Mapping[str, Any]:
    if response.status >= 400:
        raise ProviderUnavailable(f"provider returned HTTP {response.status}")
    if isinstance(response.body, Mapping):
        return response.body
    if isinstance(response.body, bytes):
        try:
            value = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderUnavailable("provider returned malformed JSON") from exc
    elif isinstance(response.body, str):
        try:
            value = json.loads(response.body)
        except json.JSONDecodeError as exc:
            raise ProviderUnavailable("provider returned malformed JSON") from exc
    else:
        value = response.body
    if not isinstance(value, Mapping):
        raise ProviderUnavailable("provider returned an unexpected JSON shape")
    return value


@dataclass(frozen=True)
class ProviderSettings:
    endpoint: str
    timeout: float = 20.0
    retries: int = 1
    budget: int = 20
    credential_name: str = ""
    credential_present: bool = True

    @classmethod
    def from_env(cls, provider: str, default_endpoint: str, *, credential_name: str = "") -> "ProviderSettings":
        prefix = "CHEMICAL_REVIEW_" + re.sub(r"[^A-Z0-9]+", "_", provider.upper())
        endpoint = os.environ.get(prefix + "_ENDPOINT", default_endpoint).strip()
        try:
            timeout = float(os.environ.get(prefix + "_TIMEOUT", "20"))
        except ValueError:
            timeout = 20.0
        try:
            retries = max(0, int(os.environ.get(prefix + "_RETRIES", "1")))
        except ValueError:
            retries = 1
        try:
            budget = max(1, int(os.environ.get(prefix + "_BUDGET", "20")))
        except ValueError:
            budget = 20
        return cls(endpoint, timeout, retries, budget, credential_name, bool(os.environ.get(credential_name, "").strip()) if credential_name else True)


class _Adapter:
    name = "provider"

    def __init__(self, *, settings: ProviderSettings | None = None, transport: Any | None = None):
        self.settings = settings or ProviderSettings.from_env(self.name, "")
        self.transport = transport or UrllibTransport()
        self.calls = 0

    def _request(self, method: str, url: str, *, headers: Mapping[str, str] | None = None, body: bytes | None = None) -> HttpResponse:
        if self.calls >= self.settings.budget:
            raise ProviderUnavailable(f"{self.name} request budget exhausted")
        last: Exception | None = None
        for _attempt in range(self.settings.retries + 1):
            self.calls += 1
            try:
                return self.transport.request(method, url, headers=headers or {"Accept": "application/json"}, body=body, timeout=self.settings.timeout)
            except Exception as exc:  # adapters expose honest degradation, never a false success
                last = exc
        raise ProviderUnavailable(f"{self.name} request failed after configured retries") from last


@dataclass(frozen=True)
class Paper:
    identifier: str
    title: str
    doi: str = ""
    year: int | None = None
    authors: tuple[str, ...] = ()
    provider: str = ""
    abstract: str = ""
    full_text_url: str = ""
    access_basis: str = ""
    priority: str = "NORMAL"
    claim_relevance: str = ""


@dataclass(frozen=True)
class FullTextLocation:
    identifier: str
    url: str
    access_basis: str
    provider: str
    direct_pdf: bool = False
    note: str = ""


class OpenAlexAdapter(_Adapter):
    name = "OpenAlex"

    def __init__(self, *, transport: Any | None = None, settings: ProviderSettings | None = None):
        super().__init__(settings=settings or ProviderSettings.from_env(self.name, "https://api.openalex.org/works"), transport=transport)

    def search(self, query: str, limit: int = 10) -> tuple[Paper, ...]:
        payload = _json_body(self._request("GET", self.settings.endpoint + "?" + urlencode({"search": query, "per-page": min(limit, 200)})))
        values = payload.get("results", [])
        return tuple(Paper(str(row.get("id", "")), str(row.get("title", "Untitled")), str(row.get("doi", "")).replace("https://doi.org/", ""), row.get("publication_year"), provider=self.name, abstract=str(row.get("abstract_inverted_index", ""))) for row in values if isinstance(row, Mapping) and row.get("id"))


class SemanticScholarAdapter(_Adapter):
    name = "Semantic Scholar"

    def __init__(self, *, transport: Any | None = None, settings: ProviderSettings | None = None, api_key: str | None = None):
        self.api_key = api_key if api_key is not None else os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
        super().__init__(settings=settings or ProviderSettings.from_env(self.name, "https://api.semanticscholar.org/graph/v1/paper/search"), transport=transport)

    def search(self, query: str, limit: int = 10) -> tuple[Paper, ...]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        payload = _json_body(self._request("GET", self.settings.endpoint + "?" + urlencode({"query": query, "limit": min(limit, 100), "fields": "title,externalIds,year,authors,abstract"}), headers=headers))
        result: list[Paper] = []
        for row in payload.get("data", []):
            if not isinstance(row, Mapping) or not row.get("paperId"):
                continue
            ids = row.get("externalIds") or {}
            result.append(Paper(f"s2:{row['paperId']}", str(row.get("title") or "Untitled"), str(ids.get("DOI") or ""), row.get("year"), tuple(str(a.get("name")) for a in row.get("authors", []) if isinstance(a, Mapping) and a.get("name")), self.name, str(row.get("abstract") or "")))
        return tuple(result)


class CrossrefAdapter(_Adapter):
    name = "Crossref"

    def __init__(self, *, transport: Any | None = None, settings: ProviderSettings | None = None, mailto: str | None = None):
        self.mailto = mailto if mailto is not None else os.environ.get("CROSSREF_MAILTO", "")
        super().__init__(settings=settings or ProviderSettings.from_env(self.name, "https://api.crossref.org/works"), transport=transport)

    def search(self, query: str, limit: int = 10) -> tuple[Paper, ...]:
        params = {"query": query, "rows": min(limit, 100)}
        if self.mailto:
            params["mailto"] = self.mailto
        payload = _json_body(self._request("GET", self.settings.endpoint + "?" + urlencode(params)))
        result: list[Paper] = []
        for row in (payload.get("message") or {}).get("items", []):
            if isinstance(row, Mapping) and row.get("DOI"):
                result.append(Paper("doi:" + str(row["DOI"]).lower(), str((row.get("title") or ["Untitled"])[0]), str(row["DOI"]), (row.get("published-print") or row.get("published-online") or {}).get("date-parts", [[None]])[0][0], self.name))
        return tuple(result)


class PubChemAdapter(_Adapter):
    name = "PubChem"

    def __init__(self, *, transport: Any | None = None, settings: ProviderSettings | None = None):
        super().__init__(settings=settings or ProviderSettings.from_env(self.name, "https://pubchem.ncbi.nlm.nih.gov/rest/pug"), transport=transport)

    def expand(self, term: str) -> tuple[str, ...]:
        payload = _json_body(self._request("GET", self.settings.endpoint.rstrip("/") + "/compound/name/" + quote(term, safe="") + "/synonyms/JSON"))
        values = (payload.get("InformationList") or {}).get("Information", [])
        return tuple(str(value) for row in values if isinstance(row, Mapping) for value in row.get("Synonym", []) if str(value).strip())


class ChebiAdapter(_Adapter):
    name = "ChEBI"

    def __init__(self, *, transport: Any | None = None, settings: ProviderSettings | None = None):
        super().__init__(settings=settings or ProviderSettings.from_env(self.name, "https://www.ebi.ac.uk/chebi/backend/api/public/es_search/"), transport=transport)

    def expand(self, term: str) -> tuple[str, ...]:
        payload = _json_body(self._request("GET", self.settings.endpoint + "?" + urlencode({"term": term})))
        values = payload.get("results", payload.get("data", []))
        return tuple(str(row.get("name") or row.get("chebiId")) for row in values if isinstance(row, Mapping) and (row.get("name") or row.get("chebiId")))


class UnpaywallAdapter(_Adapter):
    name = "Unpaywall"

    def __init__(self, *, email: str | None = None, transport: Any | None = None, settings: ProviderSettings | None = None):
        self.email = email if email is not None else os.environ.get("UNPAYWALL_EMAIL", "")
        super().__init__(settings=settings or ProviderSettings.from_env(self.name, "https://api.unpaywall.org/v2"), transport=transport)

    def locate(self, doi: str) -> tuple[FullTextLocation, ...]:
        if not self.email.strip():
            raise ProviderUnavailable("Unpaywall requires UNPAYWALL_EMAIL; add it to an untracked env file")
        payload = _json_body(self._request("GET", self.settings.endpoint.rstrip("/") + "/" + quote(doi, safe="") + "?" + urlencode({"email": self.email})))
        locations: list[FullTextLocation] = []
        for row in payload.get("oa_locations", []) + ([payload.get("best_oa_location")] if payload.get("best_oa_location") else []):
            if isinstance(row, Mapping) and row.get("url_for_pdf"):
                locations.append(FullTextLocation("doi:" + doi.lower(), str(row["url_for_pdf"]), "OPEN_ACCESS", self.name, True))
        return tuple(dict.fromkeys(locations))


class EuropePmcAdapter(_Adapter):
    name = "Europe PMC"

    def __init__(self, *, transport: Any | None = None, settings: ProviderSettings | None = None):
        super().__init__(settings=settings or ProviderSettings.from_env(self.name, "https://www.ebi.ac.uk/europepmc/webservices/rest/search"), transport=transport)

    def locate(self, doi: str) -> tuple[FullTextLocation, ...]:
        payload = _json_body(self._request("GET", self.settings.endpoint + "?" + urlencode({"query": f'DOI:"{doi}"', "format": "json"})))
        result: list[FullTextLocation] = []
        for row in (payload.get("resultList") or {}).get("result", []):
            if isinstance(row, Mapping) and row.get("pmcid"):
                pmcid = str(row["pmcid"])
                result.append(FullTextLocation("doi:" + doi.lower(), f"https://europepmc.org/articles/{pmcid}?pdf=render", "OPEN_ACCESS", self.name, True))
        return tuple(result)


class CoreAdapter(_Adapter):
    name = "CORE"

    def __init__(self, *, api_key: str | None = None, transport: Any | None = None, settings: ProviderSettings | None = None):
        self.api_key = api_key if api_key is not None else os.environ.get("CORE_API_KEY", "")
        super().__init__(settings=settings or ProviderSettings.from_env(self.name, "https://api.core.ac.uk/v3/search/works"), transport=transport)

    def locate(self, doi: str) -> tuple[FullTextLocation, ...]:
        if not self.api_key.strip():
            raise ProviderUnavailable("CORE requires CORE_API_KEY; add it to an untracked env file")
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self.api_key}"}
        payload = _json_body(self._request("GET", self.settings.endpoint + "?" + urlencode({"q": f'doi:"{doi}"', "limit": 10}), headers=headers))
        result: list[FullTextLocation] = []
        for row in payload.get("results", []):
            if isinstance(row, Mapping):
                url = row.get("downloadUrl") or row.get("sourceFulltextUrls")
                if isinstance(url, list):
                    url = url[0] if url else ""
                if url:
                    result.append(FullTextLocation("doi:" + doi.lower(), str(url), "OPEN_ACCESS", self.name, str(url).lower().endswith(".pdf")))
                elif row.get("id"):
                    # A repository landing page is a legal location, but is
                    # never treated as a direct PDF download route.
                    result.append(FullTextLocation("doi:" + doi.lower(), f"https://core.ac.uk/works/{row['id']}", "OPEN_ACCESS", self.name, False, "repository landing page; user may need to download manually"))
        return tuple(result)


class MinerUParser:
    name = "MinerU"

    def __init__(self, *, command: str | None = None, endpoint: str | None = None, token: str | None = None, transport: Any | None = None):
        self.command = command if command is not None else os.environ.get("MINERU_COMMAND", "")
        self.endpoint = endpoint if endpoint is not None else os.environ.get("MINERU_ENDPOINT", "")
        self.token = token if token is not None else os.environ.get("MINERU_TOKEN", "")
        self.transport = transport or UrllibTransport()

    @property
    def configured(self) -> bool:
        return bool(self.command.strip() or self.endpoint.strip())

    def parse(self, pdf: Path, identifier: str) -> tuple[tuple[str, ...], tuple[str, ...], str]:
        if self.command.strip():
            command = shlex.split(self.command) + [str(pdf)]
            completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=180)
            if completed.returncode != 0 or not completed.stdout.strip():
                raise ProviderUnavailable("MinerU command failed; inspect parser degradation")
            sections = tuple(part.strip() for part in completed.stdout.replace("\r\n", "\n").split("\f") if part.strip())
            return sections, tuple(f"{pdf.name}#page={i}" for i in range(1, len(sections) + 1)), "MinerU command"
        if self.endpoint.strip():
            headers = {"Content-Type": "application/pdf", "Accept": "application/json"}
            if self.token:
                headers["Authorization"] = "Bearer " + self.token
            response = self.transport.request("POST", self.endpoint, headers=headers, body=pdf.read_bytes(), timeout=180)
            payload = _json_body(response)
            text = payload.get("markdown") or payload.get("text") or payload.get("content")
            if not isinstance(text, str) or not text.strip():
                raise ProviderUnavailable("MinerU endpoint returned no structured text")
            sections = tuple(part.strip() for part in text.split("\f") if part.strip())
            return sections, tuple(f"{pdf.name}#page={i}" for i in range(1, len(sections) + 1)), "MinerU endpoint"
        raise ProviderUnavailable("MinerU is not configured")


def _pdftotext(pdf: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not shutil.which("pdftotext"):
        raise ProviderUnavailable("pdftotext is unavailable")
    completed = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=False, capture_output=True, text=True, timeout=60)
    if completed.returncode != 0 or not completed.stdout.strip():
        raise ProviderUnavailable("pdftotext could not parse the authorized PDF")
    sections = tuple(part.strip() for part in completed.stdout.replace("\r\n", "\n").split("\f") if part.strip())
    return sections, tuple(f"{pdf.name}#page={i}" for i in range(1, len(sections) + 1))


@dataclass(frozen=True)
class ResearchResult:
    status: str
    next_action: str
    papers: tuple[Paper, ...]
    parsed_count: int


class ResearchStage:
    """Run incremental Research and own all artifacts below ``research/``."""

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()
        self.root = self.project_root / "research"
        self.inbox = self.root / "inbox" / "authorized-pdfs"

    def run(
        self,
        *,
        fixture_dir: str | Path | None = None,
        adapters: Sequence[Any] | None = None,
        full_text_adapters: Sequence[Any] | None = None,
        download_transport: Any | None = None,
    ) -> ResearchResult:
        brief = self._confirmed_brief()
        self._ensure_dirs()
        fixture = self._load_fixture(fixture_dir)
        papers = self._discover(brief, fixture, adapters)
        papers = self._locate_full_text(papers, full_text_adapters or ())
        records = self._load_records()
        for paper in papers:
            records[paper.identifier] = {**asdict(paper), "source_id": _source_id(paper.identifier), "local_path": "", "digest": "", "parser": "", "locators": [], "full_text": "UNKNOWN", "failure": ""}
        requests: list[dict[str, str]] = []
        parsed_count = 0
        parsed_fixture = fixture.get("parsed", {}) if isinstance(fixture, Mapping) else {}
        for paper in papers:
            record = records[paper.identifier]
            inbox_pdf = self._find_inbox_pdf(paper)
            if inbox_pdf is not None:
                record["local_path"] = str(inbox_pdf)
                record["digest"] = _digest(inbox_pdf)
                try:
                    parsed = self._parse(inbox_pdf, paper.identifier, parsed_fixture.get(paper.identifier))
                    record.update({"parser": parsed[2], "locators": list(parsed[1]), "full_text": "FOUND", "failure": parsed[3]})
                    self._append_evidence(paper, parsed[0], parsed[1], parsed[2], parsed[3])
                    parsed_count += 1
                except ProviderUnavailable as exc:
                    record.update({"full_text": "FOUND", "parser": "UNPARSED", "failure": str(exc)})
            elif paper.full_text_url and paper.access_basis in LEGAL_BASES and paper.access_basis == "OPEN_ACCESS":
                target = self.root / "fulltext" / (_source_id(paper.identifier) + ".pdf")
                try:
                    self._download(paper.full_text_url, target, transport=download_transport)
                    record.update({"local_path": str(target), "digest": _digest(target), "full_text": "FOUND", "access_basis": "OPEN_ACCESS"})
                    parsed = self._parse(target, paper.identifier, parsed_fixture.get(paper.identifier))
                    record.update({"parser": parsed[2], "locators": list(parsed[1]), "failure": parsed[3]})
                    self._append_evidence(paper, parsed[0], parsed[1], parsed[2], parsed[3])
                    parsed_count += 1
                except ProviderUnavailable as exc:
                    record["failure"] = str(exc)
            else:
                requests.append({
                    "source_id": record["source_id"], "identity": paper.identifier,
                    "title": paper.title, "url": paper.full_text_url or "not-found",
                    "access_basis": paper.access_basis or "AUTHORIZATION_UNCLEAR",
                    "suggested_filename": _source_id(paper.identifier) + ".pdf",
                    "target_inbox": "research/inbox/authorized-pdfs/",
                    "claim_relevance": paper.claim_relevance or "Review core claim; confirm relevance before downloading.",
                    "next_action": "Download only through a legal route, place the PDF in the target inbox, then rerun Research.",
                })
                record.update({"full_text": "WAITING_FOR_USER", "failure": "legal user download required"})
        self._write_records(records)
        self._write_supporting_assets(brief, papers, records, requests)
        if requests:
            status, next_action = "WAITING_FOR_USER", "Complete the finite download queue in download-requests.md, then rerun Research."
        elif parsed_count:
            status, next_action = "READY_FOR_SYNTHESIS", "Synthesis may read research-handoff.md and evidence-notes.md; original PDFs remain authoritative."
        else:
            status, next_action = "RESEARCH_GAP", "Add a verified source, configure a provider, or narrow the confirmed scope; no source fact was invented."
        handoff = self.root / "research-handoff.md"
        handoff.write_text(self._handoff(status, next_action, papers, records, requests), encoding="utf-8")
        return ResearchResult(status, next_action, tuple(papers), parsed_count)

    def _confirmed_brief(self) -> str:
        path = self.project_root / "review-brief.md"
        if not path.is_file():
            raise FileNotFoundError("Intent handoff review-brief.md is missing")
        text = path.read_text(encoding="utf-8")
        first = text.split("---", 2)
        if len(first) < 3 or not re.search(r"^confirmed:\s*true\s*$", first[1], re.M):
            raise RuntimeError("HUMAN_ACTION_REQUIRED: Research requires an explicitly confirmed review brief")
        if (self.project_root / "review-brief.proposed.md").exists():
            raise RuntimeError("HUMAN_ACTION_REQUIRED: a proposed intent change must be confirmed before Research")
        return text

    def _ensure_dirs(self) -> None:
        self.inbox.mkdir(parents=True, exist_ok=True)
        for path in (self.root / "fulltext", self.root / "source-records", self.root / "history"):
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _load_fixture(fixture_dir: str | Path | None) -> Mapping[str, Any]:
        if fixture_dir is None:
            return {}
        path = Path(fixture_dir) / "research.json"
        if not path.is_file():
            raise FileNotFoundError(f"research fixture is missing: {path}")
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, Mapping) else {}

    def _discover(self, brief: str, fixture: Mapping[str, Any], adapters: Sequence[Any] | None) -> list[Paper]:
        if fixture.get("papers"):
            return [_paper_from_mapping(row) for row in fixture["papers"] if isinstance(row, Mapping)]
        topic = _section(brief, "Topic") or _section(brief, "Research question")
        if adapters is None:
            adapters = tuple(adapter() for adapter in (OpenAlexAdapter, SemanticScholarAdapter, CrossrefAdapter) if _provider_allowed(adapter.name))
        found: dict[str, Paper] = {}
        for adapter in adapters:
            try:
                for path in SEARCH_PATHS:
                    for paper in adapter.search(f"{topic}; {path}", limit=5):
                        key = paper.doi.lower() if paper.doi else paper.identifier.lower()
                        found.setdefault(key, paper)
            except (ProviderUnavailable, AttributeError):
                continue
        return list(found.values())

    @staticmethod
    def _locate_full_text(papers: Sequence[Paper], adapters: Sequence[Any]) -> list[Paper]:
        if not adapters:
            return list(papers)
        located: list[Paper] = []
        for paper in papers:
            if paper.full_text_url or not paper.doi:
                located.append(paper)
                continue
            for adapter in adapters:
                try:
                    locations = adapter.locate(paper.doi)
                except (ProviderUnavailable, AttributeError):
                    continue
                if locations:
                    location = locations[0]
                    located.append(replace(paper, full_text_url=location.url, access_basis=location.access_basis, provider=f"{paper.provider}+{getattr(adapter, 'name', 'full-text')}"))
                    break
            else:
                located.append(paper)
        return located

    def _load_records(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for path in sorted((self.root / "source-records").glob("*.md")):
            values: dict[str, Any] = {}
            for line in path.read_text(encoding="utf-8").splitlines():
                if ": " in line:
                    key, value = line.split(": ", 1)
                    values[key] = value
            if values.get("identifier"):
                values["locators"] = [v for v in values.get("locators", "").split(";") if v]
                result[values["identifier"]] = values
        return result

    def _write_records(self, records: Mapping[str, Mapping[str, Any]]) -> None:
        for paper_id, record in records.items():
            path = self.root / "source-records" / (str(record.get("source_id") or _source_id(paper_id)) + ".md")
            values = dict(record)
            lines = ["---", "kind: research-source", "schema: 2", "---", "", f"# {values.get('title', paper_id)}", ""]
            for key in ("source_id", "identifier", "doi", "title", "year", "provider", "full_text_url", "access_basis", "priority", "claim_relevance", "local_path", "digest", "full_text", "parser", "failure"):
                lines.append(f"{key}: {values.get(key, '')}")
            lines.append("locators: " + ";".join(values.get("locators", [])))
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        registry_lines = [
            "# Research Source Registry", "", "Research owns this registry. Original PDFs are authoritative; parser output is a locator-bound reading aid.", "",
            "| Source ID | Identity | Title | Provider | Full-text URL | Access basis | Priority | Full text | Parser | Locator(s) | Digest | Claim relevance | Failure/recovery |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for record in records.values():
            registry_lines.append("| " + " | ".join(str(record.get(key, "none") or "none").replace("|", "\\|") for key in ("source_id", "identifier", "title", "provider", "full_text_url", "access_basis", "priority", "full_text", "parser", "locators", "digest", "claim_relevance", "failure")) + " |")
        (self.root / "source-registry.md").write_text("\n".join(registry_lines) + "\n", encoding="utf-8")

    def _find_inbox_pdf(self, paper: Paper) -> Path | None:
        candidates = list(self.inbox.glob("*.pdf"))
        if not candidates:
            return None
        identity_key = _compact(paper.identifier + " " + paper.doi + " " + _source_id(paper.identifier))
        matches = [path for path in candidates if _compact(path.stem) in identity_key or _compact(path.stem) in _compact(paper.doi)]
        if len(matches) == 1:
            return matches[0]
        manifest = self.inbox / "manifest.md"
        if manifest.is_file():
            for line in manifest.read_text(encoding="utf-8").splitlines():
                if "|" in line and paper.identifier in line:
                    filename = line.split("|")[1].strip()
                    candidate = self.inbox / filename
                    if candidate.is_file():
                        return candidate
        if len(candidates) == 1 and len(paper.identifier) < 4:
            return candidates[0]
        if len(matches) > 1:
            (self.root / "binding-requests.md").write_text("# PDF Binding Requests\n\nAmbiguous files require explicit human mapping in inbox/authorized-pdfs/manifest.md.\n", encoding="utf-8")
        return None

    def _parse(self, pdf: Path, identifier: str, fixture: Any | None) -> tuple[tuple[str, ...], tuple[str, ...], str, str]:
        if isinstance(fixture, Mapping) and fixture.get("sections"):
            return tuple(str(v) for v in fixture["sections"]), tuple(str(v) for v in fixture.get("locators", [])), str(fixture.get("parser", "MinerU")), str(fixture.get("note", "fixture parser route"))
        mineru = MinerUParser()
        if mineru.configured:
            try:
                sections, locators, note = mineru.parse(pdf, identifier)
                return sections, locators, "MinerU", note
            except ProviderUnavailable as exc:
                mineru_error = str(exc)
        else:
            mineru_error = "MinerU not configured"
        sections, locators = _pdftotext(pdf)
        return sections, locators, "pdftotext", f"LOW_FIDELITY_FALLBACK: {mineru_error}; complex layout, figures and tables require original PDF verification."

    def _download(self, url: str, target: Path, *, transport: Any | None = None) -> None:
        response = (transport or UrllibTransport()).request("GET", url, headers={"Accept": "application/pdf"}, timeout=30)
        if response.status >= 400 or not isinstance(response.body, (bytes, bytearray)):
            raise ProviderUnavailable("direct PDF route did not return bytes")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(bytes(response.body))

    def _append_evidence(self, paper: Paper, sections: Sequence[str], locators: Sequence[str], parser: str, note: str) -> None:
        path = self.root / "evidence-notes.md"
        if not path.exists():
            path.write_text("# Evidence Notes\n\nParser output is a reading aid. A SOURCE_FACT is valid only after a human/agent checks the original PDF at the locator.\n", encoding="utf-8")
        existing = path.read_text(encoding="utf-8")
        marker = f"\n## {paper.identifier}\n"
        if marker in existing:
            return
        lines = [marker.rstrip(), "", f"- Title: {paper.title}", f"- Parser: {parser}", f"- Parser note: {note}", "- Evidence boundary: SOURCE_EXCERPT only until original PDF verification."]
        for index, section in enumerate(sections):
            locator = locators[index] if index < len(locators) else f"{paper.identifier}#page={index + 1}"
            excerpt = " ".join(section.split())[:500]
            lines.append(f"- SOURCE_EXCERPT [{paper.identifier} @ {locator}]: {excerpt}")
        path.write_text(existing.rstrip() + "\n" + "\n".join(lines) + "\n", encoding="utf-8")

    def _write_supporting_assets(self, brief: str, papers: Sequence[Paper], records: Mapping[str, Mapping[str, Any]], requests: Sequence[Mapping[str, str]]) -> None:
        (self.root / "search-log.md").write_text("# Search Log\n\n" + "\n".join(f"- {path}: query derived from confirmed brief" for path in SEARCH_PATHS) + "\n", encoding="utf-8")
        (self.root / "comparability-matrix.md").write_text("# Comparability Matrix\n\n| Source | Conditions | Units | Endpoint | Comparable? | Notes |\n| --- | --- | --- | --- | --- | --- |\n" + "\n".join(f"| {record.get('source_id')} | UNKNOWN | UNKNOWN | UNKNOWN | NOT_COMPARABLE until checked | {record.get('claim_relevance', '')} |" for record in records.values()) + "\n", encoding="utf-8")
        (self.root / "research-gaps.md").write_text("# Research Gaps\n\n" + ("\n".join(f"- {request['identity']}: missing full text affects claim: {request['claim_relevance']}" for request in requests) or "- No unresolved download request recorded; claim-level verification remains a human/agent task.") + "\n", encoding="utf-8")
        request_lines = ["# Download Requests", "", "Only use legal routes. Do not bypass login, institutional access, CAPTCHA, or unclear authorization.", ""]
        for request in requests:
            request_lines.extend([f"## {request['source_id']}", ""] + [f"- {key}: {value}" for key, value in request.items()] + [""])
        (self.root / "download-requests.md").write_text("\n".join(request_lines), encoding="utf-8")

    @staticmethod
    def _handoff(status: str, next_action: str, papers: Sequence[Paper], records: Mapping[str, Mapping[str, Any]], requests: Sequence[Mapping[str, str]]) -> str:
        lines = ["# Research Handoff", "", f"Result: {status}", "", f"Next action: {next_action}", "", f"Sources registered: {len(papers)}", f"Parsed full texts: {sum(1 for r in records.values() if r.get('parser'))}", "", "## Ownership", "", "Research owns source-registry.md, evidence-notes.md, download-requests.md, the authorized PDF inbox and this handoff. Synthesis may read them but must not rewrite them.", "", "## Full-text route", "", "MinerU is the formal primary parser when configured. pdftotext is a LOW_FIDELITY_FALLBACK only. Original PDFs remain authoritative.", ""]
        if requests:
            lines.extend(["## Waiting for user", "", "The following core papers need a user download or explicit binding:", ""] + [f"- {request['identity']}: {request['url']} → {request['target_inbox']}" for request in requests] + [""])
        if status == "RESEARCH_GAP":
            lines.extend(["## Evidence boundary", "", "No missing SOURCE_FACT was invented. Synthesis may produce only an explicitly partial, unreviewed, evidence-bounded candidate.", ""])
        return "\n".join(lines)


def _paper_from_mapping(row: Mapping[str, Any]) -> Paper:
    return Paper(str(row.get("identifier") or row.get("doi") or row.get("id") or ""), str(row.get("title") or "Untitled"), str(row.get("doi") or ""), row.get("year"), tuple(str(a) for a in row.get("authors", [])), str(row.get("provider") or "fixture"), str(row.get("abstract") or ""), str(row.get("full_text_url") or ""), str(row.get("access_basis") or ""), str(row.get("priority") or "NORMAL"), str(row.get("claim_relevance") or ""))


def _source_id(identifier: str) -> str:
    compact = re.sub(r"[^a-zA-Z0-9]+", "-", identifier.lower()).strip("-")
    return (compact[:62] or "source") + "-" + hashlib.sha256(identifier.encode()).hexdigest()[:8]


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _section(text: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\s*$([\s\S]*?)(?=^## |\Z)", text, re.M)
    return " ".join(match.group(1).split()) if match else ""


def _provider_allowed(name: str) -> bool:
    return bool(os.environ.get("CHEMICAL_REVIEW_ENABLE_NETWORK", "")) or name == "OpenAlex"


def _configured_full_text_adapters() -> tuple[Any, ...]:
    if not os.environ.get("CHEMICAL_REVIEW_ENABLE_NETWORK", ""):
        return ()
    adapters: list[Any] = [EuropePmcAdapter()]
    if os.environ.get("UNPAYWALL_EMAIL", "").strip():
        adapters.insert(0, UnpaywallAdapter())
    if os.environ.get("CORE_API_KEY", "").strip():
        adapters.append(CoreAdapter())
    return tuple(adapters)


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"\''))


def main() -> int:
    parser = argparse.ArgumentParser(description="Chemical Review v2 Research stage")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--fixture-dir", type=Path)
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    if args.env_file:
        _load_env_file(args.env_file)
    else:
        _load_env_file(args.project / ".env.local")
    result = ResearchStage(args.project).run(
        fixture_dir=args.fixture_dir,
        full_text_adapters=_configured_full_text_adapters(),
    )
    print(json.dumps({"status": result.status, "next_action": result.next_action, "papers": len(result.papers), "parsed": result.parsed_count}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
