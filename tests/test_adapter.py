# SPDX-License-Identifier: GPL-3.0-only

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import requests
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
    SetupRequest,
    TokenInvalidError,
    UpstreamError,
    manifest,
)
from relaysms_adapter_sdk.paths import CONFIG_DIR_ENV, STATE_DIR_ENV

from mastodon_oauth2_adapter import MastodonAdapter
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


SETUP = {"client_name": "RelaySMS", "redirect_uris": ["https://app/cb"]}


def setup(inputs):
    return MastodonAdapter.setup(SetupRequest(inputs))


def test_setup_registers_the_app(mastodon):
    mastodon.post(
        "https://other.example/api/v1/apps",
        json={"client_id": "new", "client_secret": "s", "id": "9"},
    )

    result = setup({**SETUP, "base_url": "https://other.example/"})

    assert result.settings == {
        "client_id": "new",
        "client_secret": "s",
        "redirect_uris": ["https://app/cb"],
        "base_url": "https://other.example",
    }
    sent = json.loads(mastodon.calls[0].request.body)
    assert sent.items() >= SETUP.items()


def test_setup_reports_a_refused_app(mastodon):
    mastodon.post(
        "https://mastodon.social/api/v1/apps",
        status=422,
        json={"error": "Validation failed: Redirect URI must be an absolute URI."},
    )

    with pytest.raises(InvalidParamsError, match="Redirect URI"):
        setup(SETUP)


def test_setup_reports_an_unreachable_server(mastodon):
    mastodon.post(
        "https://mastodon.social/api/v1/apps", body=requests.ConnectionError("down")
    )

    with pytest.raises(UpstreamError, match="couldn't be reached"):
        setup(SETUP)


def test_adapter_toml_declares_every_setting():
    declared = manifest.load(Path(__file__).parents[1]).config
    assert {field.name for field in declared} == {
        "client_id",
        "client_secret",
        "redirect_uris",
        "base_url",
        "scope",
    }
