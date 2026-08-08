"""Optional automatic GitHub issue filing for unexpected integration errors.

Disabled by default. When a user opts in (Configure -> GitHub error
reporting) and supplies a fine-grained personal access token scoped to
*only* Issues: write on their chosen repository, unexpected (non-BLE,
non-timeout) exceptions raised by the coordinator are filed as GitHub
issues automatically: deduplicated by a fingerprint of the exception type
and its origin, and rate-limited so a repeating bug cannot spam the tracker.

This never runs for expected Bluetooth connectivity failures - only for
exceptions that indicate an actual defect in this integration's code (see
``_EXPECTED_ERRORS`` in coordinator.py for the boundary).
"""

from __future__ import annotations

import hashlib
import logging
import time
import traceback
from dataclasses import dataclass, field
from importlib import metadata
from typing import Any

import aiohttp
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import VERSION
from .redact import sanitize_string

_LOGGER = logging.getLogger(__name__)

_API_BASE = "https://api.github.com"
_ACCEPT_HEADER = "application/vnd.github+json"
_API_VERSION_HEADER = "2022-11-28"
_TIMEOUT = aiohttp.ClientTimeout(total=10)

_FINGERPRINT_COOLDOWN_SECONDS = 24 * 3600
_MAX_REPORTS_PER_DAY = 5
_ROLLING_WINDOW_SECONDS = 24 * 3600


@dataclass
class _ReportState:
    """Per-config-entry rate-limiting and dedup state, kept only in memory."""

    fingerprint_last_reported: dict[str, float] = field(default_factory=dict)
    report_timestamps: list[float] = field(default_factory=list)


class GitHubIssueReporter:
    """Fingerprinted, deduplicated, rate-limited GitHub issue filer."""

    def __init__(self, hass: HomeAssistant, *, repo: str, token: str) -> None:
        self._hass = hass
        self._repo = repo
        self._token = token
        self._state = _ReportState()

    async def async_report(self, error: Exception, context: str) -> None:
        """Fingerprint ``error`` and file a deduplicated GitHub issue if warranted."""
        fingerprint = _fingerprint(error)
        now = time.monotonic()

        last_reported = self._state.fingerprint_last_reported.get(fingerprint)
        if last_reported is not None and now - last_reported < _FINGERPRINT_COOLDOWN_SECONDS:
            _LOGGER.debug(
                "Skipping GitHub report for fingerprint %s: reported %.0fs ago (cooldown %ds)",
                fingerprint,
                now - last_reported,
                _FINGERPRINT_COOLDOWN_SECONDS,
            )
            return

        self._state.report_timestamps = [
            ts for ts in self._state.report_timestamps if now - ts < _ROLLING_WINDOW_SECONDS
        ]
        if len(self._state.report_timestamps) >= _MAX_REPORTS_PER_DAY:
            _LOGGER.warning(
                "Skipping GitHub report for fingerprint %s: daily cap of %d report(s) reached",
                fingerprint,
                _MAX_REPORTS_PER_DAY,
            )
            return

        try:
            if await self._async_issue_exists(fingerprint):
                _LOGGER.debug(
                    "GitHub issue for fingerprint %s already exists, not filing a duplicate", fingerprint
                )
                self._state.fingerprint_last_reported[fingerprint] = now
                return
            await self._async_create_issue(error, context, fingerprint)
        except Exception:  # noqa: BLE001 - reporting must never raise into the coordinator
            _LOGGER.warning("Failed to file automatic GitHub issue for fingerprint %s", fingerprint, exc_info=True)
            return

        self._state.fingerprint_last_reported[fingerprint] = now
        self._state.report_timestamps.append(now)

    async def _async_issue_exists(self, fingerprint: str) -> bool:
        session = async_get_clientsession(self._hass)
        query = f'repo:{self._repo} in:title "{fingerprint}" is:issue'
        async with session.get(
            f"{_API_BASE}/search/issues",
            params={"q": query},
            headers=self._headers(),
            timeout=_TIMEOUT,
        ) as response:
            if response.status != 200:
                _LOGGER.warning(
                    "GitHub issue search failed (HTTP %d), assuming no existing issue", response.status
                )
                return False
            payload: dict[str, Any] = await response.json()
            return int(payload.get("total_count", 0)) > 0

    async def _async_create_issue(self, error: Exception, context: str, fingerprint: str) -> None:
        session = async_get_clientsession(self._hass)
        title = f"[auto-report] {type(error).__name__} during {context} [{fingerprint}]"
        body = _build_body(error, context, fingerprint)
        async with session.post(
            f"{_API_BASE}/repos/{self._repo}/issues",
            json={"title": title, "body": body, "labels": ["auto-reported", "bug"]},
            headers=self._headers(),
            timeout=_TIMEOUT,
        ) as response:
            if response.status not in (200, 201):
                text = await response.text()
                _LOGGER.warning(
                    "Failed to file automatic GitHub issue (HTTP %d): %s",
                    response.status,
                    sanitize_string(text),
                )
                return
            payload: dict[str, Any] = await response.json()
            _LOGGER.info(
                "Filed automatic GitHub issue %s for fingerprint %s", payload.get("html_url"), fingerprint
            )

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": _ACCEPT_HEADER,
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": _API_VERSION_HEADER,
        }


def _fingerprint(error: Exception) -> str:
    """Derive a stable short id for one error, grouping by type + origin line."""
    tb = traceback.extract_tb(error.__traceback__)
    origin = ""
    for frame in tb:
        if "custom_components/jackery" in frame.filename.replace("\\", "/"):
            origin = f"{frame.filename.rsplit('/', 1)[-1]}:{frame.lineno}"
            break
    if not origin and tb:
        last = tb[-1]
        origin = f"{last.filename.rsplit('/', 1)[-1]}:{last.lineno}"
    digest = hashlib.sha256(f"{type(error).__name__}:{origin}".encode()).hexdigest()
    return digest[:12]


def _build_body(error: Exception, context: str, fingerprint: str) -> str:
    tb_text = sanitize_string("".join(traceback.format_exception(type(error), error, error.__traceback__)))
    return (
        "Automatically filed by the Jackery Home Assistant integration after an "
        f"unexpected error during **{context}**.\n\n"
        f"- Integration version: `{VERSION}`\n"
        f"- Home Assistant version: `{HA_VERSION}`\n"
        f"- bleak version: `{_package_version('bleak')}`\n"
        f"- Fingerprint: `{fingerprint}`\n\n"
        "Diagnostic data below has addresses, tokens, and other identifiers "
        "redacted before this report is sent.\n\n"
        f"```\n{tb_text}\n```\n"
    )


def _package_version(distribution: str) -> str:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "not installed"
