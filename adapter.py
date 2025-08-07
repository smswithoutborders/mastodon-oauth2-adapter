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
from authlib.integrations.base_client import OAuthError
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
        "userinfo_uri": "https://mastodon.social/oauth/userinfo",
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
        redirect_url = kwargs.pop("redirect_url", None)

        if redirect_url:
            self.session.redirect_uri = redirect_url

        try:
            token_response = self.session.fetch_token(
                self.default_config["urls"]["token_uri"], code=code, **kwargs
            )

            logger.debug("Token response: %s", token_response)
            logger.info("Access token fetched successfully.")

            if not token_response.get("refresh_token"):
                logger.warning("No refresh token received.")
                token_response["refresh_token"] = token_response.get("access_token")

            fetched_scopes = set(token_response.get("scope", "").split())
            expected_scopes = set(self.default_config["params"]["scope"])

            if not expected_scopes.issubset(fetched_scopes):
                raise ValueError(
                    f"Invalid token: Scopes do not match. Expected: {expected_scopes}, "
                    f"Received: {fetched_scopes}"
                )

            userinfo_response = self.session.get(
                self.default_config["urls"]["userinfo_uri"]
            ).json()
            userinfo = {
                "account_identifier": userinfo_response.get("preferred_username"),
                "name": userinfo_response.get("name"),
            }
            logger.info("User information fetched successfully.")

            return {"token": token_response, "userinfo": userinfo}
        except OAuthError as e:
            logger.error("Failed to fetch token or user info: %s", e)
            raise

    def revoke_token(self, token, **kwargs):
        self.session.token = token
        try:
            response = self.session.revoke_token(
                self.default_config["urls"]["revoke_uri"],
                token_type_hint="access_token",
            )

            if not response.ok:
                raise RuntimeError(response.text)
            response.raise_for_status()

            logger.info("Token revoked successfully.")
            return True
        except OAuthError as e:
            logger.error("Failed to revoke tokens: %s", e)
            raise

    def send_message(self, token, message, **kwargs):
        self.session.token = token
        url = self.default_config["urls"]["send_message_uri"]
        status_data = {"status": message}

        logger.debug("Sending status data: %s", status_data)

        try:
            response = self.session.post(url, json=status_data)

            if not response.ok:
                raise RuntimeError(response.text)
            response.raise_for_status()

            logger.info("Successfully sent message.")
            return {"success": True, "refreshed_token": self.session.token}
        except requests.exceptions.HTTPError as e:
            logger.error("Failed to send message: %s", e)
            return {
                "success": False,
                "message": e.response.text,
                "refreshed_token": self.session.token,
            }
