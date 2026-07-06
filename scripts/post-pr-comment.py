#!/usr/bin/env python3
"""Post terraform plan output as a comment on the pull request."""

import os
import sys
from pathlib import Path

import requests

PR_NUMBER = os.environ.get("PR_NUMBER", "").strip()
REPO = os.environ.get("REPO_FULL_NAME", "").strip()
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev").strip()
PLAN_FILE = Path(os.environ.get("PLAN_FILE", "/workspace/plan-output.txt"))
TOKEN_FILE = Path(os.environ.get("TOKEN_FILE", "/workspace/github_token.txt"))

MAX_BODY = 60_000


def main() -> None:
    if not PR_NUMBER:
        print("PR_NUMBER not set; skipping PR comment (not a pull-request build)")
        return

    if not REPO:
        print("REPO_FULL_NAME not set; skipping PR comment", file=sys.stderr)
        sys.exit(1)

    if not PLAN_FILE.is_file():
        print(f"Plan file not found: {PLAN_FILE}", file=sys.stderr)
        sys.exit(1)

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

    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    url = f"https://api.github.com/repos/{REPO}/issues/{PR_NUMBER}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    response = requests.post(url, headers=headers, json={"body": body}, timeout=30)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        print(response.text, file=sys.stderr)
        raise SystemExit(exc) from exc

    print(f"Posted plan comment to {REPO}#{PR_NUMBER}")


if __name__ == "__main__":
    main()
