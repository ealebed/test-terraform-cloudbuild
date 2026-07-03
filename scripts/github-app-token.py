#!/usr/bin/env python3
"""Generate a short-lived GitHub App installation access token."""

import os
import sys
import time

import jwt
import requests

APP_ID = os.environ["GH_APP_ID"]
INSTALLATION_ID = os.environ["GH_APP_INSTALLATION_ID"]
PRIVATE_KEY = os.environ["GH_APP_PRIVATE_KEY"]

# Secret Manager sometimes stores PEM keys with literal \n sequences.
if "\\n" in PRIVATE_KEY and "-----BEGIN" in PRIVATE_KEY:
    PRIVATE_KEY = PRIVATE_KEY.replace("\\n", "\n")

now = int(time.time())
payload = {
    "iat": now - 60,
    "exp": now + 540,
    "iss": APP_ID,
}

app_jwt = jwt.encode(payload, PRIVATE_KEY, algorithm="RS256")

url = f"https://api.github.com/app/installations/{INSTALLATION_ID}/access_tokens"
headers = {
    "Authorization": f"Bearer {app_jwt}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

response = requests.post(url, headers=headers, timeout=30)
try:
    response.raise_for_status()
except requests.HTTPError as exc:
    print(response.text, file=sys.stderr)
    raise SystemExit(exc) from exc

print(response.json()["token"])
