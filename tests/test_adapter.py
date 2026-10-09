# SPDX-License-Identifier: GPL-3.0-only

import json
from urllib.parse import parse_qs, urlparse

import pytest
import responses
from relaysms_adapter_sdk import (
    Account,
    Attachment,
    AuthenticationError,
    AuthorizationRequest,
    CodeExchangeRequest,
    InvalidParamsError,
    Message,
    RateLimitedError,
    RevokeRequest,
    SendRequest,
    TokenInvalidError,
    UpstreamError,
)
from relaysms_adapter_sdk.paths import CONFIG_DIR_ENV, STATE_DIR_ENV

from mastodon_oauth2_adapter import MastodonAdapter, register
from mastodon_oauth2_adapter.adapter import CHARACTER_LIMIT, split_message

BASE = "https://social.example"
SCOPE = "profile write:statuses write:media"
# Mastodon tokens don't expire; the old adapter copied access_token into refresh_token.
TOKEN = {
    "access_token": "access",
    "refresh_token": "access",
    "token_type": "Bearer",
    "scope": SCOPE,
    "created_at": 1,
}
ACCOUNT = Account("me", token=TOKEN)


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv(CONFIG_DIR_ENV, str(tmp_path))
    monkeypatch.setenv(STATE_DIR_ENV, str(tmp_path / "state"))
    return tmp_path


@pytest.fixture
def adapter(config):
    # The shape the old register command saved.
    (config / "credentials.json").write_text(
        json.dumps(
            {
                "id": "1",
                "name": "RelaySMS",
                "client_id": "client",
                "client_secret": "secret",
                "redirect_uris": ["https://app/callback"],
                "vapid_key": "k",
                "base_url": BASE,
            }
        )
    )
    return MastodonAdapter()


@pytest.fixture
def mastodon():
    with responses.RequestsMock() as mock:
        yield mock


def send(adapter, body="Hello", attachments=()):
    return adapter.send_message(
        SendRequest(Message(body=body, attachments=attachments), ACCOUNT)
    )


def test_authorization_url(adapter):
    result = adapter.create_authorization_url(
        AuthorizationRequest(state="s", code_verifier="v" * 43)
    )
    params = {k: v[0] for k, v in parse_qs(urlparse(result.url).query).items()}
    assert result.url.startswith(f"{BASE}/oauth/authorize?")
    assert params["scope"] == SCOPE
    assert params["state"] == "s"
    assert params["code_challenge_method"] == "S256"
    assert result.scope == "profile,write:statuses,write:media"


class TestExchangeCode:
    def test_account(self, adapter, mastodon):
        mastodon.post(f"{BASE}/oauth/token", json={**TOKEN, "access_token": "new"})
        mastodon.get(
            f"{BASE}/oauth/userinfo", json={"preferred_username": "me", "name": "Me"}
        )
        account = adapter.exchange_code(CodeExchangeRequest(code="c"))
        assert (account.identifier, account.name) == ("me", "Me")
        assert account.token["access_token"] == "new"
        assert mastodon.calls[1].request.headers["Authorization"] == "Bearer new"

    def test_bad_code(self, adapter, mastodon):
        mastodon.post(
            f"{BASE}/oauth/token", status=400, json={"error": "invalid_grant"}
        )
        with pytest.raises(AuthenticationError):
            adapter.exchange_code(CodeExchangeRequest(code="c"))

    def test_missing_scope(self, adapter, mastodon):
        mastodon.post(f"{BASE}/oauth/token", json={**TOKEN, "scope": "profile"})
        with pytest.raises(AuthenticationError, match="write:media"):
            adapter.exchange_code(CodeExchangeRequest(code="c"))


class TestSendMessage:
    def test_posts_with_media(self, adapter, mastodon):
        mastodon.post(f"{BASE}/api/v2/media", json={"id": "m1"})
        mastodon.post(f"{BASE}/api/v1/statuses", json={"id": "p1"})
        send(adapter, attachments=(Attachment(b"img", "a.png", "image/png"),))
        status = json.loads(mastodon.calls[1].request.body)
        assert status == {"status": "Hello", "media_ids": ["m1"]}
        assert mastodon.calls[1].request.headers["Authorization"] == "Bearer access"

    def test_long_message_becomes_a_thread(self, adapter, mastodon):
        mastodon.post(f"{BASE}/api/v1/statuses", json={"id": "p1"})
        mastodon.post(f"{BASE}/api/v1/statuses", json={"id": "p2"})
        send(adapter, body="word " * 150)
        first, second = (json.loads(c.request.body) for c in mastodon.calls)
        assert first["status"].endswith("(1/2)")
        assert second["in_reply_to_id"] == "p1"

    def test_too_many_attachments(self, adapter):
        attachments = (Attachment(b"x", "a.png", "image/png"),) * 5
        with pytest.raises(InvalidParamsError, match="at most 4"):
            send(adapter, attachments=attachments)

    def test_needs_account(self, adapter):
        with pytest.raises(InvalidParamsError):
            adapter.send_message(SendRequest(Message(body="b")))

    @pytest.mark.parametrize(
        ("status", "error"),
        [(401, TokenInvalidError), (429, RateLimitedError), (500, UpstreamError)],
    )
    def test_failures(self, adapter, mastodon, status, error):
        mastodon.post(f"{BASE}/api/v1/statuses", status=status, json={"error": "x"})
        with pytest.raises(error):
            send(adapter)


def test_revoke(adapter, mastodon):
    mastodon.post(f"{BASE}/oauth/revoke", json={})
    adapter.revoke(RevokeRequest(ACCOUNT))
    body = parse_qs(mastodon.calls[0].request.body)
    assert body["token"] == ["access"]
    assert body["client_id"] == ["client"]


def test_split_message_fits_the_limit():
    posts = split_message("word " * 300)
    assert len(posts) > 1
    assert all(len(post) + 10 <= CHARACTER_LIMIT for post in posts)


def test_register_saves_credentials(config, mastodon):
    mastodon.post(
        "https://other.example/api/v1/apps",
        json={"client_id": "new", "client_secret": "s", "id": "9"},
    )
    args = ["--name", "RelaySMS", "--redirect-uri", "https://app/cb"]
    assert register.main([*args, "--base-url", "https://other.example/"]) == 0
    saved = json.loads((config / "credentials.json").read_text())
    assert saved == {
        "client_id": "new",
        "client_secret": "s",
        "redirect_uris": ["https://app/cb"],
        "base_url": "https://other.example",
    }
    assert MastodonAdapter().credentials.base_url == "https://other.example"
