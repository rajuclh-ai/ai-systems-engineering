"""Tests for utils/github.py — URL parsing and error handling."""
import pytest
from utils.github import parse_pr_url


# ── Valid URLs ─────────────────────────────────────────────────────────────────

def test_parse_standard_pull_url():
    owner, repo, num = parse_pr_url("https://github.com/octocat/hello-world/pull/1")
    assert owner == "octocat"
    assert repo == "hello-world"
    assert num == 1


def test_parse_pulls_variant():
    owner, repo, num = parse_pr_url("https://github.com/octocat/hello-world/pulls/42")
    assert owner == "octocat"
    assert repo == "hello-world"
    assert num == 42


def test_parse_real_repo_url():
    owner, repo, num = parse_pr_url("https://github.com/rajuclh-ai/ml-fundamentals/pull/1")
    assert owner == "rajuclh-ai"
    assert repo == "ml-fundamentals"
    assert num == 1


def test_parse_url_with_trailing_whitespace():
    owner, repo, num = parse_pr_url("  https://github.com/octocat/hello-world/pull/5  ")
    assert owner == "octocat"
    assert num == 5


def test_parse_large_pr_number():
    owner, repo, num = parse_pr_url("https://github.com/org/repo/pull/9999")
    assert num == 9999


def test_parse_repo_with_hyphens_and_underscores():
    owner, repo, num = parse_pr_url("https://github.com/my-org/my_repo/pull/3")
    assert owner == "my-org"
    assert repo == "my_repo"
    assert num == 3


# ── Invalid URLs — must raise ValueError ──────────────────────────────────────

def test_invalid_not_github():
    with pytest.raises(ValueError, match="Could not parse"):
        parse_pr_url("https://gitlab.com/owner/repo/pull/1")


def test_invalid_missing_pr_number():
    with pytest.raises(ValueError):
        parse_pr_url("https://github.com/owner/repo/pull/")


def test_invalid_no_path():
    with pytest.raises(ValueError):
        parse_pr_url("https://github.com")


def test_invalid_empty_string():
    with pytest.raises(ValueError):
        parse_pr_url("")


def test_invalid_random_string():
    with pytest.raises(ValueError):
        parse_pr_url("not a url at all")
