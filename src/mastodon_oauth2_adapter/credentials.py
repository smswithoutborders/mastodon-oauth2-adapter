# SPDX-License-Identifier: GPL-3.0-only
"""The client application registered with a Mastodon server."""

import json
from dataclasses import dataclass
from typing import Any

from relaysms_adapter_sdk import config_dir

FILENAME = "credentials.json"
DEFAULT_BASE_URL = "https://mastodon.social"
DEFAULT_SCOPE = ("profile", "write:statuses", "write:media")


@dataclass(frozen=True)
class Credentials:
    client_id: str
    client_secret: str
    redirect_uri: str
    base_url: str = DEFAULT_BASE_URL
    scope: tuple[str, ...] = DEFAULT_SCOPE


def load() -> Credentials:
    """Read credentials.json from the adapter's config directory.

    Raises:
        ValueError: The file is invalid.
    """
    path = config_dir() / FILENAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} is not valid JSON: {e}") from e

    for key in ("client_id", "client_secret"):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise ValueError(f"{key} in {path} must be a non-empty string.")
    redirect_uris = raw.get("redirect_uris")
    if not isinstance(redirect_uris, list) or not redirect_uris:
        raise ValueError(f"redirect_uris in {path} must be a non-empty list.")

    return Credentials(
        client_id=raw["client_id"],
        client_secret=raw["client_secret"],
        redirect_uri=redirect_uris[0],
        base_url=raw.get("base_url", DEFAULT_BASE_URL).rstrip("/"),
        scope=tuple(raw.get("scope", DEFAULT_SCOPE)),
    )


def save(data: dict[str, Any]) -> None:
    """Write the registration Mastodon returned to credentials.json."""
    path = config_dir() / FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    path.chmod(0o600)
