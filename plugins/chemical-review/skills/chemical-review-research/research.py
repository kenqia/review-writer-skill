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
import tempfile
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


STAGE_RESULTS = ("READY_FOR_SYNTHESIS", "WAITING_FOR_USER", "RESEARCH_GAP")
CONFIGURATION_CHOICES = ("configure_and_continue", "accept_degraded", "pause")
LEGAL_BASES = {"OPEN_ACCESS", "USER_AUTHORIZED", "INSTITUTION_AUTHORIZED"}
SEARCH_PATHS = (
    "synonyms", "definitions", "methods/materials", "key events",
    "citation relations", "authors/groups", "recent developments",
)
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
_CHEMISTRY_HINT_RE = re.compile(
    r"(?:molecul|molecular|small[- ]molecule|chem(?:istr|ical)|compound|drug|ligand|"
    r"catalyst|reaction|synthesi|retrosynthesi|nickel|metal|polymer|material|分子|化学|"
    r"化合物|药物|配体|催化|反应|合成|材料|聚合物)",
    re.I,
)
_SEARCH_TERM_ALIASES = (
    ("generative ai", "generative AI"),
    ("生成式 ai", "generative AI"),
    ("molecular discovery", "molecular discovery"),
    ("分子发现", "molecular discovery"),
    ("molecular design", "molecular design"),
    ("分子设计", "molecular design"),
    ("small-molecule", "small molecule"),
    ("small molecule", "small molecule"),
    ("小分子", "small molecule"),
    ("experimental validation", "experimental validation"),
    ("实验验证", "experimental validation"),
    ("closed-loop discovery", "closed-loop discovery"),
    ("closed loop", "closed-loop discovery"),
    ("闭环", "closed-loop discovery"),
    ("retrosynthesis", "retrosynthesis"),
    ("synthesizability", "synthesizability"),
    ("合成", "synthesis"),
    ("novel molecule", "novel molecule"),
    ("新分子", "novel molecule"),
    ("nickel", "nickel"),
)
_SENSITIVE_QUERY_RE = re.compile(
    r"([?&#;](?:api[_-]?key|access[_-]?token|access[_-]?key(?:[_-]?id)?|auth(?:orization)?|password|secret|token|key|sig(?:nature)?|bearer|credential|x[_-]?api[_-]?key|x-amz-(?:credential|signature|security-token)|x-goog-(?:credential|signature)|aws[_-]?access[_-]?key[_-]?id)(?:=|:))[^&#;\s]+",
    re.I,
)
_URL_PARAM_RE = re.compile(r"([?&#;])([^=:#\s&#;]+)([=:])([^&#;\s]+)", re.I)
_SENSITIVE_HEADER_RE = re.compile(r"(\b(?:authorization|x-api-key)\s*:\s*(?:(?:bearer|basic)\s+)?)[^\s,;]+", re.I)
_SENSITIVE_USERINFO_RE = re.compile(r"(\bhttps?://)[^\s/?#]+@", re.I)
_SENSITIVE_URL_KEYS = {
    "api_key", "apikey", "access_token", "auth", "authorization", "credential",
    "key", "secret", "sig", "signature", "token", "x-api-key", "x-amz-credential", "x-amz-signature",
    "x-amz-security-token", "x-goog-credential", "x-goog-signature", "awsaccesskeyid", "aws_access_key_id",
    "bearer",
}


class ProviderUnavailable(RuntimeError):
    """A configured provider failed or is not configured."""


class ConfigurationChoiceRequired(RuntimeError):
    """Research is waiting for an explicit configuration decision."""


class ResearchPaused(RuntimeError):
    """The user explicitly paused Research at the configuration gate."""


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


def _openalex_abstract(value: object) -> str:
    """Reconstruct OpenAlex's inverted-index abstract deterministically."""
    if not isinstance(value, Mapping):
        return str(value or "")
    words: list[tuple[int, str]] = []
    for token, positions in value.items():
        if isinstance(positions, (list, tuple)):
            words.extend((int(position), str(token)) for position in positions if isinstance(position, int))
    return " ".join(token for _position, token in sorted(words))


def _looks_like_mineru_progress(value: str) -> bool:
    lines = [line.strip().lower() for line in value.splitlines() if line.strip()]
    if not lines:
        return False
    return all(line.startswith(("[upload", "[poll", "[convert", "[process", "progress")) for line in lines)


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
        self.last_status = "CONFIGURED"
        self.last_result_count = 0

    def _request(self, method: str, url: str, *, headers: Mapping[str, str] | None = None, body: bytes | None = None) -> HttpResponse:
        if self.calls >= self.settings.budget:
            raise ProviderUnavailable(f"{self.name} request budget exhausted")
        last: Exception | None = None
        for _attempt in range(self.settings.retries + 1):
            self.calls += 1
            try:
                response = self.transport.request(method, url, headers=headers or {"Accept": "application/json"}, body=body, timeout=self.settings.timeout)
                self.last_status = "REACHABLE"
                if response.status >= 400:
                    self.last_status = "FAILED"
                    self.last_error = _safe_error(
                        f"{method} {url} -> provider returned HTTP {response.status}",
                        secrets=self._credential_values(),
                    )
                return response
            except Exception as exc:  # adapters expose honest degradation, never a false success
                last = exc
                self.last_status = "FAILED"
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

    def _mark_results(self, count: int) -> None:
        self.last_result_count = int(count)
        self.last_status = "USABLE_RESULTS" if count else "REACHABLE"


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
    publication_type: str = "journal-article"
    query_family: str = ""
    version: str = ""


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
        result = tuple(
            Paper(
                str(row.get("id", "")),
                str(row.get("title", "Untitled")),
                str(row.get("doi", "")).replace("https://doi.org/", ""),
                row.get("publication_year"),
                provider=self.name,
                abstract=_openalex_abstract(row.get("abstract_inverted_index")),
                publication_type=str(row.get("type") or "journal-article"),
            )
            for row in values
            if isinstance(row, Mapping) and row.get("id")
        )
        self._mark_results(len(result))
        return result


class SemanticScholarAdapter(_Adapter):
    name = "Semantic Scholar"

    def __init__(self, *, transport: Any | None = None, settings: ProviderSettings | None = None, api_key: str | None = None):
        self.api_key = api_key if api_key is not None else os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
        super().__init__(settings=settings or ProviderSettings.from_env(self.name, "https://api.semanticscholar.org/graph/v1/paper/search"), transport=transport)

    def search(self, query: str, limit: int = 10) -> tuple[Paper, ...]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        payload = self._json(self._request("GET", self.settings.endpoint + "?" + urlencode({"query": query, "limit": min(limit, 100), "fields": "title,externalIds,year,authors,abstract,publicationTypes"}), headers=headers))
        result: list[Paper] = []
        for row in payload.get("data", []):
            if not isinstance(row, Mapping) or not row.get("paperId"):
                continue
            ids = row.get("externalIds") or {}
            publication_types = row.get("publicationTypes") or ()
            publication_type = str(publication_types[0]) if isinstance(publication_types, (list, tuple)) and publication_types else "journal-article"
            result.append(Paper(f"s2:{row['paperId']}", str(row.get("title") or "Untitled"), str(ids.get("DOI") or ""), row.get("year"), tuple(str(a.get("name")) for a in row.get("authors", []) if isinstance(a, Mapping) and a.get("name")), self.name, str(row.get("abstract") or ""), publication_type=publication_type))
        self._mark_results(len(result))
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
                        publication_type=str(row.get("type") or "journal-article"),
                    )
                )
        self._mark_results(len(result))
        return tuple(result)


class PubChemAdapter(_Adapter):
    name = "PubChem"

    def __init__(self, *, transport: Any | None = None, settings: ProviderSettings | None = None):
        super().__init__(settings=settings or ProviderSettings.from_env(self.name, "https://pubchem.ncbi.nlm.nih.gov/rest/pug"), transport=transport)

    def expand(self, term: str) -> tuple[str, ...]:
        payload = self._json(self._request("GET", self.settings.endpoint.rstrip("/") + "/compound/name/" + quote(term, safe="") + "/synonyms/JSON"))
        values = (payload.get("InformationList") or {}).get("Information", [])
        result = tuple(str(value) for row in values if isinstance(row, Mapping) for value in row.get("Synonym", []) if str(value).strip())
        self._mark_results(len(result))
        return result


class ChebiAdapter(_Adapter):
    name = "ChEBI"

    def __init__(self, *, transport: Any | None = None, settings: ProviderSettings | None = None):
        super().__init__(settings=settings or ProviderSettings.from_env(self.name, "https://www.ebi.ac.uk/chebi/backend/api/public/es_search/"), transport=transport)

    def expand(self, term: str) -> tuple[str, ...]:
        payload = self._json(self._request("GET", self.settings.endpoint + "?" + urlencode({"term": term})))
        values = payload.get("results", payload.get("data", []))
        result = tuple(str(row.get("name") or row.get("chebiId")) for row in values if isinstance(row, Mapping) and (row.get("name") or row.get("chebiId")))
        self._mark_results(len(result))
        return result


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
            if not isinstance(row, Mapping):
                continue
            url = row.get("url_for_pdf") or row.get("url_for_landing_page")
            if url:
                direct = bool(row.get("url_for_pdf"))
                note = "" if direct else "legal OA landing page; direct PDF resolution may require a later route"
                locations.append(FullTextLocation("doi:" + doi.lower(), str(url), "OPEN_ACCESS", self.name, direct, note))
        result = tuple(dict.fromkeys(locations))
        self._mark_results(len(result))
        return result


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
        self._mark_results(len(result))
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
        self._mark_results(len(result))
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
            command = shlex.split(self.command)
            try:
                with tempfile.TemporaryDirectory(prefix="chemical-review-mineru-") as output_dir:
                    input_command = list(command)
                    if "--input-dir" not in input_command:
                        input_command.extend(("--input-dir", str(pdf.parent)))
                    if "--output-dir" not in input_command:
                        input_command.extend(("--output-dir", output_dir))
                    completed = subprocess.run(input_command, check=False, capture_output=True, text=True, timeout=180)
                    # Batch parsers commonly print progress logs to stdout;
                    # structured Markdown is authoritative when it exists.
                    structured = self._markdown_output(Path(output_dir), pdf)
                    stdout = completed.stdout.strip()
                    output = structured or (stdout if not _looks_like_mineru_progress(stdout) else "")
                    if completed.returncode == 0 and output:
                        sections = tuple(part.strip() for part in output.replace("\r\n", "\n").split("\f") if part.strip())
                        return sections, tuple(f"{pdf.name}#page={i}" for i in range(1, len(sections) + 1)), "MinerU command"

                    # Keep compatibility with a small local wrapper that
                    # accepts one PDF path, while making the canonical batch
                    # contract (`--input-dir`) the first attempt.
                    legacy_command = list(command) + [str(pdf)]
                    legacy = subprocess.run(legacy_command, check=False, capture_output=True, text=True, timeout=180)
                    legacy_stdout = legacy.stdout.strip()
                    legacy_output = self._markdown_output(Path(output_dir), pdf) or (legacy_stdout if not _looks_like_mineru_progress(legacy_stdout) else "")
                    if legacy.returncode != 0 or not legacy_output:
                        raise ProviderUnavailable("MinerU command failed; inspect parser degradation")
                    sections = tuple(part.strip() for part in legacy_output.replace("\r\n", "\n").split("\f") if part.strip())
                    return sections, tuple(f"{pdf.name}#page={i}" for i in range(1, len(sections) + 1)), "MinerU command"
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ProviderUnavailable("MinerU command failed; inspect parser degradation") from exc
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

    @staticmethod
    def _markdown_output(output_dir: Path, pdf: Path) -> str:
        candidates = sorted((output_dir / "markdown").glob("*.md")) if (output_dir / "markdown").is_dir() else []
        if not candidates:
            candidates = sorted(output_dir.rglob("*.md")) if output_dir.is_dir() else []
        preferred = [path for path in candidates if path.stem.lower() == pdf.stem.lower() or _compact(path.stem) == _compact(pdf.stem)]
        target = preferred[:1] if preferred else (candidates[:1] if len(candidates) == 1 else [])
        if not target:
            return ""
        try:
            return target[0].read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            return ""


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
        self._discovery_stats: dict[str, Any] = {"raw_hits": 0, "provider_query_coverage": {}, "provider_provenance": {}}
        self._candidate_records: list[dict[str, Any]] = []
        self._screened_papers: list[Paper] = []

    def run(
        self,
        *,
        fixture_dir: str | Path | None = None,
        adapters: Sequence[Any] | None = None,
        entity_adapters: Sequence[Any] | None = None,
        full_text_adapters: Sequence[Any] | None = None,
        download_transport: Any | None = None,
        config_choice: str | None = None,
    ) -> ResearchResult:
        brief = self._confirmed_brief()
        self._ensure_dirs()
        if fixture_dir is None and adapters is None and entity_adapters is None and full_text_adapters is None:
            self._configuration_preflight(config_choice)
        fixture = self._load_fixture(fixture_dir)
        if adapters is None:
            adapters = _configured_discovery_adapters()
        if entity_adapters is None:
            entity_adapters = _configured_entity_adapters()
        if full_text_adapters is None:
            full_text_adapters = _configured_full_text_adapters()
        terms, entity_failures = self._expand_entities(brief, entity_adapters)
        discovered = self._discover(brief, fixture, adapters, terms=terms)
        papers, candidate_records = self._screen_candidates(brief, discovered)
        papers = self._locate_full_text(papers, full_text_adapters)
        for paper in papers:
            for row in candidate_records:
                if row.get("identifier") == paper.identifier:
                    row.update({"provider": paper.provider, "full_text_url": _persisted_url(paper.full_text_url), "full_text_url_status": _url_status(paper.full_text_url), "access_basis": paper.access_basis, "full_text_direct": paper.full_text_direct})
        candidate_by_id = {row["identifier"]: row for row in candidate_records}
        existing_manifest = self._load_manifest()
        current_ids = set(candidate_by_id)
        current_candidate_digest = _candidate_digest(candidate_records)
        if existing_manifest and int(existing_manifest.get("brief_revision", -1)) == _brief_revision(brief) and existing_manifest.get("candidate_digest") == current_candidate_digest:
            records = {
                str(source.get("identifier")): dict(source)
                for source in existing_manifest.get("sources", ())
                if isinstance(source, Mapping) and str(source.get("identifier", "")) in current_ids
            }
        else:
            records = {}
        for paper in papers:
            previous = records.get(paper.identifier, {})
            paper_values = asdict(paper)
            paper_values["full_text_url"] = _persisted_url(paper.full_text_url)
            records[paper.identifier] = {**previous, **paper_values, "source_id": _source_id(paper.identifier), "full_text_url_status": _url_status(paper.full_text_url), "local_path": previous.get("local_path", ""), "digest": previous.get("digest", ""), "parser": previous.get("parser", ""), "parser_attempted": previous.get("parser_attempted", False), "locators": previous.get("locators", []), "full_text": previous.get("full_text", "UNKNOWN"), "failure": previous.get("failure", ""), "screening": candidate_by_id.get(paper.identifier, {}).get("screening", {})}
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
                    record["parser_attempted"] = True
                    parsed = self._parse(inbox_pdf, paper.identifier, parsed_fixture.get(paper.identifier))
                    record.update({"parser": parsed[2], "locators": list(parsed[1]), "full_text": "FOUND", "failure": parsed[3], "failure_kind": _parser_failure_kind(parsed[2], parsed[3]), "evidence_fields": self._extract_evidence_fields(brief, parsed[0], parsed[1])})
                    self._append_evidence(paper, parsed[0], parsed[1], parsed[2], parsed[3])
                    parsed_count += 1
                    if str(parsed[2]).lower() == "pdftotext":
                        research_gap = True
                except ProviderUnavailable as exc:
                    research_gap = True
                    record.update({"full_text": "FOUND", "parser": "UNPARSED", "failure": _safe_error(str(exc)), "failure_kind": _parser_failure_kind("UNPARSED", str(exc))})
            elif safe_full_text_url and paper.full_text_direct and paper.access_basis == "OPEN_ACCESS":
                target = self.root / "fulltext" / (_source_id(paper.identifier) + ".pdf")
                try:
                    self._download(safe_full_text_url, target, transport=download_transport)
                    record.update({"local_path": str(target), "digest": _digest(target), "full_text": "FOUND", "access_basis": "OPEN_ACCESS", "downloaded_at": _now()})
                    record["parser_attempted"] = True
                    parsed = self._parse(target, paper.identifier, parsed_fixture.get(paper.identifier))
                    record.update({"parser": parsed[2], "locators": list(parsed[1]), "failure": parsed[3], "failure_kind": _parser_failure_kind(parsed[2], parsed[3]), "evidence_fields": self._extract_evidence_fields(brief, parsed[0], parsed[1])})
                    self._append_evidence(paper, parsed[0], parsed[1], parsed[2], parsed[3])
                    parsed_count += 1
                    if str(parsed[2]).lower() == "pdftotext":
                        research_gap = True
                except ProviderUnavailable as exc:
                    failure = _safe_error(str(exc))
                    research_gap = True
                    record.update({"full_text": "WAITING_FOR_USER", "failure": failure, "failure_kind": "DOWNLOAD_FAILURE"})
                    if paper.full_text_url:
                        pending_requests.append(self._download_request(paper, record, reason=failure))
                    else:
                        research_gap = True
            else:
                failure = "legal user download required" if paper.full_text_url else "no legal full-text URL was located"
                record.update({"full_text": "WAITING_FOR_USER" if paper.full_text_url else "MISSING", "failure": failure, "failure_kind": "FULL_TEXT_GAP"})
                if paper.full_text_url:
                    pending_requests.append(self._download_request(paper, record, reason=failure))
                else:
                    research_gap = True
        pending_requests.sort(key=lambda item: (-int(item["priority_score"]), item["source_id"]))
        requests = [{key: value for key, value in request.items() if key != "priority_score"} for request in pending_requests]
        self._write_records(records)
        manifest = self._write_manifest(brief, candidate_records, records, requests, terms, entity_failures, research_gap)
        self._write_supporting_assets(brief, papers, records, requests, terms, entity_failures, manifest=manifest)
        self._write_provider_status((*adapters, *entity_adapters), full_text_adapters or ())
        coverage = manifest["coverage"]
        if not papers:
            status, next_action = "RESEARCH_GAP", "No sufficiently relevant candidates survived screening; refine the confirmed brief or expand verified discovery coverage."
        elif requests:
            status, next_action = "WAITING_FOR_USER", "Complete the finite download queue in download-requests.md, then rerun Research."
        elif coverage["evidence_ready"] and not research_gap:
            status, next_action = "READY_FOR_SYNTHESIS", "Synthesis may read research-handoff.md and evidence-notes.md; original PDFs remain authoritative."
        else:
            status, next_action = "RESEARCH_GAP", "Add a verified source, configure a provider, or narrow the confirmed scope; no source fact was invented."
        handoff = self.root / "research-handoff.md"
        manifest["result"] = status
        manifest["next_action"] = next_action
        self._write_manifest_file(manifest)
        handoff.write_text(self._handoff(status, next_action, papers, records, requests, manifest=manifest), encoding="utf-8")
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
        # These are generated projections owned by Research. Remove only the
        # stale binding notice; authorized PDFs and user-authored files remain
        # untouched and are re-evaluated during this run.
        binding_requests = self.root / "binding-requests.md"
        if binding_requests.is_file() and not binding_requests.is_symlink():
            binding_requests.unlink()

    def _configuration_preflight(self, choice: str | None) -> None:
        discovery = _configured_discovery_adapters()
        parser = MinerUParser()
        rows = self._configuration_rows(discovery_adapters=discovery, parser=parser, probe_optional=True)
        missing = [row for row in rows if row.get("required") == "true" and row["status"] not in {"READY", "USABLE_RESULTS"}]
        report_path = self.root / "configuration-preflight.md"
        previous = ""
        if report_path.is_file():
            match = re.search(r"^Decision:\s*(\S+)", report_path.read_text(encoding="utf-8"), re.M)
            previous = match.group(1) if match else ""
        if choice is not None and choice not in CONFIGURATION_CHOICES:
            raise ValueError(f"unknown configuration choice: {choice}")
        if not missing:
            decision = "CONFIGURED_CONTINUE"
        elif choice == "pause":
            decision = "PAUSED"
        elif choice == "accept_degraded" or (choice is None and previous == "ACCEPT_DEGRADED"):
            decision = "ACCEPT_DEGRADED" if not missing else "PENDING"
        elif choice == "configure_and_continue":
            decision = "PENDING"
        else:
            decision = "PENDING"
        self._write_configuration_preflight(report_path, decision, rows)
        if decision == "PAUSED":
            raise ResearchPaused(f"Research configuration preflight paused; review {report_path}")
        if decision == "PENDING":
            raise ConfigurationChoiceRequired(
                f"Research configuration choice required; review {report_path} and choose one of: {', '.join(CONFIGURATION_CHOICES)}"
            )

    def _configuration_rows(self, *, discovery_adapters: Sequence[Any] | None = None, parser: MinerUParser | None = None, probe_optional: bool = False) -> list[dict[str, str]]:
        network = _env_enabled("CHEMICAL_REVIEW_ENABLE_NETWORK")
        discovery_adapters = tuple(discovery_adapters) if discovery_adapters is not None else _configured_discovery_adapters()
        if network and discovery_adapters:
            discovery_status, _discovery_note = self._probe_discovery(discovery_adapters)
        else:
            discovery_status = "MISSING"
        mineru_status, mineru_note = self._mineru_probe(parser or MinerUParser())
        optional = self._probe_optional_capabilities() if network and probe_optional else {}
        return [
            {
                "capability": "Metadata discovery (OpenAlex / Semantic Scholar / Crossref)",
                "status": discovery_status,
                "required": "true",
                "impact": "Without a reachable provider returning usable metadata, Research cannot discover candidates.",
                "recovery": "Set CHEMICAL_REVIEW_ENABLE_NETWORK=true; provider credentials remain optional or provider-specific.",
            },
            {
                "capability": "Chemistry term expansion (PubChem / ChEBI)",
                "status": optional.get("PubChem / ChEBI", "CONFIGURED" if network else "OPTIONAL_MISSING"),
                "required": "false",
                "impact": "Without the network route, synonym and entity expansion is unavailable.",
                "recovery": "Enable the network route or accept a narrower, manually supplied vocabulary.",
            },
            {
                "capability": "Legal full-text location (Europe PMC)",
                "status": optional.get("Europe PMC", "CONFIGURED" if network else "OPTIONAL_MISSING"),
                "required": "false",
                "impact": "Without the route, Research cannot automatically locate open full text.",
                "recovery": "Enable the network route or use legal user downloads recorded in download-requests.md.",
            },
            {
                "capability": "Additional open-access full text (Unpaywall)",
                "status": optional.get("Unpaywall", "CONFIGURED" if network and os.environ.get("UNPAYWALL_EMAIL", "").strip() else "OPTIONAL_MISSING"),
                "required": "false",
                "impact": "Without UNPAYWALL_EMAIL, Unpaywall lookup is skipped.",
                "recovery": "Set UNPAYWALL_EMAIL in an untracked env file, or accept reduced full-text coverage.",
            },
            {
                "capability": "Additional repository full text (CORE)",
                "status": optional.get("CORE", "CONFIGURED" if network and os.environ.get("CORE_API_KEY", "").strip() else "OPTIONAL_MISSING"),
                "required": "false",
                "impact": "Without CORE_API_KEY, CORE lookup is skipped.",
                "recovery": "Set CORE_API_KEY in an untracked env file, or accept reduced full-text coverage.",
            },
            {
                "capability": "Primary PDF parser (MinerU)",
                "status": mineru_status,
                "required": "true",
                "impact": mineru_note,
                "recovery": "Set MINERU_COMMAND or MINERU_ENDPOINT, place an authorized PDF in research/inbox/authorized-pdfs/, and rerun the preflight (MINERU_TOKEN only in an untracked env file).",
            },
        ]

    def _probe_optional_capabilities(self) -> dict[str, str]:
        """Make real bounded calls for optional routes during the preflight."""
        results: dict[str, str] = {}

        def probe(name: str, callback: Any) -> None:
            try:
                value = callback()
                results[name] = "USABLE_RESULTS" if value else "REACHABLE"
            except Exception:
                results[name] = "FAILED"

        entities = _configured_entity_adapters()
        if entities:
            entity_results = []
            for adapter in entities:
                try:
                    entity_results.append(bool(adapter.expand("water")))
                except Exception:
                    entity_results.append(False)
            results["PubChem / ChEBI"] = "USABLE_RESULTS" if any(entity_results) else "FAILED"
        else:
            results["PubChem / ChEBI"] = "OPTIONAL_MISSING"
        full_text = _configured_full_text_adapters()
        europe = next((adapter for adapter in full_text if getattr(adapter, "name", "") == "Europe PMC"), None)
        probe("Europe PMC", lambda: europe.locate("10.1038/s41586-023-06747-5") if europe else ())
        unpaywall = next((adapter for adapter in full_text if getattr(adapter, "name", "") == "Unpaywall"), None)
        if unpaywall:
            probe("Unpaywall", lambda: unpaywall.locate("10.1038/s41586-023-06747-5"))
        else:
            results["Unpaywall"] = "OPTIONAL_MISSING"
        core = next((adapter for adapter in full_text if getattr(adapter, "name", "") == "CORE"), None)
        if core:
            probe("CORE", lambda: core.locate("10.1038/s41586-023-06747-5"))
        else:
            results["CORE"] = "OPTIONAL_MISSING"
        return results

    def _probe_discovery(self, adapters: Sequence[Any]) -> tuple[str, str]:
        reachable = 0
        usable = 0
        errors: list[str] = []
        for adapter in adapters:
            try:
                values = tuple(adapter.search("chemical literature", limit=1))
                reachable += 1
                usable += bool(values)
            except Exception as exc:
                errors.append(f"{getattr(adapter, 'name', adapter.__class__.__name__)}: {_safe_error(str(exc))}")
        if usable:
            return "USABLE_RESULTS", "At least one configured metadata provider returned a usable result."
        if reachable:
            return "REACHABLE", "Configured metadata providers responded but returned no usable result for the probe."
        return "MISSING", "No metadata provider was reachable: " + ("; ".join(errors) or "no route")

    def _mineru_probe(self, parser: MinerUParser | None = None) -> tuple[str, str]:
        parser = parser or MinerUParser()
        if not parser.configured:
            return "MISSING", "Without MinerU, authorized PDFs use the explicitly marked pdftotext low-fidelity fallback."
        candidates = sorted((self.inbox.glob("*.pdf"))) + sorted((self.root / "fulltext").glob("*.pdf"))
        candidates = [path for path in candidates if path.is_file()]
        if not candidates:
            return "NOT_VERIFIED", "MinerU is configured but no authorized PDF is available for a real parse probe; readiness is not claimed."
        probe = candidates[0]
        try:
            result = parser.parse(probe, "configuration-preflight")
            if not isinstance(result, tuple) or len(result) != 3 or not result[0] or not result[1]:
                raise ProviderUnavailable("MinerU real PDF parse probe returned no structured sections/locators")
        except Exception as exc:
            return "FAILED", f"MinerU is configured but the real PDF parse probe failed: {_safe_error(str(exc))}"
        return "READY", f"MinerU real PDF parse probe passed for {probe.name}."

    @staticmethod
    def _write_configuration_preflight(path: Path, decision: str, rows: Sequence[Mapping[str, str]]) -> None:
        lines = [
            "# Research Configuration Preflight", "", f"Decision: {decision}", "",
            "No credential value is recorded here. Research will not start with missing configuration until a user chooses an explicit route.", "",
            "## Capability check", "", "| Capability | Status | Impact | Recovery |", "| --- | --- | --- | --- |",
        ]
        for row in rows:
            lines.append("| " + " | ".join(str(row[key]).replace("|", "\\|") for key in ("capability", "status", "impact", "recovery")) + " |")
        lines.extend([
            "", "## Choices", "",
            "- `configure_and_continue`: configure all missing recommended capabilities, then rerun Research.",
            "- `accept_degraded`: continue with the documented degradation and preserve its impact in provider-status.md.",
            "- `pause`: stop before discovery, full-text location, parsing, and evidence generation.", "",
        ])
        path.write_text("\n".join(lines), encoding="utf-8")

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
            papers = [_paper_from_mapping(row) for row in fixture["papers"] if isinstance(row, Mapping)]
            self._discovery_stats = {
                "raw_hits": len(papers),
                "provider_query_coverage": {str(getattr(paper, "provider", "fixture")): ["fixture"] for paper in papers},
                "provider_provenance": {
                    (paper.doi.lower() if paper.doi else paper.identifier.lower()): [paper.provider or "fixture"]
                    for paper in papers
                },
            }
            return papers
        core_claims = _core_claims(brief)
        query_terms = list(_brief_search_terms(brief))
        for term in terms:
            normalized = " ".join(str(term).split()).strip()
            if normalized and len(normalized) <= 80 and normalized.lower() not in {item.lower() for item in query_terms}:
                query_terms.append(normalized)
        query_base = " ".join(query_terms[:6]).strip() or "chemical literature"
        if adapters is None:
            adapters = _configured_discovery_adapters()
        found: list[Paper] = []
        raw_hits = 0
        coverage: dict[str, list[str]] = {}
        provenance: dict[str, set[str]] = {}
        for adapter in adapters:
            for path in SEARCH_PATHS:
                coverage.setdefault(getattr(adapter, "name", adapter.__class__.__name__), []).append(path)
                try:
                    query = f"{query_base} {path}"[:220]
                    for paper in adapter.search(query, limit=5):
                        raw_hits += 1
                        provenance.setdefault(paper.doi.lower() if paper.doi else paper.identifier.lower(), set()).add(getattr(adapter, "name", adapter.__class__.__name__))
                        if not paper.claim_relevance:
                            paper = replace(paper, claim_relevance=_candidate_claim_relevance(core_claims, path))
                        paper = replace(paper, query_family=path)
                        found.append(paper)
                except Exception:
                    continue
        self._discovery_stats = {"raw_hits": raw_hits, "provider_query_coverage": coverage, "provider_provenance": {key: sorted(values) for key, values in provenance.items()}}
        return found

    def _screen_candidates(self, brief: str, papers: Sequence[Paper]) -> tuple[list[Paper], list[dict[str, Any]]]:
        """Normalize versions and apply deterministic metadata screening before routing."""
        unique: dict[str, Paper] = {}
        provenance: dict[str, set[str]] = {}
        doi_index: dict[str, str] = {}
        title_index: dict[str, str] = {}
        for paper in papers:
            paper = replace(paper, access_basis=_legal_access_basis(paper.access_basis))
            doi_key = paper.doi.strip().lower().removeprefix("https://doi.org/")
            title_key = _title_candidate_key(paper)
            key = doi_index.get(doi_key) if doi_key else None
            key = key or title_index.get(title_key)
            if not key:
                key = _candidate_key(paper)
            if doi_key:
                doi_index[doi_key] = key
            title_index[title_key] = key
            provenance.setdefault(key, set()).add(paper.provider or "unknown")
            current = unique.get(key)
            if current is None or _screen_quality(paper) > _screen_quality(current):
                unique[key] = paper
        rows: list[dict[str, Any]] = []
        relevant: list[Paper] = []
        for key, paper in sorted(unique.items(), key=lambda item: (_source_id(item[1].identifier), item[1].title.lower())):
            decision, role, reason, review_relevant = _screen_paper(brief, paper)
            screening_fields = _screening_fields(brief, paper)
            row = {
                "candidate_id": _source_id(paper.identifier),
                "identifier": paper.identifier,
                "doi": paper.doi,
                "title": paper.title,
                "year": paper.year,
                "provider": paper.provider,
                "abstract": paper.abstract,
                "version": paper.version,
                "query_family": paper.query_family,
                "full_text_url": _persisted_url(paper.full_text_url),
                "full_text_url_status": _url_status(paper.full_text_url),
                "access_basis": paper.access_basis,
                "full_text_direct": paper.full_text_direct,
                "priority": paper.priority,
                "claim_relevance": paper.claim_relevance,
                "non_substitutability": paper.non_substitutability,
                "publication_type": paper.publication_type,
                "providers": sorted(provenance.get(key, set())),
                "screening": {**screening_fields, "decision": decision, "reason": reason, "review_relevant": review_relevant, "evidence_role": role, "confidence": "HIGH" if decision != "MAYBE" else "MEDIUM"},
                "source_id": _source_id(paper.identifier),
            }
            rows.append(row)
            if decision == "INCLUDE" or (decision == "MAYBE" and review_relevant):
                relevant.append(replace(paper, priority=paper.priority or ("CORE" if role == "primary" else "NORMAL")))
        self._candidate_records = rows
        self._screened_papers = relevant
        self._discovery_stats["unique_candidates"] = len(rows)
        self._discovery_stats["screened_relevant"] = len(relevant)
        return relevant, rows

    @staticmethod
    def _expand_entities(brief: str, adapters: Sequence[Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
        terms = set(_brief_search_terms(brief))
        failures: list[str] = []
        for term in _entity_search_terms(brief)[:6]:
            for adapter in adapters:
                try:
                    terms.update(str(value).strip() for value in adapter.expand(term) if str(value).strip())
                except Exception as exc:
                    credentials = adapter._credential_values() if hasattr(adapter, "_credential_values") else ()
                    failures.append(f"{getattr(adapter, 'name', adapter.__class__.__name__)} ({term}): {_safe_error(str(exc), secrets=credentials)}")
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
                except Exception:
                    continue
                if locations:
                    location = locations[0]
                    located.append(replace(paper, full_text_url=location.url, full_text_direct=location.direct_pdf, access_basis=_legal_access_basis(location.access_basis), provider=f"{paper.provider}+{getattr(adapter, 'name', 'full-text')}"))
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
                    if key in {"evidence_fields", "screening"}:
                        try:
                            parsed = json.loads(value)
                            values[key] = parsed if isinstance(parsed, dict) else {}
                        except json.JSONDecodeError:
                            values[key] = {}
                    else:
                        values[key] = value
            if values.get("identifier"):
                values["locators"] = [v for v in values.get("locators", "").split(";") if v]
                result[values["identifier"]] = values
        return result

    def _load_manifest(self) -> dict[str, Any]:
        path = self.root / "manifest.json"
        if not path.is_file():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _write_manifest(
        self,
        brief: str,
        candidates: Sequence[Mapping[str, Any]],
        records: Mapping[str, Mapping[str, Any]],
        requests: Sequence[Mapping[str, Any]],
        terms: Sequence[str],
        entity_failures: Sequence[str],
        research_gap: bool,
    ) -> dict[str, Any]:
        brief_revision = _brief_revision(brief)
        source_ids = sorted(str(record.get("source_id") or _source_id(str(record.get("identifier", "")))) for record in records.values())
        run_seed = f"{brief_revision}|{'|'.join(source_ids)}|{self._discovery_stats.get('raw_hits', 0)}"
        unresolved_sources = [record for record in records.values() if record.get("full_text") in {"MISSING", "WAITING_FOR_USER"} or record.get("parser") == "UNPARSED"]
        manifest = {
            "schema": 1,
            "run_id": hashlib.sha256(run_seed.encode()).hexdigest()[:16],
            "brief_revision": brief_revision,
            "brief_digest": hashlib.sha256(brief.encode()).hexdigest(),
            "candidate_digest": _candidate_digest(candidates),
            "generated_at": _now(),
            "candidates": [dict(row) for row in candidates],
            "sources": [self._manifest_source(record) for record in records.values()],
            "evidence_matrix": self._evidence_matrix(brief, records),
            "gaps": [
                {"source_id": str(request.get("source_id", "")), "kind": "FULL_TEXT_REQUIRED", "reason": str(request.get("failure", "manual action required")), "claim": str(request.get("claim_relevance", ""))}
                for request in requests
            ] + [
                {"source_id": str(record.get("source_id", "")), "kind": "RESEARCH_GAP", "reason": str(record.get("failure", "unresolved full-text or parser gap")), "claim": str(record.get("claim_relevance", ""))}
                for record in unresolved_sources if str(record.get("source_id", "")) not in {str(request.get("source_id", "")) for request in requests}
            ] + ([{"kind": "ENTITY_PROVIDER_DEGRADED", "reason": failure} for failure in entity_failures] if entity_failures else []),
            "coverage": self._coverage(candidates, records, requests, research_gap),
            "download_requests": [dict(request) for request in requests],
            "provider_query_coverage": self._discovery_stats.get("provider_query_coverage", {}),
            "provider_provenance": self._discovery_stats.get("provider_provenance", {}),
            "terms": list(terms),
        }
        self._write_manifest_file(manifest)
        return manifest

    def _write_manifest_file(self, manifest: Mapping[str, Any]) -> None:
        path = self.root / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        safe_manifest = dict(manifest)
        safe_manifest["candidates"] = []
        for row in manifest.get("candidates", ()):
            if not isinstance(row, Mapping):
                continue
            candidate = dict(row)
            if "full_text_url" in candidate:
                candidate["full_text_url"] = _persisted_url(str(candidate.get("full_text_url", "")))
            safe_manifest["candidates"].append(candidate)
        safe_manifest["sources"] = [
            self._manifest_source(source)
            for source in manifest.get("sources", ())
            if isinstance(source, Mapping)
        ]
        safe_manifest["download_requests"] = []
        for request in manifest.get("download_requests", ()):
            if not isinstance(request, Mapping):
                continue
            safe_request = dict(request)
            safe_request["url"] = _persisted_url(str(safe_request.get("url", "")))
            safe_manifest["download_requests"].append(safe_request)
        path.write_text(json.dumps(safe_manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

    @staticmethod
    def _manifest_source(record: Mapping[str, Any]) -> dict[str, Any]:
        source = dict(record)
        if "full_text_url" in source:
            source["full_text_url"] = _persisted_url(str(source.get("full_text_url", "")))
        for key in ("local_path",):
            if key in source and source[key]:
                source[key] = str(source[key])
        source["evidence_fields"] = dict(source.get("evidence_fields") or {})
        return source

    def _coverage(self, candidates: Sequence[Mapping[str, Any]], records: Mapping[str, Mapping[str, Any]], requests: Sequence[Mapping[str, Any]], research_gap: bool) -> dict[str, Any]:
        decisions = [row.get("screening", {}).get("decision") for row in candidates]
        relevant = [row for row in candidates if row.get("screening", {}).get("decision") == "INCLUDE" or (row.get("screening", {}).get("decision") == "MAYBE" and row.get("screening", {}).get("review_relevant"))]
        downloaded = [record for record in records.values() if record.get("full_text") == "FOUND" and record.get("digest")]
        mineru_success = [record for record in downloaded if str(record.get("parser", "")).lower().startswith("mineru")]
        fallback = [record for record in downloaded if str(record.get("parser", "")).lower() == "pdftotext"]
        unparsed = [record for record in records.values() if record.get("parser") == "UNPARSED" or (record.get("parser_attempted") and not record.get("parser") and record.get("full_text") == "FOUND")]
        evidence_ready = [record for record in downloaded if record.get("evidence_fields") and record.get("parser") and str(record.get("parser")).lower() not in {"unparsed", "pdftotext"}]
        relevant_ids = {
            str(row.get("identifier"))
            for row in relevant
            if row.get("identifier")
        }
        relevant_pdfs = [record for record in downloaded if str(record.get("identifier")) in relevant_ids]
        return {
            "raw_hits": int(self._discovery_stats.get("raw_hits", len(candidates))),
            "unique_candidates": int(self._discovery_stats.get("unique_candidates", len(candidates))),
            "included": decisions.count("INCLUDE"), "excluded": decisions.count("EXCLUDE"), "maybe": decisions.count("MAYBE"),
            "relevant_candidates": len(relevant), "primary_evidence": sum(1 for row in candidates if row.get("screening", {}).get("evidence_role") == "primary" and row.get("screening", {}).get("decision") == "INCLUDE"),
            "relevant_pdfs": len(relevant_pdfs), "downloaded_pdfs": len(downloaded), "parser_attempts": sum(1 for record in records.values() if record.get("parser_attempted")), "manual_queue": len(requests),
            "mineru_success": len(mineru_success), "mineru_failure": sum(1 for record in records.values() if record.get("failure_kind") == "MINERU_FAILURE"),
            "fallback_pdftotext": len(fallback), "unparsed": len(unparsed), "evidence_ready": len(evidence_ready),
            "gaps": len(requests) + len([record for record in records.values() if record.get("full_text") == "MISSING" or record.get("parser") == "UNPARSED"]) + int(bool(research_gap and not requests and not any(record.get("full_text") == "MISSING" or record.get("parser") == "UNPARSED" for record in records.values()))),
        }

    def _evidence_matrix(self, brief: str, records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        fields = _review_specific_fields(brief)
        return {
            "layers": {
                "research_kernel": ["identity", "version", "provenance", "access_basis", "parser", "locators", "evidence_level"],
                "chemistry_comparison_spine": ["system", "method", "conditions", "comparator", "endpoint", "units", "replicates", "uncertainty"],
                "domain_modules": ["chemistry", "molecular-discovery"] if any(value in brief.lower() for value in ("molecule", "molecular", "分子")) else ["chemistry"],
                "review_specific_evidence_plan": fields,
            },
            "review_specific_fields": fields,
            "source_count": len(records),
            "evidence_levels": {str(record.get("source_id")): (record.get("evidence_fields") or {}).get("evidence_level", "UNKNOWN") for record in records.values()},
            "claim_vocabulary": ["SOURCE_FACT", "AUTHOR_HYPOTHESIS", "MODEL_SYNTHESIS", "MODEL_HYPOTHESIS", "UNKNOWN", "NOT_COMPARABLE", "Chemical GAP", "SOURCE_EXCERPT", "VERIFIED_SOURCE_FACT"],
        }

    @staticmethod
    def _extract_evidence_fields(brief: str, sections: Sequence[str], locators: Sequence[str]) -> dict[str, Any]:
        text = " ".join(" ".join(str(section).replace("\n", " ").split()) for section in sections)
        fields = _review_specific_fields(brief)
        values: dict[str, Any] = {field: "UNKNOWN" for field in fields}
        spine = {field: "UNKNOWN" for field in ("system", "method", "conditions", "comparator", "endpoint", "units", "replicates", "uncertainty")}
        patterns = {
            "candidate_denominator": r"(?i)(\d+)\s+(?:attempted|generated|candidate)\s+molecules?",
            "synthesis_attempt": r"(?i)(\d+)\s+(?:attempted|synthesis attempts?)",
            "identity_confirmation": r"(?i)(\d+\s+(?:confirmed|validated)[^.;]*)",
            "screening_process": r"(?i)(screen(?:ing|ed)[^.;]*)",
            "assay_endpoint": r"(?i)((?:assay|endpoint)[^.;]*)",
            "key_result": r"(?i)(?:result|yield|selectivity|accuracy)\s*[:=]?\s*([^.;]+)",
            "limitation": r"(?i)(limitation[^.;]*)",
            "generation_task": r"(?i)(generation[^.;]*)",
            "closed_loop_feedback": r"(?i)(closed[- ]loop[^.;]*)",
        }
        patterns.update({
            "system": r"(?i)(?:\b(?:chemical|reaction|catalyst|molecular)\s+system|\bsystem)\s*[:=]\s*([^.;]+)",
            "method": r"(?i)(?:\b(?:method|model|approach|strategy))\s*[:=]\s*([^.;]+)",
            "conditions": r"(?i)(?:\b(?:reaction|experimental|operating)\s+conditions|\bconditions)\s*[:=]\s*([^.;]+)",
            "comparator": r"(?i)(?:\b(?:comparator|comparison|control)|\b(?:versus|vs\.?))\s*[:=]?\s*([^.;]+)",
            "endpoint": r"(?i)(?:\b(?:assay\s+)?endpoint|\boutcome)\s*[:=]\s*([^.;]+)",
            "units": r"(?i)\bunits?\s*[:=]\s*([^.;]+)",
            "replicates": r"(?i)\b(?:replicates?|repeats?)\s*[:=]\s*([^.;]+)",
            "uncertainty": r"(?i)\b(?:uncertainty|error|standard\s+deviation|confidence\s+interval)\s*[:=]\s*([^.;]+)",
        })
        for field, pattern in patterns.items():
            if field in values or field in spine:
                match = re.search(pattern, text)
                if match:
                    (values if field in values else spine)[field] = " ".join(match.group(1).split())[:500]
        for field in ("comparator", "endpoint"):
            if spine[field] == "UNKNOWN" and values.get(field, "UNKNOWN") != "UNKNOWN":
                spine[field] = values[field]
        values.update({"evidence_level": "EXCERPT", "evidence_label": "SOURCE_EXCERPT", "locators": ";".join(str(locator) for locator in locators) or "UNKNOWN", "excerpts": [{"locator": str(locators[index] if index < len(locators) else f"page={index + 1}"), "text": " ".join(str(section).split())[:500]} for index, section in enumerate(sections)], "study_object": text[:500] or "UNKNOWN", "model_or_method": spine["method"], "data_or_training_source": "UNKNOWN", "synthesis_or_assay_evidence": values.get("identity_confirmation", "UNKNOWN"), "comparator": spine["comparator"], "endpoint": spine["endpoint"] if spine["endpoint"] != "UNKNOWN" else values.get("assay_endpoint", "UNKNOWN"), "key_result": values.get("key_result", "UNKNOWN"), "limitation": values.get("limitation", "UNKNOWN")})
        return {**spine, **values}

    def promote_evidence(self, identifier: str, *, fields: Mapping[str, str] | None = None, locators: Sequence[str] = (), verifier: str = "human") -> dict[str, Any]:
        """Explicitly promote parser excerpts after original-PDF verification."""
        if not str(verifier).strip() or not locators:
            raise ValueError("promotion requires a verifier and at least one original-PDF locator")
        manifest = self._load_manifest()
        for source in manifest.get("sources", []):
            if source.get("identifier") != identifier and source.get("doi") != identifier.removeprefix("doi:"):
                continue
            self._validate_promotion_source(source, locators)
            evidence = dict(source.get("evidence_fields") or {})
            evidence.update({str(key): str(value) for key, value in (fields or {}).items()})
            evidence.update({"evidence_level": "VERIFIED", "evidence_label": "VERIFIED_SOURCE_FACT", "verified_by": str(verifier), "locators": ";".join(str(item) for item in locators)})
            source["evidence_fields"] = evidence
            source["locators"] = list(locators)
            manifest.setdefault("evidence_matrix", {}).setdefault("evidence_levels", {})[str(source.get("source_id"))] = "VERIFIED"
            # The manifest is the authority; projections must never be read
            # back as a second source of truth during promotion.
            records = {
                str(item.get("identifier")): dict(item)
                for item in manifest.get("sources", ())
                if isinstance(item, Mapping) and item.get("identifier")
            }
            records[str(source.get("identifier"))] = source
            previous_coverage = dict(manifest.get("coverage") or {})
            self._discovery_stats.update({
                "raw_hits": previous_coverage.get("raw_hits", len(manifest.get("candidates", ()))),
                "unique_candidates": previous_coverage.get("unique_candidates", len(manifest.get("candidates", ()))),
            })
            manifest["coverage"] = self._coverage(manifest.get("candidates", ()), records, manifest.get("download_requests", ()), False)
            self._write_manifest_file(manifest)
            self._write_records(records)
            self._write_evidence_notes_from_manifest(manifest)
            self._write_evidence_matrix_projection(manifest, records)
            self._write_comparability_projection(records)
            handoff = self.root / "research-handoff.md"
            handoff.write_text(
                self._handoff(
                    str(manifest.get("result", "RESEARCH_GAP")),
                    str(manifest.get("next_action", "Re-evaluate Research after evidence promotion.")),
                    tuple(records.values()),
                    records,
                    manifest.get("download_requests", ()),
                    manifest=manifest,
                ),
                encoding="utf-8",
            )
            return source
        raise KeyError(f"source not found in current manifest: {identifier}")

    def _validate_promotion_source(self, source: Mapping[str, Any], locators: Sequence[str]) -> None:
        raw_path = str(source.get("local_path") or "").strip()
        if not raw_path:
            raise ValueError("promotion requires a manifest-bound original PDF path")
        pdf = Path(raw_path)
        if not pdf.is_absolute():
            pdf = (self.project_root / pdf).resolve()
        else:
            pdf = pdf.resolve()
        if not pdf.is_file() or pdf.is_symlink() or pdf.suffix.lower() != ".pdf":
            raise ValueError("promotion requires an existing regular original PDF")
        recorded_digest = str(source.get("digest") or "").strip()
        if not recorded_digest or recorded_digest != _digest(pdf):
            raise ValueError("promotion requires the current PDF digest to match the manifest")
        expected_name = _compact(pdf.name)
        for locator in locators:
            locator_name = str(locator).split("#", 1)[0].strip()
            if not locator_name or _compact(Path(locator_name).name) != expected_name or "#page=" not in str(locator):
                raise ValueError("every promotion locator must identify the manifest-bound PDF and a page")

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
            "| Capability | Provider | Configured | Reachability/result evidence | Failure/degradation | Recovery |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for capability, provider, recovery in rows:
            configured_here = provider in configured or (provider == "MinerU" and MinerUParser().configured)
            adapter = next((item for item in (*discovery, *full_text) if getattr(item, "name", "") == provider), None)
            raw_failure = getattr(adapter, "last_error", "") if adapter is not None else ""
            credentials = adapter._credential_values() if adapter is not None and hasattr(adapter, "_credential_values") else ()
            failure = _safe_error(str(raw_failure), secrets=credentials) if raw_failure else ""
            action = "Retry the configured route; no credential value is persisted." if failure else recovery
            state = getattr(adapter, "last_status", "CONFIGURED" if configured_here else "MISSING") if adapter is not None else ("CONFIGURED" if configured_here else "MISSING")
            if adapter is not None and getattr(adapter, "last_result_count", 0) == 0 and state == "CONFIGURED":
                state = "REACHABLE" if getattr(adapter, "calls", 0) else state
            lines.append(f"| {capability} | {provider} | {'YES' if configured_here else 'NO'} | {state} | {failure or 'none recorded'} | {action} |")
        (self.root / "provider-status.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_records(self, records: Mapping[str, Mapping[str, Any]]) -> None:
        active_paths: set[Path] = set()
        for paper_id, record in records.items():
            path = self.root / "source-records" / (str(record.get("source_id") or _source_id(paper_id)) + ".md")
            active_paths.add(path.resolve())
            values = dict(record)
            lines = ["---", "kind: research-source", "schema: 2", "---", "", f"# {values.get('title', paper_id)}", ""]
            for key in ("source_id", "identifier", "doi", "title", "year", "provider", "publication_type", "version", "full_text_url", "full_text_url_status", "access_basis", "priority", "claim_relevance", "non_substitutability", "local_path", "digest", "downloaded_at", "full_text", "parser", "failure", "failure_kind"):
                value = _persisted_url(str(values.get(key, ""))) if key == "full_text_url" else values.get(key, "")
                lines.append(f"{key}: {value}")
            lines.append("locators: " + ";".join(values.get("locators", [])))
            lines.append("evidence_fields: " + json.dumps(values.get("evidence_fields", {}), ensure_ascii=False, sort_keys=True))
            lines.append("screening: " + json.dumps(values.get("screening", {}), ensure_ascii=False, sort_keys=True))
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        records_dir = self.root / "source-records"
        for path in records_dir.glob("*.md"):
            if path.resolve() not in active_paths and path.is_file() and not path.is_symlink():
                path.unlink()
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
            "access_basis": _legal_access_basis(paper.access_basis),
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
        """Compatibility hook; evidence-notes is projected from manifest after the run."""
        return None

    def _write_supporting_assets(self, brief: str, papers: Sequence[Paper], records: Mapping[str, Mapping[str, Any]], requests: Sequence[Mapping[str, str]], terms: Sequence[str], entity_failures: Sequence[str], *, manifest: Mapping[str, Any] | None = None) -> None:
        manifest = manifest or self._load_manifest()
        coverage = manifest.get("coverage", {})
        provider_coverage = manifest.get("provider_query_coverage", {})
        self._write_evidence_notes_from_manifest(manifest)
        (self.root / "search-log.md").write_text("# Search Log\n\n" + "\n".join(f"- {path}: query derived from confirmed brief and entity terms" for path in SEARCH_PATHS) + "\n\n## Coverage\n\n" + "\n".join(f"- {key}: {', '.join(value)}" for key, value in provider_coverage.items()) + f"\n\n- Raw hits: {coverage.get('raw_hits', 0)}\n- Unique candidates: {coverage.get('unique_candidates', 0)}\n", encoding="utf-8")
        (self.root / "terms-and-entities.md").write_text("# Terms and Chemistry Entities\n\n" + "\n".join(f"- {term}" for term in terms) + ("\n\n## Provider degradation\n\n" + "\n".join(f"- {failure}" for failure in entity_failures) if entity_failures else "") + "\n", encoding="utf-8")
        self._write_comparability_projection(records)
        self._write_evidence_matrix_projection(manifest, records)
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

    def _write_comparability_projection(self, records: Mapping[str, Mapping[str, Any]]) -> None:
        rows = []
        for record in records.values():
            evidence = record.get("evidence_fields") or {}
            values = (
                record.get("source_id"), evidence.get("conditions", "UNKNOWN"),
                evidence.get("units", "UNKNOWN"), evidence.get("endpoint", "UNKNOWN"),
                "NOT_COMPARABLE until checked", record.get("claim_relevance", ""),
            )
            rows.append("| " + " | ".join(str(value or "UNKNOWN").replace("|", "\\|") for value in values) + " |")
        (self.root / "comparability-matrix.md").write_text(
            "# Comparability Matrix\n\n| Source | Conditions | Units | Endpoint | Comparable? | Notes |\n| --- | --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n",
            encoding="utf-8",
        )

    def _write_evidence_matrix_projection(self, manifest: Mapping[str, Any], records: Mapping[str, Mapping[str, Any]]) -> None:
        matrix = manifest.get("evidence_matrix", {})
        layers = matrix.get("layers", {})
        matrix_lines = ["# Evidence Matrix", "", "The canonical matrix is stored in manifest.json; this Markdown is a projection.", "", "## Four layers", ""]
        for layer, fields in layers.items():
            matrix_lines.append(f"- **{layer}**: {', '.join(str(field) for field in fields)}")
        matrix_lines.extend(["", "## Source evidence", "", "| Source | Evidence level | Locator(s) | Key result | Limitation |", "| --- | --- | --- | --- | --- |"])
        matrix_lines.extend(
            "| " + " | ".join(
                str(value or "UNKNOWN").replace("|", "\\|")
                for value in (
                    record.get("source_id"),
                    (record.get("evidence_fields") or {}).get("evidence_level", "UNKNOWN"),
                    (record.get("evidence_fields") or {}).get("locators", "UNKNOWN"),
                    (record.get("evidence_fields") or {}).get("key_result", "UNKNOWN"),
                    (record.get("evidence_fields") or {}).get("limitation", "UNKNOWN"),
                )
            ) + " |"
            for record in records.values()
        )
        matrix_lines.extend(["", "## Chemistry comparison spine", "", "| Source | System | Method | Conditions | Comparator | Endpoint | Units | Replicates | Uncertainty |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"])
        matrix_lines.extend(
            "| " + " | ".join(
                str(value or "UNKNOWN").replace("|", "\\|")
                for value in (
                    record.get("source_id"),
                    *((record.get("evidence_fields") or {}).get(field, "UNKNOWN") for field in ("system", "method", "conditions", "comparator", "endpoint", "units", "replicates", "uncertainty")),
                )
            ) + " |"
            for record in records.values()
        )
        (self.root / "evidence-matrix.md").write_text("\n".join(matrix_lines) + "\n", encoding="utf-8")

    def _write_evidence_notes_from_manifest(self, manifest: Mapping[str, Any]) -> None:
        lines = ["# Evidence Notes", "", "Parser output is a reading aid. A SOURCE_FACT is valid only after a human/agent checks the original PDF at the locator.", ""]
        for source in manifest.get("sources", []):
            evidence = source.get("evidence_fields") or {}
            if not evidence:
                continue
            identifier = str(source.get("identifier", source.get("source_id", "UNKNOWN")))
            lines.extend([f"## {identifier}", "", f"- Title: {source.get('title', 'Untitled')}", f"- Parser: {source.get('parser', 'UNKNOWN')}", f"- Evidence boundary: {evidence.get('evidence_label', 'SOURCE_EXCERPT')} until original PDF verification."])
            excerpts = evidence.get("excerpts") or []
            for excerpt in excerpts:
                lines.append(f"- SOURCE_EXCERPT [{identifier} @ {excerpt.get('locator', 'UNKNOWN')}]: {excerpt.get('text', '')}")
            if evidence.get("evidence_level") == "VERIFIED":
                claim = str(evidence.get("key_result") or evidence.get("study_object") or "Verified structured evidence")
                for locator in str(evidence.get("locators", "UNKNOWN")).split(";"):
                    lines.append(f"- VERIFIED_SOURCE_FACT [{identifier} @ {locator}]: {claim}")
            lines.append("")
        (self.root / "evidence-notes.md").write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _handoff(status: str, next_action: str, papers: Sequence[Paper], records: Mapping[str, Mapping[str, Any]], requests: Sequence[Mapping[str, str]], *, manifest: Mapping[str, Any] | None = None) -> str:
        coverage = (manifest or {}).get("coverage", {})
        lines = ["# Research Handoff", "", f"Result: {status}", "", f"Next action: {next_action}", "", f"Run ID: {(manifest or {}).get('run_id', 'UNKNOWN')}", f"Brief revision: {(manifest or {}).get('brief_revision', 'UNKNOWN')}", "", f"Sources registered: {len(papers)}", f"Parsed full texts: {sum(1 for r in records.values() if r.get('parser'))}", "", "## Coverage", "", f"- Raw hits: {coverage.get('raw_hits', 0)}", f"- Unique candidates: {coverage.get('unique_candidates', 0)}", f"- Included: {coverage.get('included', 0)}", f"- Excluded: {coverage.get('excluded', 0)}", f"- Maybe: {coverage.get('maybe', 0)}", f"- Primary evidence: {coverage.get('primary_evidence', 0)}", f"- Relevant candidates: {coverage.get('relevant_candidates', 0)}", f"- Relevant PDFs: {coverage.get('relevant_pdfs', 0)}", f"- Automatic downloads: {coverage.get('downloaded_pdfs', 0)}", f"- Parser attempts: {coverage.get('parser_attempts', 0)}", f"- Manual queue: {coverage.get('manual_queue', 0)}", f"- MinerU success: {coverage.get('mineru_success', 0)}", f"- MinerU failure: {coverage.get('mineru_failure', 0)}", f"- pdftotext fallback: {coverage.get('fallback_pdftotext', 0)}", f"- Unparsed: {coverage.get('unparsed', 0)}", f"- Evidence-ready: {coverage.get('evidence_ready', 0)}", f"- Gaps: {coverage.get('gaps', 0)}", "", "## Ownership", "", "Research owns manifest.json, source-registry.md, provider-status.md, terms-and-entities.md, evidence-notes.md, download-requests.md, the authorized PDF inbox and this handoff. Synthesis may read them but must not rewrite them.", "", "## Full-text route", "", "MinerU is the formal primary parser when configured. pdftotext is a LOW_FIDELITY_FALLBACK only. Original PDFs remain authoritative.", ""]
        if requests:
            lines.extend(["## Waiting for user", "", "The following core papers need a user download or explicit binding:", ""] + [f"- {request['identity']}: {request['url'] or request['url_status']} → {request['target_inbox']}" for request in requests] + [""])
        if status == "RESEARCH_GAP":
            lines.extend(["## Evidence boundary", "", "No missing SOURCE_FACT was invented. Synthesis may produce only an explicitly partial, unreviewed, evidence-bounded candidate.", ""])
        return "\n".join(lines)


def _paper_from_mapping(row: Mapping[str, Any]) -> Paper:
    url = str(row.get("full_text_url") or "")
    direct = bool(row.get("full_text_direct", url.lower().split("?", 1)[0].endswith(".pdf")))
    non_substitutability = row.get("non_substitutability") or row.get("irreplaceability") or row.get("indispensability") or ""
    return Paper(str(row.get("identifier") or row.get("doi") or row.get("id") or ""), str(row.get("title") or "Untitled"), str(row.get("doi") or ""), row.get("year"), tuple(str(a) for a in row.get("authors", [])), str(row.get("provider") or "fixture"), str(row.get("abstract") or ""), url, _legal_access_basis(row.get("access_basis")), str(row.get("priority") or "NORMAL"), str(row.get("claim_relevance") or ""), direct, str(non_substitutability), str(row.get("publication_type") or row.get("type") or "journal-article"), str(row.get("query_family") or ""), str(row.get("version") or ""))


def _legal_access_basis(value: object) -> str:
    normalized = str(value or "").strip().upper().replace("-", "_")
    return normalized if normalized in LEGAL_BASES else "AUTHORIZATION_UNCLEAR"


def _candidate_key(paper: Paper) -> str:
    if paper.doi.strip():
        return "doi:" + paper.doi.strip().lower().removeprefix("https://doi.org/")
    title = _compact(paper.title)
    author = _compact(paper.authors[0]) if paper.authors else ""
    return f"title:{title}|author:{author}|year:{paper.year or ''}"


def _title_candidate_key(paper: Paper) -> str:
    normalized = re.sub(r"\b(?:version|preprint|accepted manuscript|v\d+)\b|\([^)]*version[^)]*\)", "", paper.title, flags=re.I)
    author = _compact(paper.authors[0]) if paper.authors else ""
    return f"title:{_compact(normalized)}|author:{author}|year:{paper.year or ''}"


def _candidate_digest(candidates: Sequence[Mapping[str, Any]]) -> str:
    # This digest gates manifest-only reruns. Include every candidate property
    # that can change screening, provenance, or the legal/full-text route;
    # omit only volatile projection fields such as generated timestamps.
    keys = (
        "identifier", "doi", "title", "year", "publication_type", "provider",
        "providers", "claim_relevance", "non_substitutability", "priority",
        "version", "query_family", "abstract", "full_text_url", "full_text_url_status",
        "access_basis", "full_text_direct", "screening",
    )
    payload = [
        {key: row.get(key, "") for key in keys}
        for row in sorted(candidates, key=lambda item: str(item.get("identifier", "")))
    ]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def _screen_quality(paper: Paper) -> int:
    return int(bool(paper.abstract)) * 4 + int(bool(paper.claim_relevance)) * 2 + int(bool(paper.full_text_url)) + int(bool(paper.doi))


def _claim_relevance_bound(brief: str, relevance: str) -> bool:
    claims = _core_claims(brief)
    if claims == ("the confirmed review question",):
        return True
    claim_tokens = {
        token
        for claim in claims
        for token in re.findall(r"[a-z][a-z0-9-]{3,}", claim.lower())
        if token not in {"which", "what", "have", "been", "using", "must", "this", "that"}
    }
    relevance_tokens = set(re.findall(r"[a-z][a-z0-9-]{3,}", relevance.lower()))
    return bool(claim_tokens & relevance_tokens)


def _screen_paper(brief: str, paper: Paper) -> tuple[str, str, str, bool]:
    title = " ".join(paper.title.split()).lower()
    abstract = " ".join(paper.abstract.split()).lower()
    text = title + " " + abstract
    topic = _brief_topic(brief).lower()
    terms = _brief_search_terms(brief)
    chemistry = bool(_CHEMISTRY_HINT_RE.search(text))
    molecule_focus = any(token in text for token in ("small molecule", "small-molecule", "molecular", "molecule", "compound"))
    topic_tokens = [token for token in re.findall(r"[a-z][a-z0-9-]{3,}", topic) if token not in {"generative", "studies", "which", "have", "been", "using"}]
    topic_match = sum(1 for token in topic_tokens if token in text)
    alias_match = sum(1 for term in terms if term.lower() in text)
    publication_type = (paper.publication_type or "journal-article").lower().replace("_", "-")
    review_like = any(word in (title + " " + publication_type) for word in ("review", "survey", "meta-analysis", "workshop", "book chapter", "book-chapter", "editorial"))
    preprint = "preprint" in publication_type or "arxiv" in text
    generated_relevance = paper.claim_relevance.startswith("Candidate relevance from") or "screening still required" in paper.claim_relevance.lower()
    if not paper.claim_relevance.strip() and not generated_relevance:
        return "EXCLUDE", "excluded", "no core-claim relevance binding was supplied; retain only as a research gap", False
    year_match = re.search(r"(?:since|from)\s+(20\d{2})|(?:20\d{2})\s*[-–]\s*(?:present|20\d{2})", brief, re.I)
    min_year = int(year_match.group(1)) if year_match and year_match.group(1) else None
    if min_year is not None and paper.year is not None:
        try:
            numeric_year = int(paper.year)
        except (TypeError, ValueError):
            numeric_year = None
        if numeric_year is not None and numeric_year < min_year:
            return "EXCLUDE", "excluded", f"year {paper.year} is outside the confirmed range beginning {min_year}", False
    if review_like or preprint:
        role = "background" if review_like else "secondary"
        return "EXCLUDE", role, "publication type is contextual/non-primary and cannot enter the primary evidence pool", False
    explicit_relevance = bool(paper.claim_relevance.strip()) and not generated_relevance
    if explicit_relevance and not _claim_relevance_bound(brief, paper.claim_relevance):
        return "EXCLUDE", "excluded", "claim relevance is not lexically bound to a confirmed core claim", False
    if generated_relevance and not paper.abstract and not any(term in text for term in ("protein", "unrelated", "workshop", "survey", "review")):
        return "MAYBE", "secondary", "provider hit lacks an abstract or concrete chemistry match; manual screening is required", True
    if (not chemistry and not explicit_relevance) or (topic_tokens and topic_match == 0 and alias_match == 0 and not explicit_relevance):
        return "EXCLUDE", "excluded", "title/abstract lacks a concrete chemistry-topic match to the confirmed brief", False
    if not paper.abstract and not explicit_relevance:
        return "MAYBE", "secondary", "title is potentially relevant but abstract evidence is unavailable; manual screening required", True
    if molecule_focus and any(word in text for word in ("protein", "peptide", "sequence-only")) and "molecule" not in title:
        return "EXCLUDE", "excluded", "candidate is adjacent AI/protein work rather than the confirmed small-molecule topic", False
    if topic_match >= 1 or alias_match >= 1 or explicit_relevance:
        return "INCLUDE", "primary", "title/abstract and chemistry relevance match the confirmed review scope", True
    return "MAYBE", "secondary", "ambiguous metadata relevance; retain for review-relevant manual screening", True


def _screening_fields(brief: str, paper: Paper) -> dict[str, str]:
    title = " ".join(paper.title.split()).lower()
    abstract = " ".join(paper.abstract.split()).lower()
    topic = _brief_topic(brief).lower()
    topic_terms = [token for token in re.findall(r"[a-z][a-z0-9-]{3,}", topic) if token not in {"which", "what", "have", "been", "using"}]
    title_match = bool(_CHEMISTRY_HINT_RE.search(title)) and (not topic_terms or any(token in title for token in topic_terms) or any(term.lower() in title for term in _brief_search_terms(brief)))
    abstract_match = bool(abstract) and (title_match or any(term.lower() in abstract for term in _brief_search_terms(brief)))
    publication_type = (paper.publication_type or "UNKNOWN").lower()
    try:
        year = str(int(paper.year)) if paper.year is not None else "UNKNOWN"
    except (TypeError, ValueError):
        year = "UNKNOWN"
    return {
        "title_screen": "MATCH" if title_match else "NO_MATCH",
        "abstract_screen": "MATCH" if abstract_match else ("UNAVAILABLE" if not abstract else "NO_MATCH"),
        "publication_type_screen": "CONTEXTUAL" if any(word in publication_type for word in ("review", "survey", "workshop", "chapter", "preprint")) else ("PRIMARY" if publication_type != "unknown" else "UNKNOWN"),
        "year_screen": year,
        "topic_screen": "MATCH" if title_match or abstract_match else "NO_MATCH",
    }


def _source_id(identifier: str) -> str:
    compact = re.sub(r"[^a-zA-Z0-9]+", "-", identifier.lower()).strip("-")
    return (compact[:62] or "source") + "-" + hashlib.sha256(identifier.encode()).hexdigest()[:8]


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parser_failure_kind(parser: object, note: object) -> str:
    """Classify parser fallback without calling an unconfigured route a failure."""
    parser_name = str(parser or "").strip().lower()
    note_text = str(note or "").lower()
    if parser_name == "pdftotext":
        return "FALLBACK_UNCONFIGURED" if "mineru not configured" in note_text else "MINERU_FAILURE"
    if parser_name == "unparsed":
        return "PARSER_FAILURE"
    return ""


def _section(text: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\s*$([\s\S]*?)(?=^## |\Z)", text, re.M)
    return " ".join(match.group(1).split()) if match else ""


def _brief_revision(text: str) -> int:
    match = re.search(r"^revision:\s*(\d+)\s*$", text, re.M)
    return int(match.group(1)) if match else 1


def _review_specific_fields(text: str) -> list[str]:
    lowered = text.lower()
    if any(term in lowered for term in ("molecule", "molecular", "分子", "generative ai", "生成式")):
        return ["candidate_denominator", "generation_task", "screening_process", "synthesis_attempt", "identity_confirmation", "assay_endpoint", "closed_loop_feedback", "key_result", "limitation"]
    if any(term in lowered for term in ("catalysis", "catalytic", "催化", "coupling", "偶联")):
        return ["catalyst_system", "reaction_conditions", "ligand_or_additive", "comparator", "endpoint", "key_result", "limitation"]
    return ["study_object", "model_or_method", "data_or_training_source", "screening_process", "endpoint", "key_result", "limitation"]


def _brief_topic(text: str) -> str:
    """Read the Intent topic without confusing it with the research question."""
    frontmatter = re.search(r"^topic:\s*(.+?)\s*$", text, re.M)
    if frontmatter and frontmatter.group(1).strip():
        return " ".join(frontmatter.group(1).split())
    inline = re.search(r"^Topic:\s*(.+?)\s*$", text, re.M)
    if inline and inline.group(1).strip():
        return " ".join(inline.group(1).split())
    return _section(text, "Topic") or _section(text, "Research question")


def _brief_search_terms(text: str) -> tuple[str, ...]:
    """Extract bounded discovery/entity terms from the confirmed brief.

    The Intent brief is a human-facing document and its research question can
    be a full sentence. Provider search and chemistry entity endpoints need
    short concepts instead of that sentence, so only known bilingual aliases
    and short chemistry-hinted fragments are admitted here.
    """
    topic = _brief_topic(text)
    source = " ".join((topic, _section(text, "Research question"), *_core_claims(text)))
    lowered = source.lower()
    terms: list[str] = []

    def add(value: str) -> None:
        normalized = " ".join(value.replace("–", "-").split()).strip(" -:;,.，。；：")
        if not normalized or len(normalized) > 80 or normalized.lower() in {item.lower() for item in terms}:
            return
        terms.append(normalized)

    for alias, normalized in _SEARCH_TERM_ALIASES:
        if alias in lowered:
            add(normalized)

    for fragment in re.split(r"[｜|;,，。！？?!:：、()（）\[\]/]+", source):
        fragment = " ".join(fragment.split()).strip()
        words = re.findall(r"[A-Za-z][A-Za-z0-9-]*", fragment)
        if 1 <= len(words) <= 6 and len(fragment) <= 80 and _CHEMISTRY_HINT_RE.search(fragment):
            add(" ".join(words))

    if not terms:
        add(" ".join(re.findall(r"[A-Za-z][A-Za-z0-9-]*", topic)[:6]))
    return tuple(terms)


def _entity_search_terms(text: str) -> tuple[str, ...]:
    terms = _brief_search_terms(text)
    hinted = tuple(term for term in terms if _CHEMISTRY_HINT_RE.search(term))
    return hinted or terms[:1]


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
    redacted = _URL_PARAM_RE.sub(_redact_url_param, redacted)
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


def _redact_url_param(match: re.Match[str]) -> str:
    if not _sensitive_url_key(match.group(2)):
        return match.group(0)
    return f"{match.group(1)}{match.group(2)}{match.group(3)}[REDACTED]"


def _persisted_url(value: str) -> str:
    """Return a URL safe for Markdown/cache, withholding credential-bearing routes."""
    if not value.strip():
        return ""
    try:
        parsed = urlsplit(value)
        query = parse_qsl(parsed.query, keep_blank_values=True)
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    if parsed.username or parsed.password or _url_contains_credentials(value):
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _url_status(value: str) -> str:
    if not value.strip():
        return "NOT_FOUND"
    safe = _persisted_url(value)
    if safe:
        return "LEGAL_URL"
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "INVALID_URL"
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return "INVALID_URL"
    return "WITHHELD_CREDENTIAL_BEARING_URL"


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
    parser.add_argument("--config-choice", choices=CONFIGURATION_CHOICES)
    args = parser.parse_args()
    if args.env_file:
        _load_env_file(args.env_file)
    else:
        _load_env_file(args.project / ".env.local")
    try:
        result = ResearchStage(args.project).run(
            fixture_dir=args.fixture_dir,
            config_choice=args.config_choice,
        )
    except ConfigurationChoiceRequired as exc:
        print(json.dumps({"action": "CONFIGURATION_CHOICE_REQUIRED", "message": str(exc)}, ensure_ascii=False))
        return 2
    except ResearchPaused as exc:
        print(json.dumps({"action": "CONFIGURATION_PAUSED", "message": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": result.status, "next_action": result.next_action, "papers": len(result.papers), "parsed": result.parsed_count}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
