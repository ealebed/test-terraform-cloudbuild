#!/usr/bin/env python3
"""Post terraform plan output as a comment on the pull request."""

import os
import sys
from pathlib import Path

import requests

PR_NUMBER = os.environ.get("PR_NUMBER", "").strip()
HEAD_BRANCH = os.environ.get("HEAD_BRANCH", "").strip()
BASE_BRANCH = os.environ.get("BASE_BRANCH", "master").strip()
REPO = os.environ.get("REPO_FULL_NAME", "").strip()
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev").strip()
PLAN_FILE = Path(os.environ.get("PLAN_FILE", "/workspace/plan-output.txt"))
TOKEN_FILE = Path(os.environ.get("TOKEN_FILE", "/workspace/github_token.txt"))

MAX_BODY = 60_000


def github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def resolve_pr_number(token: str, repo: str, pr_number: str, head_branch: str, base_branch: str) -> str:
    if pr_number:
        return pr_number

    if not head_branch:
        return ""

    owner = repo.split("/")[0]
    url = f"https://api.github.com/repos/{repo}/pulls"
    params = {
        "head": f"{owner}:{head_branch}",
        "base": base_branch,
        "state": "open",
    }
    response = requests.get(url, headers=github_headers(token), params=params, timeout=30)
    response.raise_for_status()
    pulls = response.json()
    if not pulls:
        print(f"No open PR found for head={head_branch} base={base_branch}", file=sys.stderr)
        return ""

    return str(pulls[0]["number"])


def main() -> None:
    if not REPO:
        print("REPO_FULL_NAME not set; skipping PR comment", file=sys.stderr)
        sys.exit(1)

    if not PLAN_FILE.is_file():
        print(f"Plan file not found: {PLAN_FILE}", file=sys.stderr)
        sys.exit(1)

    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    pr_number = resolve_pr_number(token, REPO, PR_NUMBER, HEAD_BRANCH, BASE_BRANCH)
    if not pr_number:
        print("PR_NUMBER not available; skipping PR comment")
        return

    plan = PLAN_FILE.read_text(encoding="utf-8").strip()
    if not plan:
        plan = "(empty plan)"

    body = (
        f"## Terraform Plan (`{ENVIRONMENT}`)\n\n"
        f"<details>\n<summary>Show plan</summary>\n\n"
        f"```terraform\n{plan}\n```\n\n</details>\n"
    )

    if len(body) > MAX_BODY:
        body = (
            f"## Terraform Plan (`{ENVIRONMENT}`)\n\n"
            f"<details>\n<summary>Show plan (truncated)</summary>\n\n"
            f"```terraform\n{plan[: MAX_BODY - 200]}\n```\n\n</details>\n"
        )

    url = f"https://api.github.com/repos/{REPO}/issues/{pr_number}/comments"

    response = requests.post(
        url,
        headers=github_headers(token),
        json={"body": body},
        timeout=30,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        print(response.text, file=sys.stderr)
        raise SystemExit(exc) from exc

    print(f"Posted plan comment to {REPO}#{pr_number}")


if __name__ == "__main__":
    main()
