"""
Tests for the prerequisite verifiers.

The distinction these exist to protect is the one this whole codebase is built
around: **"I could not look" is not "it is not so."** A verifier returns
``None`` when it cannot answer and ``False`` only when it has actually
established the negative. Collapsing those two is how a BOM review reports an
unrun check as a pass, and how a launch tracker records a package as
unpublished because the wifi was off.

Nothing here touches the network. The suite must pass on a machine with no
connection, and a test that silently depends on PyPI being reachable is a test
that fails for reasons unrelated to the code.
"""

import json
import urllib.error

import pytest

from helix_ops import verify


class _Response:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_urlopen(monkeypatch, behaviour):
    monkeypatch.setattr("urllib.request.urlopen", behaviour)


# --------------------------------------------------------------------
# The published case
# --------------------------------------------------------------------

def test_a_published_package_is_confirmed_with_its_version(monkeypatch):
    _patch_urlopen(monkeypatch, lambda url, timeout=0: _Response(
        {"info": {"version": "0.1.2"}, "releases": {"0.1.0": [], "0.1.1": [], "0.1.2": []}}))

    ok, why = verify.check_pypi_published("helix-grounding")
    assert ok is True
    assert "0.1.2" in why and "3 release" in why


def test_a_missing_package_is_a_definite_no(monkeypatch):
    """404 from the index is a real answer, not an absence of one."""
    def raise404(url, timeout=0):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
    _patch_urlopen(monkeypatch, raise404)

    ok, why = verify.check_pypi_published("definitely-not-a-package-xyz")
    assert ok is False
    assert "not on PyPI" in why


# --------------------------------------------------------------------
# The distinction that matters
# --------------------------------------------------------------------

def test_no_network_is_none_not_false(monkeypatch):
    """The load-bearing test. Returning False here would record a live package
    as unpublished because the machine was offline — a tracker asserting
    something false about the world, which is worse than one that admits it
    does not know."""
    def unreachable(url, timeout=0):
        raise urllib.error.URLError("no route to host")
    _patch_urlopen(monkeypatch, unreachable)

    ok, why = verify.check_pypi_published("helix-grounding")
    assert ok is None
    assert "could not reach" in why


def test_a_server_error_is_none_not_false(monkeypatch):
    """A 503 says the index is unwell, not that the package is absent."""
    def raise503(url, timeout=0):
        raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, None)
    _patch_urlopen(monkeypatch, raise503)

    ok, why = verify.check_pypi_published("helix-grounding")
    assert ok is None
    assert "503" in why


def test_unreadable_json_is_none_not_false(monkeypatch):
    class _Garbage:
        def read(self): return b"<html>not json</html>"
        def __enter__(self): return self
        def __exit__(self, *exc): return False
    _patch_urlopen(monkeypatch, lambda url, timeout=0: _Garbage())

    ok, _ = verify.check_pypi_published("helix-grounding")
    assert ok is None


# --------------------------------------------------------------------
# Dispatch
# --------------------------------------------------------------------

def test_pypi_is_no_longer_declared_unverifiable():
    """It was, and it sat recorded as false for a week while the package was
    live. A question one public GET can answer should not be answered by
    asking somebody to remember."""
    assert "pypi_published" not in verify.UNVERIFIABLE


def test_demo_works_is_still_honestly_unverifiable():
    """This one really is a fact about a person, and pretending otherwise
    would be worse than admitting it."""
    ok, why = verify.check("demo_works", "", "helix-grounding")
    assert ok is None
    assert "somebody else's machine" in why


def test_an_unknown_prerequisite_returns_none(monkeypatch):
    ok, why = verify.check("invented_key", "", "helix-grounding")
    assert ok is None
    assert "no verifier" in why


def test_a_repo_url_with_no_github_in_it_is_none_not_false():
    """Same rule: an unparseable URL means the check did not run."""
    ok, why = verify.check_repo_public("https://example.com/not-github")
    assert ok is None
    assert "no github.com repository" in why
