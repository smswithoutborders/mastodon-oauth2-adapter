# SPDX-License-Identifier: GPL-3.0-only
"""mastodon-register: register the client application with a Mastodon server.

Writes credentials.json to RELAYSMS_ADAPTER_CONFIG_DIR, or .relaysms/config.
"""

import argparse
import os
import sys

import requests
from relaysms_adapter_sdk.paths import CONFIG_DIR_ENV

from mastodon_oauth2_adapter import credentials


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mastodon-register", description=__doc__)
    parser.add_argument("--name", required=True, help="client application name")
    parser.add_argument(
        "--redirect-uri", action="append", required=True, help="repeatable"
    )
    parser.add_argument("--website")
    parser.add_argument("--base-url", default=credentials.DEFAULT_BASE_URL)
    args = parser.parse_args(argv)
    os.environ.setdefault(CONFIG_DIR_ENV, ".relaysms/config")

    base_url = args.base_url.rstrip("/")
    body = {
        "client_name": args.name,
        "redirect_uris": args.redirect_uri,
        "scopes": " ".join(credentials.DEFAULT_SCOPE),
    }
    if args.website:
        body["website"] = args.website
    try:
        response = requests.post(f"{base_url}/api/v1/apps", json=body, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Registration failed: {e}", file=sys.stderr)
        return 1

    registration = response.json()
    credentials.save(
        {
            "client_id": registration["client_id"],
            "client_secret": registration["client_secret"],
            "redirect_uris": args.redirect_uri,
            "base_url": base_url,
        }
    )
    print(f"Registered {args.name} with {base_url}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
