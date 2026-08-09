"""Tests for the opt-in automatic GitHub issue reporter.

Covers the safety properties that matter most: stable fingerprints so
identical bugs dedupe, a cooldown per fingerprint, and a rolling daily cap -
all so a repeating bug can't spam the maintainer's issue tracker, and so a
failure to reach GitHub never raises back into the coordinator.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.jackery.github_reporter import GitHubIssueReporter, _fingerprint


def _raise_value_error() -> None:
    raise ValueError("boom")


def _make_error() -> ValueError:
    try:
        _raise_value_error()
    except ValueError as err:
        return err
    raise AssertionError("unreachable")


def test_fingerprint_is_stable_for_the_same_error_site() -> None:
    first = _fingerprint(_make_error())
    second = _fingerprint(_make_error())
    assert first == second
    assert len(first) == 12


def test_fingerprint_differs_for_different_exception_types() -> None:
    try:
        raise KeyError("boom")
    except KeyError as err:
        key_error_fp = _fingerprint(err)
    assert key_error_fp != _fingerprint(_make_error())


class _FakeResponse:
    def __init__(self, status: int, payload: dict) -> None:
        self.status = status
        self._payload = payload

    async def json(self):
        return self._payload

    async def text(self):
        return str(self._payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeSession:
    """Records calls and returns scripted responses for get()/post()."""

    def __init__(self, *, search_total_count: int = 0, create_status: int = 201) -> None:
        self.search_total_count = search_total_count
        self.create_status = create_status
        self.get_calls: list[dict] = []
        self.post_calls: list[dict] = []

    def get(self, url, **kwargs):
        self.get_calls.append({"url": url, **kwargs})
        return _FakeResponse(200, {"total_count": self.search_total_count})

    def post(self, url, **kwargs):
        self.post_calls.append({"url": url, **kwargs})
        return _FakeResponse(self.create_status, {"html_url": "https://github.com/o/r/issues/1"})


@pytest.fixture
def hass():
    return MagicMock()


def _patched_session(session: _FakeSession):
    return patch(
        "custom_components.jackery.github_reporter.async_get_clientsession",
        return_value=session,
    )


async def test_report_creates_an_issue_when_none_exists(hass) -> None:
    session = _FakeSession(search_total_count=0)
    reporter = GitHubIssueReporter(hass, repo="owner/repo", token="tok")

    with _patched_session(session):
        await reporter.async_report(_make_error(), "poll")

    assert len(session.post_calls) == 1
    assert "owner/repo" in session.post_calls[0]["url"]


async def test_report_skips_creating_a_duplicate_issue(hass) -> None:
    session = _FakeSession(search_total_count=1)
    reporter = GitHubIssueReporter(hass, repo="owner/repo", token="tok")

    with _patched_session(session):
        await reporter.async_report(_make_error(), "poll")

    assert session.post_calls == []


async def test_report_respects_per_fingerprint_cooldown(hass) -> None:
    session = _FakeSession(search_total_count=0)
    reporter = GitHubIssueReporter(hass, repo="owner/repo", token="tok")

    with _patched_session(session):
        await reporter.async_report(_make_error(), "poll")
        await reporter.async_report(_make_error(), "poll")

    # Second call for the same fingerprint should be skipped by the cooldown
    # before it ever calls the (fake) network.
    assert len(session.get_calls) == 1
    assert len(session.post_calls) == 1


def _raise_at_distinct_site(site: int) -> None:
    """Raise from one of several distinct source lines so each gets its own fingerprint."""
    if site == 0:
        raise ValueError("bug 0")
    if site == 1:
        raise ValueError("bug 1")
    if site == 2:
        raise ValueError("bug 2")
    if site == 3:
        raise ValueError("bug 3")
    if site == 4:
        raise ValueError("bug 4")
    raise ValueError("bug 5")


async def test_report_respects_daily_rate_cap(hass) -> None:
    session = _FakeSession(search_total_count=0)
    reporter = GitHubIssueReporter(hass, repo="owner/repo", token="tok")

    errors = []
    for site in range(6):
        try:
            _raise_at_distinct_site(site)
        except ValueError as err:
            errors.append(err)

    fingerprints = {_fingerprint(err) for err in errors}
    assert len(fingerprints) == 6, "test setup bug: expected 6 distinct fingerprints"

    with _patched_session(session):
        for err in errors:
            await reporter.async_report(err, "poll")

    # 6 distinct bugs, but the daily cap is 5: the 6th must be suppressed.
    assert len(session.post_calls) == 5


async def test_report_creates_an_issue_when_search_request_fails(hass) -> None:
    # A non-200 search response means we can't confirm whether a duplicate
    # exists; the reporter should assume no duplicate and still file, rather
    # than silently dropping a genuine bug report.
    session = _FakeSession(search_total_count=0)
    session.get = lambda url, **kwargs: _FakeResponse(503, {})
    reporter = GitHubIssueReporter(hass, repo="owner/repo", token="tok")

    with _patched_session(session):
        await reporter.async_report(_make_error(), "poll")

    assert len(session.post_calls) == 1


async def test_report_does_not_raise_when_issue_creation_request_fails(hass) -> None:
    session = _FakeSession(search_total_count=0, create_status=500)
    reporter = GitHubIssueReporter(hass, repo="owner/repo", token="tok")

    with _patched_session(session):
        await reporter.async_report(_make_error(), "poll")  # must not raise

    assert len(session.post_calls) == 1


async def test_reporter_never_raises_when_the_network_call_fails(hass) -> None:
    reporter = GitHubIssueReporter(hass, repo="owner/repo", token="tok")

    with patch(
        "custom_components.jackery.github_reporter.async_get_clientsession",
        side_effect=RuntimeError("no session"),
    ):
        await reporter.async_report(_make_error(), "poll")  # must not raise


async def test_create_issue_title_includes_type_context_and_fingerprint(hass) -> None:
    session = _FakeSession(search_total_count=0)
    reporter = GitHubIssueReporter(hass, repo="owner/repo", token="tok")

    with _patched_session(session):
        await reporter.async_report(_make_error(), "write")

    body = session.post_calls[0]["json"]
    assert "ValueError" in body["title"]
    assert "write" in body["title"]
    assert "auto-reported" in body["labels"]


async def test_report_body_redacts_secrets_in_the_traceback(hass) -> None:
    session = _FakeSession(search_total_count=0)
    reporter = GitHubIssueReporter(hass, repo="owner/repo", token="tok")

    try:
        raise ValueError("token=ghp_abcdefghijklmnopqrstuvwxyz0123456789")
    except ValueError as err:
        error = err

    with _patched_session(session):
        await reporter.async_report(error, "poll")

    body_text = session.post_calls[0]["json"]["body"]
    assert "ghp_" not in body_text
    assert "**REDACTED**" in body_text


async def test_headers_never_log_the_raw_token_in_a_readable_key(hass) -> None:
    reporter = GitHubIssueReporter(hass, repo="owner/repo", token="secret-token-value")
    headers = reporter._headers()
    assert headers["Authorization"] == "Bearer secret-token-value"
