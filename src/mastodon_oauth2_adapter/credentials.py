# SPDX-License-Identifier: GPL-3.0-only
"""The client application registered with a Mastodon server."""

from dataclasses import dataclass

from relaysms_adapter_sdk import read_config

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
    raw = read_config()
    for key in ("client_id", "client_secret"):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise ValueError(f"{key} in credentials.json must be a non-empty string.")
    redirect_uris = raw.get("redirect_uris")
    if not isinstance(redirect_uris, list) or not redirect_uris:
        raise ValueError("redirect_uris in credentials.json must be a non-empty list.")

    return Credentials(
        client_id=raw["client_id"],
        client_secret=raw["client_secret"],
        redirect_uri=redirect_uris[0],
        base_url=raw.get("base_url", DEFAULT_BASE_URL).rstrip("/"),
        scope=tuple(raw.get("scope", DEFAULT_SCOPE)),
    )
