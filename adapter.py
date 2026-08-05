# SPDX-License-Identifier: GPL-3.0-only

import base64
import math
import textwrap
from dataclasses import dataclass
from typing import Any, Dict, List

import requests
from authlib.common.security import generate_token
from authlib.integrations.base_client import OAuthError
from authlib.integrations.requests_client import OAuth2Session

from config import Credentials, load_credentials
from logutils import get_logger
from protocol_interfaces import OAuth2ProtocolInterface
from utils import require

logger = get_logger(__name__)

MAX_MEDIA_ATTACHMENTS = 4


class AttachmentError(Exception):
    """Raised when an attachment cannot be uploaded or attached to a status."""


class MastodonAPIError(Exception):
    """Raised when the Mastodon API returns an error response."""


@dataclass
class Attachment:
    data: bytes
    filename: str
    mimetype: str


def _extract_error(response: requests.Response) -> str:
    try:
        return response.json().get("error") or response.text
    except Exception:
        return response.text or f"HTTP {response.status_code}"


def _handle_response(response: requests.Response) -> Any:
    """Raise a clean MastodonAPIError on failure, otherwise return the parsed body."""
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError:
        raise MastodonAPIError(_extract_error(response)) from None
    except requests.exceptions.RequestException as e:
        raise MastodonAPIError(str(e)) from e

    return response.json() if response.content else {}


def split_message_into_chunks(
    message: str, max_length: int, suffix_reserve: int
) -> List[str]:
    """Split a message into chunks that fit within Mastodon's character limit."""
    if len(message) <= max_length:
        return [message]

    effective_max_length = max_length - suffix_reserve
    threads_required = math.ceil(len(message) / effective_max_length)
    chars_per_thread = math.ceil(len(message) / threads_required)

    return textwrap.wrap(message, chars_per_thread, break_long_words=False)


class MastodonOAuth2Adapter(OAuth2ProtocolInterface):
    """Adapter integrating Mastodon's OAuth2 protocol with RelaySMS."""

    def __init__(self):
        self.credentials: Credentials = load_credentials(self.config)
        self.session = OAuth2Session(
            client_id=self.credentials.CLIENT_ID,
            client_secret=self.credentials.CLIENT_SECRET,
            redirect_uri=self.credentials.redirect_uri,
            token_endpoint=self.credentials.token_uri,
        )

    def get_authorization_url(self, **kwargs) -> Dict[str, Any]:
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

        params = {
            "scope": " ".join(self.credentials.SCOPE),
            "response_type": "code",
            **kwargs,
        }

        authorization_url, state = self.session.create_authorization_url(
            self.credentials.auth_uri, **params
        )

        logger.debug("Authorization URL generated: %s", authorization_url)

        return {
            "authorization_url": authorization_url,
            "state": state,
            "code_verifier": code_verifier,
            "client_id": self.credentials.CLIENT_ID,
            "scope": ",".join(self.credentials.SCOPE),
            "redirect_uri": self.session.redirect_uri,
        }

    def exchange_code_and_fetch_user_info(
        self, code: str, **kwargs
    ) -> Dict[str, Dict[str, Any]]:
        redirect_url = kwargs.pop("redirect_url", None)

        if redirect_url:
            self.session.redirect_uri = redirect_url

        try:
            token_response = self.session.fetch_token(
                self.credentials.token_uri, code=code, **kwargs
            )

            logger.debug("Token response: %s", token_response)
            logger.info("Access token fetched successfully.")

            if not token_response.get("refresh_token"):
                logger.warning("No refresh token received.")
                token_response["refresh_token"] = token_response.get("access_token")

            fetched_scopes = set(token_response.get("scope", "").split())
            expected_scopes = set(self.credentials.SCOPE)

            if not expected_scopes.issubset(fetched_scopes):
                raise ValueError(
                    f"Invalid token: Scopes do not match. Expected: {expected_scopes}, "
                    f"Received: {fetched_scopes}"
                )

            userinfo_response = _handle_response(
                self.session.get(self.credentials.userinfo_uri)
            )
            userinfo = {
                "account_identifier": userinfo_response.get("preferred_username"),
                "name": userinfo_response.get("name"),
            }
            logger.info("User information fetched successfully.")

            return {"token": token_response, "userinfo": userinfo}
        except (OAuthError, MastodonAPIError) as e:
            logger.error("Failed to fetch token or user info: %s", e)
            raise

    def revoke_token(self, token: Dict[str, str], **_) -> bool:
        self.session.token = token
        try:
            response = self.session.revoke_token(
                self.credentials.revoke_uri, token_type_hint="access_token"
            )
            _handle_response(response)

            logger.info("Token revoked successfully.")
            return True
        except (OAuthError, MastodonAPIError) as e:
            logger.error("Failed to revoke tokens: %s", e)
            raise

    def _upload_media(self, attachment: Attachment) -> str:
        """Upload a single attachment and return its Mastodon media id."""
        files = {
            "file": (
                attachment.filename,
                attachment.data,
                attachment.mimetype or "application/octet-stream",
            )
        }
        response = self.session.post(self.credentials.media_uri, files=files)
        try:
            media = _handle_response(response)
        except MastodonAPIError as e:
            raise AttachmentError(
                f"Failed to upload attachment '{attachment.filename}': {e}"
            ) from e

        media_id = media.get("id")
        if not media_id:
            raise AttachmentError(
                f"No media id returned for attachment '{attachment.filename}'."
            )
        return media_id

    def send_message(self, token: Dict[str, str], **kwargs) -> Dict[str, Any]:
        (message,) = require(kwargs, "message")

        processed_attachments: List[Attachment] = []
        for idx, att_dict in enumerate(kwargs.get("attachments") or []):
            filename = att_dict.get("filename") or f"attachment_{idx}"
            try:
                processed_attachments.append(
                    Attachment(
                        data=base64.b64decode(att_dict.get("data", ""), validate=True),
                        filename=filename,
                        mimetype=att_dict.get("mimetype") or "",
                    )
                )
            except Exception as exc:
                raise ValueError(f"Invalid attachment data in '{filename}'.") from exc

        if len(processed_attachments) > MAX_MEDIA_ATTACHMENTS:
            raise AttachmentError(
                f"Mastodon statuses support at most {MAX_MEDIA_ATTACHMENTS} media "
                f"attachments, got {len(processed_attachments)}."
            )

        self.session.token = token
        url = self.credentials.send_message_uri
        message_chunks = split_message_into_chunks(
            message,
            self.credentials.CHARACTER_LIMIT,
            self.credentials.THREAD_SUFFIX_RESERVE,
        )

        try:
            media_ids = [self._upload_media(a) for a in processed_attachments]

            thread_posts = []
            parent_post_id = None

            for i, chunk in enumerate(message_chunks):
                thread_text = (
                    f"{chunk} ({i + 1}/{len(message_chunks)})"
                    if len(message_chunks) > 1
                    else chunk
                )
                status_data = {"status": thread_text}

                if parent_post_id:
                    status_data["in_reply_to_id"] = parent_post_id
                if i == 0 and media_ids:
                    status_data["media_ids"] = media_ids

                logger.debug("Sending status data: %s", status_data)

                response = self.session.post(url, json=status_data)
                post_data = _handle_response(response)
                thread_posts.append(post_data)

                parent_post_id = post_data.get("id")

            logger.info("Successfully sent message with %d post(s).", len(thread_posts))
            return {"success": True, "refreshed_token": self.session.token}
        except MastodonAPIError as e:
            logger.error("Failed to send message: %s", e)
            return {
                "success": False,
                "message": str(e),
                "refreshed_token": self.session.token,
            }
        except AttachmentError as e:
            logger.error("Failed to attach media: %s", e)
            return {
                "success": False,
                "message": str(e),
                "refreshed_token": self.session.token,
            }
