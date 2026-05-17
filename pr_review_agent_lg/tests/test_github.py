"""
Tests for GitHub REST API utility.
All HTTP calls are mocked — no real network requests.
"""
import pytest
from unittest.mock import patch, MagicMock
from utils.github import _parse_pr_url, extract_repo, fetch_pr_diff, post_pr_comment


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("https://github.com/owner/repo/pull/123",        ("owner", "repo", 123)),
    ("https://github.com/org-name/my.repo/pull/1",    ("org-name", "my.repo", 1)),
    ("http://github.com/foo/bar/pull/99",              ("foo", "bar", 99)),
])
def test_parse_pr_url(url, expected):
    assert _parse_pr_url(url) == expected


def test_parse_pr_url_invalid():
    with pytest.raises(ValueError, match="Could not parse"):
        _parse_pr_url("https://github.com/owner/repo")


def test_extract_repo():
    assert extract_repo("https://github.com/owner/repo/pull/1") == "owner/repo"


def test_extract_repo_invalid_returns_empty():
    assert extract_repo("not-a-url") == ""


# ---------------------------------------------------------------------------
# fetch_pr_diff
# ---------------------------------------------------------------------------

def test_fetch_pr_diff_calls_github_api(sample_diff):
    mock_response = MagicMock()
    mock_response.text = sample_diff
    mock_response.raise_for_status = MagicMock()

    with patch("utils.github.httpx.get", return_value=mock_response) as mock_get:
        result = fetch_pr_diff("https://github.com/owner/repo/pull/1")

    assert result == sample_diff
    call_args = mock_get.call_args
    assert "repos/owner/repo/pulls/1" in call_args[0][0]


def test_fetch_pr_diff_sets_auth_header_when_token_present(monkeypatch, sample_diff):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    mock_response = MagicMock()
    mock_response.text = sample_diff
    mock_response.raise_for_status = MagicMock()

    with patch("utils.github.httpx.get", return_value=mock_response) as mock_get:
        fetch_pr_diff("https://github.com/owner/repo/pull/1")

    headers = mock_get.call_args[1]["headers"]
    assert "Authorization" in headers
    assert "ghp_test_token" in headers["Authorization"]


def test_fetch_pr_diff_no_auth_header_without_token(monkeypatch, sample_diff):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    mock_response = MagicMock()
    mock_response.text = sample_diff
    mock_response.raise_for_status = MagicMock()

    with patch("utils.github.httpx.get", return_value=mock_response) as mock_get:
        fetch_pr_diff("https://github.com/owner/repo/pull/1")

    headers = mock_get.call_args[1]["headers"]
    assert "Authorization" not in headers


# ---------------------------------------------------------------------------
# post_pr_comment
# ---------------------------------------------------------------------------

def test_post_pr_comment_returns_false_without_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    result = post_pr_comment("https://github.com/owner/repo/pull/1", "review body")
    assert result is False


def test_post_pr_comment_posts_when_token_present(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with patch("utils.github.httpx.post", return_value=mock_response) as mock_post:
        result = post_pr_comment("https://github.com/owner/repo/pull/1", "review body")

    assert result is True
    call_args = mock_post.call_args
    assert "repos/owner/repo/issues/1/comments" in call_args[0][0]
    assert mock_post.call_args[1]["json"]["body"] == "review body"
