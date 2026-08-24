"""Chemical Review v2 Research stage.

This module is a document-boundary runner, not an orchestrator.  It owns the
``research/`` directory, exposes real provider adapters with injectable HTTP
transport, and stops at the first missing legal/full-text or binding decision.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, replace
from datetime import datetime, timezone
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
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


STAGE_RESULTS = ("READY_FOR_SYNTHESIS", "WAITING_FOR_USER", "RESEARCH_GAP")
LEGAL_BASES = {"OPEN_ACCESS", "USER_AUTHORIZED", "INSTITUTION_AUTHORIZED"}
SEARCH_PATHS = (
    "synonyms", "definitions", "methods/materials", "key events",
    "citation relations", "authors/groups", "recent developments",
)
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
_SENSITIVE_QUERY_RE = re.compile(
    r"([?&#;](?:api[_-]?key|access[_-]?token|auth(?:orization)?|password|secret|token|key|sig(?:nature)?|bearer|credential|x-amz-(?:credential|signature|security-token)|x-goog-(?:credential|signature)|aws[_-]?access[_-]?key[_-]?id)(?:=|:))[^&#;\s]+",
    re.I,
)
_SENSITIVE_HEADER_RE = re.compile(r"(\b(?:authorization|x-api-key)\s*:\s*(?:bearer\s+)?)[^\s,;]+", re.I)
_SENSITIVE_USERINFO_RE = re.compile(r"(\bhttps?://)[^\s/?#]+@", re.I)
_SENSITIVE_URL_KEYS = {
    "api_key", "apikey", "access_token", "auth", "authorization", "credential",
    "key", "secret", "sig", "signature", "token", "x-api-key", "x-amz-credential", "x-amz-signature",
    "x-amz-security-token", "x-goog-credential", "x-goog-signature", "awsaccesskeyid", "aws_access_key_id",
    "bearer",
}


class ProviderUnavailable(RuntimeError):
    """A configured provider failed or is not configured."""


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


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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
        self.last_error = ""

    def _request(self, method: str, url: str, *, headers: Mapping[str, str] | None = None, body: bytes | None = None) -> HttpResponse:
        if self.calls >= self.settings.budget:
            raise ProviderUnavailable(f"{self.name} request budget exhausted")
        last: Exception | None = None
        for _attempt in range(self.settings.retries + 1):
            self.calls += 1
            try:
                response = self.transport.request(method, url, headers=headers or {"Accept": "application/json"}, body=body, timeout=self.settings.timeout)
                if response.status >= 400:
                    self.last_error = _safe_error(
                        f"{method} {url} -> provider returned HTTP {response.status}",
                        secrets=self._credential_values(),
                    )
                return response
            except Exception as exc:  # adapters expose honest degradation, never a false success
                last = exc
                self.last_error = _safe_error(str(exc), secrets=self._credential_values())
        raise ProviderUnavailable(f"{self.name} request failed after configured retries") from last

    def _credential_values(self) -> tuple[str, ...]:
        return tuple(
            value.strip()
            for name in ("api_key", "token")
            if (value := getattr(self, name, ""))
            and isinstance(value, str)
            and value.strip()
        )

    def _json(self, response: HttpResponse) -> Mapping[str, Any]:
        try:
            return _json_body(response)
        except ProviderUnavailable as exc:
            self.last_error = _safe_error(str(exc), secrets=self._credential_values())
            raise


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
    full_text_direct: bool = False
    non_substitutability: str = ""


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

    def __init__(self, *, transport: Any | None = None, settings: ProviderSettings | None = None, api_key: str | None = None, mailto: str | None = None):
        self.api_key = api_key if api_key is not None else os.environ.get("OPENALEX_API_KEY", "")
        self.mailto = mailto if mailto is not None else os.environ.get("OPENALEX_MAILTO", "")
        super().__init__(settings=settings or ProviderSettings.from_env(self.name, "https://api.openalex.org/works"), transport=transport)

    def search(self, query: str, limit: int = 10) -> tuple[Paper, ...]:
        params: dict[str, object] = {"search": query, "per-page": min(limit, 200)}
        if self.api_key:
            params["api_key"] = self.api_key
        if self.mailto:
            params["mailto"] = self.mailto
        payload = self._json(self._request("GET", self.settings.endpoint + "?" + urlencode(params)))
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
        payload = self._json(self._request("GET", self.settings.endpoint + "?" + urlencode({"query": query, "limit": min(limit, 100), "fields": "title,externalIds,year,authors,abstract"}), headers=headers))
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
        payload = self._json(self._request("GET", self.settings.endpoint + "?" + urlencode(params)))
        result: list[Paper] = []
        for row in (payload.get("message") or {}).get("items", []):
            if isinstance(row, Mapping) and row.get("DOI"):
                result.append(
                    Paper(
                        identifier="doi:" + str(row["DOI"]).lower(),
                        title=str((row.get("title") or ["Untitled"])[0]),
                        doi=str(row["DOI"]),
                        year=(row.get("published-print") or row.get("published-online") or {}).get("date-parts", [[None]])[0][0],
                        provider=self.name,
                    )
                )
        return tuple(result)


class PubChemAdapter(_Adapter):
    name = "PubChem"

    def __init__(self, *, transport: Any | None = None, settings: ProviderSettings | None = None):
        super().__init__(settings=settings or ProviderSettings.from_env(self.name, "https://pubchem.ncbi.nlm.nih.gov/rest/pug"), transport=transport)

    def expand(self, term: str) -> tuple[str, ...]:
        payload = self._json(self._request("GET", self.settings.endpoint.rstrip("/") + "/compound/name/" + quote(term, safe="") + "/synonyms/JSON"))
        values = (payload.get("InformationList") or {}).get("Information", [])
        return tuple(str(value) for row in values if isinstance(row, Mapping) for value in row.get("Synonym", []) if str(value).strip())


class ChebiAdapter(_Adapter):
    name = "ChEBI"

    def __init__(self, *, transport: Any | None = None, settings: ProviderSettings | None = None):
        super().__init__(settings=settings or ProviderSettings.from_env(self.name, "https://www.ebi.ac.uk/chebi/backend/api/public/es_search/"), transport=transport)

    def expand(self, term: str) -> tuple[str, ...]:
        payload = self._json(self._request("GET", self.settings.endpoint + "?" + urlencode({"term": term})))
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
        payload = self._json(self._request("GET", self.settings.endpoint.rstrip("/") + "/" + quote(doi, safe="") + "?" + urlencode({"email": self.email})))
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
        payload = self._json(self._request("GET", self.settings.endpoint + "?" + urlencode({"query": f'DOI:"{doi}"', "format": "json"})))
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
        payload = self._json(self._request("GET", self.settings.endpoint + "?" + urlencode({"q": f'doi:"{doi}"', "limit": 10}), headers=headers))
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
            try:
                completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=180)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ProviderUnavailable("MinerU command failed; inspect parser degradation") from exc
            if completed.returncode != 0 or not completed.stdout.strip():
                raise ProviderUnavailable("MinerU command failed; inspect parser degradation")
            sections = tuple(part.strip() for part in completed.stdout.replace("\r\n", "\n").split("\f") if part.strip())
            return sections, tuple(f"{pdf.name}#page={i}" for i in range(1, len(sections) + 1)), "MinerU command"
        if self.endpoint.strip():
            headers = {"Content-Type": "application/pdf", "Accept": "application/json"}
            if self.token:
                headers["Authorization"] = "Bearer " + self.token
            try:
                response = self.transport.request("POST", self.endpoint, headers=headers, body=pdf.read_bytes(), timeout=180)
            except Exception as exc:
                raise ProviderUnavailable("MinerU endpoint request failed; inspect parser degradation") from exc
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
        entity_adapters: Sequence[Any] | None = None,
        full_text_adapters: Sequence[Any] | None = None,
        download_transport: Any | None = None,
    ) -> ResearchResult:
        brief = self._confirmed_brief()
        self._ensure_dirs()
        fixture = self._load_fixture(fixture_dir)
        if adapters is None:
            adapters = _configured_discovery_adapters()
        if entity_adapters is None:
            entity_adapters = _configured_entity_adapters()
        if full_text_adapters is None:
            full_text_adapters = _configured_full_text_adapters()
        terms, entity_failures = self._expand_entities(brief, entity_adapters)
        papers = self._discover(brief, fixture, adapters, terms=terms)
        papers = self._locate_full_text(papers, full_text_adapters)
        records = self._load_records()
        for paper in papers:
            records[paper.identifier] = {**asdict(paper), "source_id": _source_id(paper.identifier), "full_text_url_status": _url_status(paper.full_text_url), "local_path": "", "digest": "", "parser": "", "locators": [], "full_text": "UNKNOWN", "failure": ""}
        requests: list[dict[str, str]] = []
        pending_requests: list[dict[str, str]] = []
        research_gap = False
        parsed_count = 0
        parsed_fixture = fixture.get("parsed", {}) if isinstance(fixture, Mapping) else {}
        for paper in papers:
            record = records[paper.identifier]
            safe_full_text_url = _persisted_url(paper.full_text_url)
            inbox_pdf = self._find_inbox_pdf(paper)
            if inbox_pdf is not None:
                record["local_path"] = str(inbox_pdf)
                record["digest"] = _digest(inbox_pdf)
                record["access_basis"] = "USER_AUTHORIZED"
                record["downloaded_at"] = "USER_PROVIDED_TIME_NOT_OBSERVED"
                try:
                    parsed = self._parse(inbox_pdf, paper.identifier, parsed_fixture.get(paper.identifier))
                    record.update({"parser": parsed[2], "locators": list(parsed[1]), "full_text": "FOUND", "failure": parsed[3]})
                    self._append_evidence(paper, parsed[0], parsed[1], parsed[2], parsed[3])
                    parsed_count += 1
                except ProviderUnavailable as exc:
                    research_gap = True
                    record.update({"full_text": "FOUND", "parser": "UNPARSED", "failure": _safe_error(str(exc))})
            elif safe_full_text_url and paper.full_text_direct and paper.access_basis == "OPEN_ACCESS":
                target = self.root / "fulltext" / (_source_id(paper.identifier) + ".pdf")
                try:
                    self._download(safe_full_text_url, target, transport=download_transport)
                    record.update({"local_path": str(target), "digest": _digest(target), "full_text": "FOUND", "access_basis": "OPEN_ACCESS", "downloaded_at": _now()})
                    parsed = self._parse(target, paper.identifier, parsed_fixture.get(paper.identifier))
                    record.update({"parser": parsed[2], "locators": list(parsed[1]), "failure": parsed[3]})
                    self._append_evidence(paper, parsed[0], parsed[1], parsed[2], parsed[3])
                    parsed_count += 1
                except ProviderUnavailable as exc:
                    failure = _safe_error(str(exc))
                    research_gap = True
                    record.update({"full_text": "WAITING_FOR_USER", "failure": failure})
                    if _download_priority(paper) > 0:
                        pending_requests.append(self._download_request(paper, record, reason=failure))
                    else:
                        research_gap = True
            else:
                failure = "legal user download required" if paper.full_text_url else "no legal full-text URL was located"
                record.update({"full_text": "WAITING_FOR_USER" if paper.full_text_url else "MISSING", "failure": failure})
                if paper.full_text_url and _download_priority(paper) > 0:
                    pending_requests.append(self._download_request(paper, record, reason=failure))
                else:
                    research_gap = True
        pending_requests.sort(key=lambda item: (-int(item["priority_score"]), item["source_id"]))
        requests = [{key: value for key, value in request.items() if key != "priority_score"} for request in pending_requests]
        self._write_records(records)
        self._write_supporting_assets(brief, papers, records, requests, terms, entity_failures)
        self._write_provider_status((*adapters, *entity_adapters), full_text_adapters or ())
        if requests:
            status, next_action = "WAITING_FOR_USER", "Complete the finite download queue in download-requests.md, then rerun Research."
        elif parsed_count and not research_gap:
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

    def _discover(self, brief: str, fixture: Mapping[str, Any], adapters: Sequence[Any] | None, *, terms: Sequence[str] = ()) -> list[Paper]:
        if fixture.get("papers"):
            return [_paper_from_mapping(row) for row in fixture["papers"] if isinstance(row, Mapping)]
        topic = _section(brief, "Topic") or _section(brief, "Research question")
        core_claims = _core_claims(brief)
        if adapters is None:
            adapters = _configured_discovery_adapters()
        found: dict[str, Paper] = {}
        for adapter in adapters:
            try:
                for path in SEARCH_PATHS:
                    query = f"{topic}; core claims: {'; '.join(core_claims)}; terms: {', '.join(terms)}; {path}"
                    for paper in adapter.search(query, limit=5):
                        if not paper.claim_relevance:
                            paper = replace(paper, claim_relevance=_candidate_claim_relevance(core_claims, path))
                        key = paper.doi.lower() if paper.doi else paper.identifier.lower()
                        found.setdefault(key, paper)
            except (ProviderUnavailable, AttributeError):
                continue
        return list(found.values())

    @staticmethod
    def _expand_entities(brief: str, adapters: Sequence[Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
        topic = _section(brief, "Topic") or _section(brief, "Research question")
        terms = {topic}
        failures: list[str] = []
        for adapter in adapters:
            try:
                terms.update(str(value).strip() for value in adapter.expand(topic) if str(value).strip())
            except (ProviderUnavailable, AttributeError) as exc:
                credentials = adapter._credential_values() if hasattr(adapter, "_credential_values") else ()
                failures.append(f"{getattr(adapter, 'name', adapter.__class__.__name__)}: {_safe_error(str(exc), secrets=credentials)}")
        return tuple(sorted(terms)), tuple(failures)

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
                    located.append(replace(paper, full_text_url=location.url, full_text_direct=location.direct_pdf, access_basis=location.access_basis, provider=f"{paper.provider}+{getattr(adapter, 'name', 'full-text')}"))
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

    def _write_provider_status(self, discovery: Sequence[Any], full_text: Sequence[Any]) -> None:
        configured = {
            getattr(adapter, "name", adapter.__class__.__name__)
            for adapter in (*discovery, *full_text)
        }
        rows = (
            ("discovery/metadata", "OpenAlex", "configure the adapter or enable the documented network route"),
            ("discovery/metadata", "Semantic Scholar", "set SEMANTIC_SCHOLAR_API_KEY when required and enable the route"),
            ("discovery/metadata", "Crossref", "configure CROSSREF_MAILTO and enable the route"),
            ("chemistry entity/term", "PubChem", "configure the adapter or provide verified terms"),
            ("chemistry entity/term", "ChEBI", "configure the adapter or provide verified terms"),
            ("legal full text", "Unpaywall", "set UNPAYWALL_EMAIL and enable the route"),
            ("legal full text", "Europe PMC", "enable the route or use a legal user download"),
            ("legal full text", "CORE", "set CORE_API_KEY and enable the route"),
            ("PDF parsing", "MinerU", "set MINERU_COMMAND or MINERU_ENDPOINT; pdftotext remains degraded fallback"),
        )
        lines = [
            "# Research Provider Status", "",
            "Missing configuration is real degradation, not a claim that the provider is available.", "",
            "| Capability | Provider | Configured in this run | Failure/degradation | Recovery |",
            "| --- | --- | --- | --- | --- |",
        ]
        for capability, provider, recovery in rows:
            configured_here = provider in configured or (provider == "MinerU" and MinerUParser().configured)
            adapter = next((item for item in (*discovery, *full_text) if getattr(item, "name", "") == provider), None)
            failure = getattr(adapter, "last_error", "") if adapter is not None else ""
            action = "Retry the configured route; no credential value is persisted." if failure else recovery
            lines.append(f"| {capability} | {provider} | {'YES' if configured_here else 'NO'} | {failure or 'none recorded'} | {action} |")
        (self.root / "provider-status.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_records(self, records: Mapping[str, Mapping[str, Any]]) -> None:
        for paper_id, record in records.items():
            path = self.root / "source-records" / (str(record.get("source_id") or _source_id(paper_id)) + ".md")
            values = dict(record)
            lines = ["---", "kind: research-source", "schema: 2", "---", "", f"# {values.get('title', paper_id)}", ""]
            for key in ("source_id", "identifier", "doi", "title", "year", "provider", "full_text_url", "full_text_url_status", "access_basis", "priority", "claim_relevance", "non_substitutability", "local_path", "digest", "downloaded_at", "full_text", "parser", "failure"):
                value = _persisted_url(str(values.get(key, ""))) if key == "full_text_url" else values.get(key, "")
                lines.append(f"{key}: {value}")
            lines.append("locators: " + ";".join(values.get("locators", [])))
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        registry_lines = [
            "# Research Source Registry", "", "Research owns this registry. Original PDFs are authoritative; parser output is a locator-bound reading aid.", "",
            "| Source ID | Identity | Title | Provider | Full-text URL | URL status | Access basis | Priority | Full text | Parser | Locator(s) | Digest | Downloaded at | Claim relevance | Non-substitutability | Failure/recovery |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for record in records.values():
            registry_values = []
            for key in ("source_id", "identifier", "title", "provider", "full_text_url", "full_text_url_status", "access_basis", "priority", "full_text", "parser", "locators", "digest", "downloaded_at", "claim_relevance", "non_substitutability", "failure"):
                value = _persisted_url(str(record.get(key, ""))) if key == "full_text_url" else record.get(key, "none")
                registry_values.append(str(value or "none").replace("|", "\\|"))
            registry_lines.append("| " + " | ".join(registry_values) + " |")
        (self.root / "source-registry.md").write_text("\n".join(registry_lines) + "\n", encoding="utf-8")

    def _find_inbox_pdf(self, paper: Paper) -> Path | None:
        candidates = list(self.inbox.glob("*.pdf"))
        if not candidates:
            return None
        identity_keys = {
            _compact(value)
            for value in (paper.identifier, paper.doi, _source_id(paper.identifier))
            if value
        }
        matches = [path for path in candidates if _compact(path.stem) in identity_keys]
        if len(matches) == 1:
            return matches[0]
        manifest = self.inbox / "manifest.md"
        if manifest.is_file():
            for line in manifest.read_text(encoding="utf-8").splitlines():
                if "|" not in line:
                    continue
                fields = [field.strip() for field in line.strip().strip("|").split("|")]
                if len(fields) < 2 or not any(field in {paper.identifier, paper.doi, _source_id(paper.identifier)} for field in fields):
                    continue
                filename = fields[0] if fields[0].lower().endswith(".pdf") else fields[1]
                candidate = (self.inbox / filename).resolve()
                try:
                    candidate.relative_to(self.inbox.resolve())
                except ValueError:
                    continue
                if candidate.is_file() and candidate.suffix.lower() == ".pdf":
                    return candidate
        if candidates and len(matches) != 1:
            (self.root / "binding-requests.md").write_text(
                "# PDF Binding Requests\n\nAmbiguous or unmatched files require explicit human mapping in inbox/authorized-pdfs/manifest.md.\n\n"
                + "Files: " + ", ".join(path.name for path in candidates) + "\n",
                encoding="utf-8",
            )
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
        try:
            response = (transport or UrllibTransport()).request("GET", url, headers={"Accept": "application/pdf"}, timeout=30)
        except Exception as exc:
            raise ProviderUnavailable("direct PDF route request failed; use the recorded legal URL for manual download") from exc
        if response.status >= 400 or not isinstance(response.body, (bytes, bytearray)):
            raise ProviderUnavailable("direct PDF route did not return bytes")
        content_type = next((str(value) for key, value in response.headers.items() if key.lower() == "content-type"), "").lower()
        if content_type and not (content_type.startswith("application/pdf") or content_type.startswith("application/octet-stream")):
            raise ProviderUnavailable("direct PDF route returned a non-PDF content type")
        if not bytes(response.body)[:1024].lstrip().startswith(b"%PDF"):
            raise ProviderUnavailable("direct PDF route did not return a PDF document")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(bytes(response.body))

    @staticmethod
    def _download_request(paper: Paper, record: Mapping[str, Any], *, reason: str) -> dict[str, str]:
        return {
            "source_id": str(record["source_id"]),
            "identity": paper.identifier,
            "title": paper.title,
            "url": _persisted_url(paper.full_text_url),
            "url_status": _url_status(paper.full_text_url),
            "access_basis": paper.access_basis or "AUTHORIZATION_UNCLEAR",
            "suggested_filename": _source_id(paper.identifier) + ".pdf",
            "target_inbox": "research/inbox/authorized-pdfs/",
            "claim_relevance": paper.claim_relevance or "Core/high-priority source; confirm relevance before downloading.",
            "non_substitutability": paper.non_substitutability or "Not recorded; treat this source as replaceable until reviewed.",
            "priority": paper.priority,
            "priority_score": str(_download_priority(paper)),
            "failure": reason,
            "next_action": (
                "Obtain a fresh legal landing/download URL without embedded credentials, then rerun Research."
                if not _persisted_url(paper.full_text_url)
                else "Download only through a legal route, place the PDF in the target inbox, then rerun Research."
            ),
        }

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

    def _write_supporting_assets(self, brief: str, papers: Sequence[Paper], records: Mapping[str, Mapping[str, Any]], requests: Sequence[Mapping[str, str]], terms: Sequence[str], entity_failures: Sequence[str]) -> None:
        (self.root / "search-log.md").write_text("# Search Log\n\n" + "\n".join(f"- {path}: query derived from confirmed brief and entity terms" for path in SEARCH_PATHS) + "\n", encoding="utf-8")
        (self.root / "terms-and-entities.md").write_text("# Terms and Chemistry Entities\n\n" + "\n".join(f"- {term}" for term in terms) + ("\n\n## Provider degradation\n\n" + "\n".join(f"- {failure}" for failure in entity_failures) if entity_failures else "") + "\n", encoding="utf-8")
        (self.root / "comparability-matrix.md").write_text("# Comparability Matrix\n\n| Source | Conditions | Units | Endpoint | Comparable? | Notes |\n| --- | --- | --- | --- | --- | --- |\n" + "\n".join(f"| {record.get('source_id')} | UNKNOWN | UNKNOWN | UNKNOWN | NOT_COMPARABLE until checked | {record.get('claim_relevance', '')} |" for record in records.values()) + "\n", encoding="utf-8")
        requested_ids = {request["identity"] for request in requests}
        unresolved = [
            record for record in records.values()
            if (record.get("full_text") in {"WAITING_FOR_USER", "MISSING"} or record.get("parser") == "UNPARSED")
            and record.get("identifier") not in requested_ids
        ]
        gap_lines = [
            f"- {request['identity']}: missing full text affects claim: {request['claim_relevance']}"
            for request in requests
        ]
        gap_lines.extend(
            f"- {record.get('identifier')}: {record.get('failure') or 'unresolved research gap'}"
            for record in unresolved
        )
        (self.root / "research-gaps.md").write_text("# Research Gaps\n\n" + ("\n".join(gap_lines) or "- No unresolved download request recorded; claim-level verification remains a human/agent task.") + "\n", encoding="utf-8")
        request_lines = ["# Download Requests", "", "Only use legal routes. Do not bypass login, institutional access, CAPTCHA, or unclear authorization.", ""]
        for request in requests:
            request_lines.extend([f"## {request['source_id']}", ""] + [f"- {key}: {value}" for key, value in request.items()] + [""])
        (self.root / "download-requests.md").write_text("\n".join(request_lines), encoding="utf-8")

    @staticmethod
    def _handoff(status: str, next_action: str, papers: Sequence[Paper], records: Mapping[str, Mapping[str, Any]], requests: Sequence[Mapping[str, str]]) -> str:
        lines = ["# Research Handoff", "", f"Result: {status}", "", f"Next action: {next_action}", "", f"Sources registered: {len(papers)}", f"Parsed full texts: {sum(1 for r in records.values() if r.get('parser'))}", "", "## Ownership", "", "Research owns source-registry.md, provider-status.md, terms-and-entities.md, evidence-notes.md, download-requests.md, the authorized PDF inbox and this handoff. Synthesis may read them but must not rewrite them.", "", "## Full-text route", "", "MinerU is the formal primary parser when configured. pdftotext is a LOW_FIDELITY_FALLBACK only. Original PDFs remain authoritative.", ""]
        if requests:
            lines.extend(["## Waiting for user", "", "The following core papers need a user download or explicit binding:", ""] + [f"- {request['identity']}: {request['url'] or request['url_status']} → {request['target_inbox']}" for request in requests] + [""])
        if status == "RESEARCH_GAP":
            lines.extend(["## Evidence boundary", "", "No missing SOURCE_FACT was invented. Synthesis may produce only an explicitly partial, unreviewed, evidence-bounded candidate.", ""])
        return "\n".join(lines)


def _paper_from_mapping(row: Mapping[str, Any]) -> Paper:
    url = str(row.get("full_text_url") or "")
    direct = bool(row.get("full_text_direct", url.lower().split("?", 1)[0].endswith(".pdf")))
    non_substitutability = row.get("non_substitutability") or row.get("irreplaceability") or row.get("indispensability") or ""
    return Paper(str(row.get("identifier") or row.get("doi") or row.get("id") or ""), str(row.get("title") or "Untitled"), str(row.get("doi") or ""), row.get("year"), tuple(str(a) for a in row.get("authors", [])), str(row.get("provider") or "fixture"), str(row.get("abstract") or ""), url, str(row.get("access_basis") or ""), str(row.get("priority") or "NORMAL"), str(row.get("claim_relevance") or ""), direct, str(non_substitutability))


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


def _core_claims(text: str) -> tuple[str, ...]:
    for heading in ("Core-claim candidates", "Core claims"):
        match = re.search(rf"^## {re.escape(heading)}\s*$([\s\S]*?)(?=^## |\Z)", text, re.M)
        if not match:
            continue
        claims = tuple(
            line.strip()[2:].strip() if line.strip().startswith("- ") else line.strip()
            for line in match.group(1).splitlines()
            if line.strip() and not line.strip().startswith("Open question")
        )
        if claims:
            return claims
    question = _section(text, "Research question")
    return (question,) if question else ("the confirmed review question",)


def _candidate_claim_relevance(core_claims: Sequence[str], search_path: str) -> str:
    claims = "; ".join(core_claims[:5])
    return f"Candidate relevance from {search_path} search for confirmed core claim(s): {claims}. Metadata/title screening still required."


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() not in {"", "0", "false", "no", "off"}


def _configured_discovery_adapters() -> tuple[Any, ...]:
    if not _env_enabled("CHEMICAL_REVIEW_ENABLE_NETWORK"):
        return ()
    return tuple(adapter() for adapter in (OpenAlexAdapter, SemanticScholarAdapter, CrossrefAdapter))


def _configured_full_text_adapters() -> tuple[Any, ...]:
    if not _env_enabled("CHEMICAL_REVIEW_ENABLE_NETWORK"):
        return ()
    adapters: list[Any] = [EuropePmcAdapter()]
    if os.environ.get("UNPAYWALL_EMAIL", "").strip():
        adapters.insert(0, UnpaywallAdapter())
    if os.environ.get("CORE_API_KEY", "").strip():
        adapters.append(CoreAdapter())
    return tuple(adapters)


def _configured_entity_adapters() -> tuple[Any, ...]:
    if not _env_enabled("CHEMICAL_REVIEW_ENABLE_NETWORK"):
        return ()
    return (PubChemAdapter(), ChebiAdapter())


def _download_priority(paper: Paper) -> int:
    if not paper.claim_relevance.strip():
        return 0
    priority = paper.priority.strip().upper()
    score = {"CORE": 3, "HIGH": 2, "IMPORTANT": 2, "NORMAL": 1, "LOW": 0}.get(priority, 1)
    if paper.non_substitutability.strip():
        score += 4
    return score


def _safe_error(value: str, *, secrets: Sequence[str] = ()) -> str:
    redacted, exhausted = _unquote_layers(value)
    if exhausted:
        return "[REDACTED_ENCODED_ERROR]"
    redacted = _SENSITIVE_QUERY_RE.sub(r"\1[REDACTED]", redacted)
    redacted = _SENSITIVE_HEADER_RE.sub(r"\1[REDACTED]", redacted)
    redacted = _SENSITIVE_USERINFO_RE.sub(r"\1[REDACTED]@", redacted)
    for name in ("OPENALEX_API_KEY", "SEMANTIC_SCHOLAR_API_KEY", "CORE_API_KEY", "MINERU_TOKEN"):
        secret = os.environ.get(name, "").strip()
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    for secret in secrets:
        redacted = redacted.replace(secret, "[REDACTED]")
    return redacted[:500]


def _persisted_url(value: str) -> str:
    """Return a URL safe for Markdown/cache, withholding credential-bearing routes."""
    if not value.strip():
        return ""
    try:
        parsed = urlsplit(value)
        query = parse_qsl(parsed.query, keep_blank_values=True)
    except ValueError:
        return ""
    if parsed.username or parsed.password or _url_contains_credentials(value):
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _url_status(value: str) -> str:
    if not value.strip():
        return "NOT_FOUND"
    return "LEGAL_URL" if _persisted_url(value) else "WITHHELD_CREDENTIAL_BEARING_URL"


def _sensitive_url_key(key: str) -> bool:
    lowered = key.lower()
    normalized = key.lower().replace("-", "_")
    known = {value.replace("-", "_") for value in _SENSITIVE_URL_KEYS}
    return lowered in _SENSITIVE_URL_KEYS or normalized in known or any(
        marker in normalized
        for marker in ("token", "signature", "credential", "secret", "accesskey", "access_key", "api_key", "apikey", "authorization")
    )


def _unquote_layers(value: str, *, limit: int = 32) -> tuple[str, bool]:
    decoded = value
    for _ in range(limit):
        next_value = unquote(decoded)
        if next_value == decoded:
            return decoded, False
        decoded = next_value
    return decoded, True


def _url_contains_credentials(value: str, *, depth: int = 0) -> bool:
    """Detect credential parameters in a URL or an encoded nested redirect URL."""
    if depth > 3:
        # Unknown-depth nested URLs are withheld rather than risk persisting a
        # credential hidden behind another redirect/encoding layer.
        return True
    decoded, exhausted = _unquote_layers(value)
    if exhausted:
        return True
    if _SENSITIVE_QUERY_RE.search(decoded) or _SENSITIVE_HEADER_RE.search(decoded):
        return True
    try:
        parsed = urlsplit(decoded)
    except ValueError:
        return True
    if parsed.username or parsed.password:
        return True
    for component in (parsed.query, parsed.fragment.lstrip("?#")):
        for key, nested in parse_qsl(component, keep_blank_values=True):
            if _sensitive_url_key(key) or _url_contains_credentials(nested, depth=depth + 1):
                return True
    return False


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
        entity_adapters=_configured_entity_adapters(),
        full_text_adapters=_configured_full_text_adapters(),
    )
    print(json.dumps({"status": result.status, "next_action": result.next_action, "papers": len(result.papers), "parsed": result.parsed_count}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
