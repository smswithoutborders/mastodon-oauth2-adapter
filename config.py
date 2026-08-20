# SPDX-License-Identifier: GPL-3.0-only

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from logutils import get_logger

logger = get_logger(__name__)

DEFAULT_BASE_URL = "https://mastodon.social"
DEFAULT_SCOPE = ["profile", "write:statuses", "write:media"]
DEFAULT_CHARACTER_LIMIT = 500
DEFAULT_THREAD_SUFFIX_RESERVE = 10


@dataclass
class Credentials:
    """OAuth2 client credentials and endpoints for the Mastodon adapter."""

    CLIENT_ID: str
    CLIENT_SECRET: str
    REDIRECT_URIS: List[str]
    SCOPE: List[str] = field(default_factory=lambda: list(DEFAULT_SCOPE))
    BASE_URL: str = DEFAULT_BASE_URL

    CHARACTER_LIMIT: int = DEFAULT_CHARACTER_LIMIT
    THREAD_SUFFIX_RESERVE: int = DEFAULT_THREAD_SUFFIX_RESERVE

    @property
    def redirect_uri(self) -> str:
        return self.REDIRECT_URIS[0]

    @property
    def auth_uri(self) -> str:
        return f"{self.BASE_URL}/oauth/authorize"

    @property
    def token_uri(self) -> str:
        return f"{self.BASE_URL}/oauth/token"

    @property
    def userinfo_uri(self) -> str:
        return f"{self.BASE_URL}/oauth/userinfo"

    @property
    def send_message_uri(self) -> str:
        return f"{self.BASE_URL}/api/v1/statuses"

    @property
    def revoke_uri(self) -> str:
        return f"{self.BASE_URL}/oauth/revoke"

    @property
    def register_uri(self) -> str:
        return f"{self.BASE_URL}/api/v1/apps"

    @property
    def media_uri(self) -> str:
        return f"{self.BASE_URL}/api/v2/media"


_REQUIRED_FIELDS = {"client_id", "client_secret", "redirect_uris"}


def _resolve_creds_path(configs: Dict[str, Any]) -> Path:
    creds_config = configs.get("credentials", {})
    raw_path = creds_config.get("path", "")
    if not raw_path:
        raise ValueError("Missing 'credentials.path' in configuration.")

    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = Path(__file__).parent / path
    return path


def _validate_creds(creds: Dict[str, Any]) -> None:
    missing = _REQUIRED_FIELDS - creds.keys()
    if missing:
        raise ValueError(
            f"Missing required credential fields: {', '.join(sorted(missing))}"
        )

    if not isinstance(creds["client_id"], str) or not creds["client_id"].strip():
        raise ValueError("'client_id' must be a non-empty string.")

    if (
        not isinstance(creds["client_secret"], str)
        or not creds["client_secret"].strip()
    ):
        raise ValueError("'client_secret' must be a non-empty string.")

    redirect_uris = creds["redirect_uris"]
    if (
        not isinstance(redirect_uris, list)
        or not redirect_uris
        or not all(isinstance(uri, str) and uri.strip() for uri in redirect_uris)
    ):
        raise ValueError("'redirect_uris' must be a non-empty list of strings.")

    if "scope" in creds and (
        not isinstance(creds["scope"], list)
        or not creds["scope"]
        or not all(isinstance(s, str) and s.strip() for s in creds["scope"])
    ):
        raise ValueError("'scope' must be a non-empty list of strings when provided.")

    if "base_url" in creds and (
        not isinstance(creds["base_url"], str) or not creds["base_url"].strip()
    ):
        raise ValueError("'base_url' must be a non-empty string when provided.")


def load_credentials(configs: Dict[str, Any]) -> Credentials:
    """Load, validate, and return a Credentials instance from the specified path."""
    path = _resolve_creds_path(configs)
    logger.debug("Loading credentials from %s", path)

    try:
        with path.open(encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Credentials file not found: {path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Credentials file is not valid JSON: {e}")

    _validate_creds(raw)

    return Credentials(
        CLIENT_ID=raw["client_id"],
        CLIENT_SECRET=raw["client_secret"],
        REDIRECT_URIS=raw["redirect_uris"],
        SCOPE=raw.get("scope", DEFAULT_SCOPE),
        BASE_URL=raw.get("base_url", DEFAULT_BASE_URL),
    )


def save_credentials(configs: Dict[str, Any], credentials: Dict[str, Any]) -> None:
    """Save credentials to the credentials.json file."""
    path = _resolve_creds_path(configs)
    logger.info("Saving credentials to: %s", path)

    with path.open("w", encoding="utf-8") as f:
        json.dump(credentials, f, indent=2)

    logger.info("Credentials saved successfully.")
