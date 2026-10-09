# SPDX-License-Identifier: GPL-3.0-only

import logging
import math
import textwrap
from typing import Any, override

import requests
from authlib.integrations.base_client import OAuthError
from authlib.integrations.requests_client import OAuth2Session
from relaysms_adapter_sdk import (
    Account,
    Attachment,
    AuthenticationError,
    AuthorizationRequest,
    AuthorizationUrl,
    CodeExchangeRequest,
    InvalidParamsError,
    OAuth2Adapter,
    RateLimitedError,
    RevokeRequest,
    SendRequest,
    SendResult,
    TokenInvalidError,
    UpstreamError,
)

from mastodon_oauth2_adapter import credentials

logger = logging.getLogger(__name__)

CHARACTER_LIMIT = 500
# Room for the " (n/m)" each post of a thread ends with.
THREAD_SUFFIX_RESERVE = 10
MAX_ATTACHMENTS = 4
TIMEOUT = 30


class MastodonAdapter(OAuth2Adapter):
    def __init__(self) -> None:
        self.credentials = credentials.load()

    @override
    def create_authorization_url(
        self, request: AuthorizationRequest
    ) -> AuthorizationUrl:
        session = self._session(
            redirect_url=request.redirect_url, pkce=bool(request.code_verifier)
        )
        url, state = session.create_authorization_url(
            self._url("/oauth/authorize"),
            state=request.state,
            code_verifier=request.code_verifier,
            scope=" ".join(self.credentials.scope),
        )
        return AuthorizationUrl(
            url=url,
            state=state,
            code_verifier=request.code_verifier,
            client_id=self.credentials.client_id,
            # Clients expect the scope comma-separated.
            scope=",".join(self.credentials.scope),
            redirect_url=session.redirect_uri,
        )

    @override
    def exchange_code(self, request: CodeExchangeRequest) -> Account:
        session = self._session(redirect_url=request.redirect_url)
        try:
            token = session.fetch_token(
                self._url("/oauth/token"),
                code=request.code,
                code_verifier=request.code_verifier,
            )
        except OAuthError as e:
            raise AuthenticationError(f"Mastodon rejected the code: {e.error}") from e
        except requests.RequestException as e:
            raise UpstreamError(f"Mastodon couldn't be reached: {e}") from e

        missing = set(self.credentials.scope) - set(token.get("scope", "").split())
        if missing:
            raise AuthenticationError(
                f"Access wasn't granted to {', '.join(sorted(missing))}."
            )

        userinfo = self._call("GET", "/oauth/userinfo", token).json()
        return Account(
            identifier=userinfo["preferred_username"],
            token=dict(token),
            name=userinfo.get("name"),
        )

    @override
    def send_message(self, request: SendRequest) -> SendResult:
        if request.account is None or request.account.token is None:
            raise InvalidParamsError("Mastodon posts only from a linked account.")
        attachments = request.message.attachments
        if len(attachments) > MAX_ATTACHMENTS:
            raise InvalidParamsError(
                f"Mastodon takes at most {MAX_ATTACHMENTS} attachments."
            )

        token = request.account.token
        media_ids = [self._upload(token, attachment) for attachment in attachments]
        chunks = split_message(request.message.body)
        parent_id = None
        for i, chunk in enumerate(chunks):
            status: dict[str, Any] = {
                "status": f"{chunk} ({i + 1}/{len(chunks)})"
                if len(chunks) > 1
                else chunk
            }
            if parent_id:
                status["in_reply_to_id"] = parent_id
            if i == 0 and media_ids:
                status["media_ids"] = media_ids
            post = self._call("POST", "/api/v1/statuses", token, json=status)
            parent_id = post.json()["id"]
        logger.info("Posted %d status(es).", len(chunks))
        return SendResult()

    @override
    def revoke(self, request: RevokeRequest) -> None:
        access_token = (request.account.token or {}).get("access_token")
        if not access_token:
            return
        data = {
            "client_id": self.credentials.client_id,
            "client_secret": self.credentials.client_secret,
            "token": access_token,
        }
        try:
            response = requests.post(
                self._url("/oauth/revoke"), data=data, timeout=TIMEOUT
            )
        except requests.RequestException as e:
            raise UpstreamError(f"Mastodon couldn't be reached: {e}") from e
        _check(response)
        logger.info("Token revoked.")

    def _upload(self, token: dict[str, Any], attachment: Attachment) -> str:
        file = (attachment.filename, attachment.data, attachment.mimetype)
        media = self._call("POST", "/api/v2/media", token, files={"file": file})
        return media.json()["id"]

    def _call(
        self, method: str, path: str, token: dict[str, Any], **kwargs: Any
    ) -> requests.Response:
        headers = {"Authorization": f"Bearer {token['access_token']}"}
        try:
            response = requests.request(
                method, self._url(path), headers=headers, timeout=TIMEOUT, **kwargs
            )
        except requests.RequestException as e:
            raise UpstreamError(f"Mastodon couldn't be reached: {e}") from e
        return _check(response)

    def _session(
        self, *, redirect_url: str | None = None, pkce: bool = False
    ) -> OAuth2Session:
        return OAuth2Session(
            client_id=self.credentials.client_id,
            client_secret=self.credentials.client_secret,
            redirect_uri=redirect_url or self.credentials.redirect_uri,
            code_challenge_method="S256" if pkce else None,
        )

    def _url(self, path: str) -> str:
        return self.credentials.base_url + path


def split_message(message: str) -> list[str]:
    """Split a message into posts that fit the character limit."""
    if len(message) <= CHARACTER_LIMIT:
        return [message]
    posts = math.ceil(len(message) / (CHARACTER_LIMIT - THREAD_SUFFIX_RESERVE))
    width = math.ceil(len(message) / posts)
    return textwrap.wrap(message, width, break_long_words=False)


def _check(response: requests.Response) -> requests.Response:
    if response.ok:
        return response
    status = response.status_code
    if status in {401, 403}:
        raise TokenInvalidError(f"Mastodon refused the token: {_error(response)}")
    if status == 429:
        raise RateLimitedError("Mastodon is rate limiting requests.")
    raise UpstreamError(f"Mastodon returned {status}: {_error(response)}")


def _error(response: requests.Response) -> str:
    try:
        return response.json().get("error") or response.text
    except ValueError:
        return response.text
