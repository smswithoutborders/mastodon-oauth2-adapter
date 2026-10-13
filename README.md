# Mastodon OAuth2 Platform Adapter

Lets [RelaySMS Publisher](https://github.com/smswithoutborders/RelaySMS-Publisher) users post to their Mastodon account. Long messages become a thread. Built with the [RelaySMS Adapter SDK](https://github.com/smswithoutborders/RelaySMS-Publisher/tree/main/sdk).

## Settings

Setup registers the app with the Mastodon server and saves the client ID and secret it gets back. Its inputs and settings are described in [adapter.toml](adapter.toml). On a Publisher, an administrator sets them with its [settings commands](https://github.com/smswithoutborders/RelaySMS-Publisher/blob/main/docs/platforms.md#settings) or REST API.

## Develop

```bash
python3 -m venv venv
venv/bin/pip install -e '.[dev]'
venv/bin/pytest
```

To try it against a server, register with a local redirect, then link an account and post with the [`relaysms-adapter`](https://github.com/smswithoutborders/RelaySMS-Publisher/tree/main/sdk#try-it) console:

```bash
venv/bin/relaysms-adapter setup --input client_name="RelaySMS dev" \
  --input redirect_uris=http://localhost:8765/callback
venv/bin/relaysms-adapter link
venv/bin/relaysms-adapter send --attach ./photo.png
venv/bin/relaysms-adapter revoke
```
