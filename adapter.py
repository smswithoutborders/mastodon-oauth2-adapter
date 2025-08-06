"""
This program is free software: you can redistribute it under the terms
of the GNU General Public License, v. 3.0. If a copy of the GNU General
Public License was not distributed with this file, see <https://www.gnu.org/licenses/>.
"""

import os
import json
from typing import Dict, Any
import requests
from authlib.integrations.requests_client import OAuth2Session
from authlib.common.security import generate_token
from protocol_interfaces import OAuth2ProtocolInterface
from logutils import get_logger

logger = get_logger(__name__)

DEFAULT_CONFIG = {
    "urls": {
        "base_url": "https://mastodon.social",
        "register_uri": "https://mastodon.social/api/v1/apps",
        "auth_uri": "https://mastodon.social/oauth/authorize",
        "token_uri": "https://mastodon.social/oauth/token",
        "userinfo_uri": "https://mastodon.social/api/v1/accounts/verify_credentials",
        "send_message_uri": "https://mastodon.social/api/v1/statuses",
        "revoke_uri": "https://mastodon.social/oauth/revoke",
    },
    "params": {
        "scope": ["profile", "write:statuses"],
        "response_type": "code",
    },
}


def load_credentials(configs: Dict[str, Any]) -> Dict[str, str]:
    """Load OAuth2 credentials from a specified configuration."""

    creds_config = configs.get("credentials", {})
    creds_path = os.path.expanduser(creds_config.get("path", ""))
    if not creds_path:
        raise ValueError("Missing 'credentials.path' in configuration.")
    if not os.path.isabs(creds_path):
        creds_path = os.path.join(os.path.dirname(__file__), creds_path)

    logger.debug("Loading credentials from %s", creds_path)
    with open(creds_path, encoding="utf-8") as f:
        creds = json.load(f)

    return {
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "redirect_uri": creds["redirect_uris"][0],
    }


def save_credentials(configs: Dict[str, Any], credentials: Dict[str, Any]):
    """Save credentials to the credentials.json file."""

    creds_config = configs.get("credentials", {})
    creds_path = os.path.expanduser(creds_config.get("path", ""))
    if not creds_path:
        raise ValueError("Missing 'credentials.path' in configuration.")
    if not os.path.isabs(creds_path):
        creds_path = os.path.join(os.path.dirname(__file__), creds_path)

    logger.info("Saving credentials to: %s", creds_path)

    with open(creds_path, "w", encoding="utf-8") as f:
        json.dump(credentials, f, indent=2)

    logger.info("Credentials saved successfully")


def register_client(client_name, redirect_uris, website=None):
    """
    Register a new client application with a Mastodon server.
    """
    register_uri = DEFAULT_CONFIG["urls"]["register_uri"]

    logger.info("Registering client with server: %s", register_uri)

    registration_data = {
        "client_name": client_name,
        "redirect_uris": redirect_uris,
        "scopes": " ".join(DEFAULT_CONFIG["params"]["scope"]),
    }

    if website:
        registration_data["website"] = website

    try:
        response = requests.post(register_uri, data=registration_data, timeout=30)
        response.raise_for_status()

        result = response.json()

        logger.debug("Client registration response: %s", result)

        logger.info("Client registration successful")
        return result

    except requests.exceptions.RequestException as e:
        logger.exception("Failed to register client: %s", e)
        raise


class MastodonOAuth2Adapter(OAuth2ProtocolInterface):
    """Adapter for integrating Mastodon's OAuth2 protocol."""

    def __init__(self):
        self.default_config = DEFAULT_CONFIG
        self.credentials = load_credentials(self.config)
        self.session = OAuth2Session(
            client_id=self.credentials["client_id"],
            client_secret=self.credentials["client_secret"],
            redirect_uri=self.credentials["redirect_uri"],
            token_endpoint=self.default_config["urls"]["token_uri"],
        )

    def get_authorization_url(self, **kwargs):
        code_verifier = kwargs.get("code_verifier")
        autogenerate_code_verifier = kwargs.pop("autogenerate_code_verifier", False)
        redirect_url = kwargs.pop("redirect_url", None)

        if autogenerate_code_verifier and not code_verifier:
            code_verifier = generate_token(48)
            kwargs["code_verifier"] = code_verifier
            self.session.code_challenge_method = "S256"

        if code_verifier:
            kwargs["code_verifier"] = code_verifier
            self.session.code_challenge_method = "S256"

        if redirect_url:
            self.session.redirect_uri = redirect_url

        params = {**self.default_config["params"], **kwargs}

        authorization_url, state = self.session.create_authorization_url(
            self.default_config["urls"]["auth_uri"], **params
        )

        logger.debug("Authorization URL generated: %s", authorization_url)

        return {
            "authorization_url": authorization_url,
            "state": state,
            "code_verifier": code_verifier,
            "client_id": self.credentials["client_id"],
            "scope": ",".join(self.default_config["params"]["scope"]),
            "redirect_uri": self.session.redirect_uri,
        }

    def exchange_code_and_fetch_user_info(self, code, **kwargs):
        return super().exchange_code_and_fetch_user_info(code, **kwargs)

    def revoke_token(self, token, **kwargs):
        return super().revoke_token(token, **kwargs)

    def send_message(self, token, message, **kwargs):
        return super().send_message(token, message, **kwargs)
