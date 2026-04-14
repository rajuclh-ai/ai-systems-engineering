"""
GitHub utility — fetch a pull request diff via the GitHub REST API.

Supports public PRs without a token.
Set GITHUB_TOKEN in .env for higher rate limits.

URL format accepted:
  https://github.com/{owner}/{repo}/pull/{number}
  https://github.com/{owner}/{repo}/pulls/{number}
"""

import re
import os
import requests


def parse_pr_url(url: str) -> tuple[str, str, int]:
    """
    Parse a GitHub PR URL and return (owner, repo, pr_number).
    Raises ValueError if the URL format is not recognised.
    """
    pattern = r"https?://github\.com/([^/]+)/([^/]+)/pulls?/(\d+)"
    match = re.match(pattern, url.strip())
    if not match:
        raise ValueError(
            f"Could not parse GitHub PR URL: {url!r}\n"
            "Expected format: https://github.com/owner/repo/pull/123"
        )
    owner, repo, pr_number = match.groups()
    return owner, repo, int(pr_number)


def fetch_pr_diff(pr_url: str) -> str:
    """
    Fetch the unified diff for a GitHub PR.

    Returns the raw diff string.
    Raises ValueError for bad URLs or HTTP errors.
    """
    owner, repo, pr_number = parse_pr_url(pr_url)

    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    headers = {
        "Accept": "application/vnd.github.v3.diff",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = requests.get(api_url, headers=headers, timeout=15)

    if response.status_code == 404:
        raise ValueError(f"PR not found: {pr_url}\nCheck the URL or make sure the repository is public.")
    if response.status_code == 401:
        raise ValueError("GitHub token missing or invalid. Paste the diff manually instead.")
    if response.status_code == 403:
        raise ValueError("GitHub rate limit exceeded or access denied. Add a GITHUB_TOKEN to .env.")
    if not response.ok:
        raise ValueError(f"GitHub API error {response.status_code}: {response.text[:200]}")

    diff = response.text.strip()
    if not diff:
        raise ValueError("The PR diff is empty — nothing to review.")

    return diff
