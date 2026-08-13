# SPDX-License-Identifier: GPL-3.0-only
"""
CLI for platform-specific administrative tasks that aren't part of the
adapter's runtime OAuth2 interface, namely registering a client application
with a Mastodon server.
"""

from typing import Any, Dict, List, Optional

import click
import requests

from config import DEFAULT_BASE_URL, DEFAULT_SCOPE, save_credentials
from logutils import get_logger
from protocol_interfaces import BaseProtocolInterface

logger = get_logger(__name__)


def register_client(
    client_name: str,
    redirect_uris: List[str],
    website: Optional[str] = None,
    base_url: str = DEFAULT_BASE_URL,
) -> Dict[str, Any]:
    """Register a new client application with a Mastodon server."""
    register_uri = f"{base_url}/api/v1/apps"

    logger.info("Registering client with server: %s", register_uri)

    registration_data = {
        "client_name": client_name,
        "redirect_uris": redirect_uris,
        "scopes": " ".join(DEFAULT_SCOPE),
    }

    if website:
        registration_data["website"] = website

    try:
        response = requests.post(register_uri, json=registration_data, timeout=30)
        response.raise_for_status()

        result = response.json()

        logger.debug("Client registration response: %s", result)
        logger.info("Client registration successful")
        return result

    except requests.exceptions.RequestException:
        logger.exception("Failed to register client.")
        raise


@click.group
def cli():
    """Mastodon OAuth2 Adapter CLI."""


@cli.command("register")
@click.option("-n", "--name", default=None, help="Client application name")
@click.option(
    "-r", "--redirect-uris", default=None, help="Redirect URIs (space-separated)"
)
@click.option("-w", "--website", default=None, help="Client website URL")
@click.option(
    "-b",
    "--base-url",
    default=DEFAULT_BASE_URL,
    show_default=True,
    help="Mastodon instance base URL to register the client with.",
)
@click.option(
    "-i",
    "--interactive",
    is_flag=True,
    default=False,
    help="Prompt for each field instead of requiring them as flags.",
)
def register(name, redirect_uris, website, base_url, interactive):
    """Register a new client application with a Mastodon server."""

    if interactive:
        name = name or click.prompt("Client application name", type=str)
        redirect_uris = redirect_uris or click.prompt(
            "Redirect URIs (space-separated)", type=str
        )
        website = (
            website
            or click.prompt(
                "Client website URL (optional)",
                type=str,
                default="",
                show_default=False,
            )
            or None
        )
        base_url = click.prompt(
            "Mastodon instance base URL", type=str, default=base_url
        )
    else:
        missing = [
            flag
            for flag, value in (
                ("-n/--name", name),
                ("-r/--redirect-uris", redirect_uris),
            )
            if not value
        ]
        if missing:
            raise click.UsageError(
                f"Missing required option(s): {', '.join(missing)}. "
                "Pass them directly, or use -i/--interactive to be prompted."
            )

    try:
        credentials = register_client(
            client_name=name,
            redirect_uris=redirect_uris.split(),
            website=website,
            base_url=base_url,
        )
        credentials["base_url"] = base_url

        adapter = BaseProtocolInterface()

        save_credentials(adapter.config, credentials)

        divider = "=" * 40
        print(f"\n{divider}\nClient Registration Successful\n{divider}")
        for k, v in credentials.items():
            print(f"{k:20}: {v}")
        print(divider)

    except Exception as err:
        print(f"Registration failed: {err}")


if __name__ == "__main__":
    cli()
