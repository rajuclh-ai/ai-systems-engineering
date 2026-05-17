"""
GitHub REST API utility.
Fetches the unified diff for a pull request.
Carried over from v1 — no LLM involved.
"""
import os
import re
import httpx

GITHUB_API = "https://api.github.com"


def _parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    """Extract owner, repo, pr_number from a GitHub PR URL."""
    pattern = r"github\.com/([^/]+)/([^/]+)/pull/(\d+)"
    match = re.search(pattern, pr_url)
    if not match:
        raise ValueError(f"Could not parse GitHub PR URL: {pr_url}")
    owner, repo, pr_number = match.group(1), match.group(2), int(match.group(3))
    return owner, repo, pr_number


def fetch_pr_diff(pr_url: str) -> str:
    """Fetch the unified diff for a GitHub pull request."""
    owner, repo, pr_number = _parse_pr_url(pr_url)
    token = os.getenv("GITHUB_TOKEN", "")
    headers = {
        "Accept": "application/vnd.github.v3.diff",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}"
    response = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
    response.raise_for_status()
    return response.text


def post_pr_comment(pr_url: str, body: str) -> bool:
    """
    Post a review comment to a GitHub PR.
    Returns True on success, False if GITHUB_TOKEN is not set (display-only mode).
    """
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        return False

    owner, repo, pr_number = _parse_pr_url(pr_url)
    url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    response = httpx.post(url, json={"body": body}, headers=headers, timeout=30)
    response.raise_for_status()
    return True


def extract_repo(pr_url: str) -> str:
    """Return 'owner/repo' from a PR URL."""
    try:
        owner, repo, _ = _parse_pr_url(pr_url)
        return f"{owner}/{repo}"
    except ValueError:
        return ""
