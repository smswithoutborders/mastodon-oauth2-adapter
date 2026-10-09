# Mastodon OAuth2 Platform Adapter

Lets [RelaySMS Publisher](https://github.com/smswithoutborders/RelaySMS-Publisher) users post to their Mastodon account. Long messages become a thread. Built with the [RelaySMS Adapter SDK](https://github.com/smswithoutborders/RelaySMS-Publisher/tree/main/sdk).

## Credentials

Register the client application with the Mastodon server once. `mastodon-register` writes `credentials.json` to `RELAYSMS_ADAPTER_CONFIG_DIR`, which on the Publisher is `data/platforms/config/<adapter id>/`.

```bash
RELAYSMS_ADAPTER_CONFIG_DIR=data/platforms/config/<adapter id> \
  venv/bin/mastodon-register --name RelaySMS \
  --redirect-uri https://example.com/callback --base-url https://mastodon.social
```

| Field | Required | Description |
|---|---|---|
| `client_id`, `client_secret` | yes | From the registration |
| `redirect_uris` | yes | The first is the default redirect |
| `base_url` | no | Mastodon server, `https://mastodon.social` by default |
| `scope` | no | Scopes to request, `["profile", "write:statuses", "write:media"]` by default |

## Develop

```bash
python3 -m venv venv
venv/bin/pip install -e '.[dev]'
venv/bin/pytest
```

To try it against a server, register with a local redirect; without `RELAYSMS_ADAPTER_CONFIG_DIR` the credentials go to `.relaysms/config/`. The [`relaysms-adapter`](https://github.com/smswithoutborders/RelaySMS-Publisher/tree/main/sdk#try-it) console then links an account and posts.

```bash
venv/bin/mastodon-register --name "RelaySMS dev" --redirect-uri http://localhost:8765/callback
venv/bin/relaysms-adapter link
venv/bin/relaysms-adapter send --attach ./photo.png
venv/bin/relaysms-adapter revoke
```
