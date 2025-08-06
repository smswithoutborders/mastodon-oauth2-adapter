"""
This program is free software: you can redistribute it under the terms
of the GNU General Public License, v. 3.0. If a copy of the GNU General
Public License was not distributed with this file, see <https://www.gnu.org/licenses/>.
"""

import json
import click
from protocol_interfaces import BaseProtocolInterface
from adapter import MastodonOAuth2Adapter, save_credentials, register_client


def print_table(title, data: dict):
    divider = "=" * 40
    print(f"\n{divider}\n{title}\n{divider}")
    for k, v in data.items():
        print(
            f"{k:20}: {json.dumps(v, indent=2) if isinstance(v, (dict, list)) else v}"
        )
    print(divider)


@click.group
def cli():
    """Mastodon OAuth2 Adapter CLI."""


@cli.command("register")
@click.option("-n", "--name", required=False, help="Client application name")
@click.option(
    "-r", "--redirect-uris", required=False, help="Redirect URIs (space-separated)"
)
@click.option("-w", "--website", default=None, help="Client website URL")
def register(name, redirect_uris, website):
    """Register a new client application with a Mastodon server."""

    if not name:
        name = click.prompt("Client application name", type=str)

    if not redirect_uris:
        redirect_uris = click.prompt("Redirect URIs (space-separated)", type=str)

    try:
        credentials = register_client(
            client_name=name, redirect_uris=redirect_uris, website=website
        )

        adapter = BaseProtocolInterface()

        save_credentials(adapter.config, credentials)
        print_table("Client Registration Successful", credentials)

    except Exception as err:
        print("Registration failed:", err)
        print(f"Registration failed: {err}")


@cli.command("auth-url")
@click.option(
    "-p",
    "--pkce",
    is_flag=True,
    default=False,
    help="Auto-generate PKCE code verifier.",
)
@click.option("-r", "--redirect", default=None, help="Redirect URI.")
@click.option("-s", "--state", default=None, help="OAuth2 state parameter.")
@click.option("-o", "--output", default=None, help="File to store the output as JSON.")
def auth_url(pkce, redirect, state, output):
    """Get the OAuth2 authorization URL."""
    adapter = MastodonOAuth2Adapter()
    result = adapter.get_authorization_url(
        autogenerate_code_verifier=pkce,
        redirect_url=redirect,
        state=state,
    )
    print_table("Authorization URL Result", result)
    if output:
        with open(output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"Output saved to {output}")


@cli.command("exchange")
@click.option("-c", "--code", required=True, help="Authorization code")
@click.option("-v", "--verifier", help="PKCE code verifier")
@click.option("-r", "--redirect", help="Redirect URI")
@click.option(
    "-o", "--output", default=None, help="File to read/write the output as JSON."
)
@click.option(
    "-f", "--input-file", default=None, help="File to read parameters from as JSON."
)
def exchange(code, verifier, redirect, output, input_file):
    """Exchange code and fetch userinfo."""
    request_identifier = None
    if input_file:
        try:
            with open(input_file, "r", encoding="utf-8") as f:
                params = json.load(f)
            code = code or params.get("authorization_code")
            verifier = verifier or params.get("code_verifier")
            redirect = redirect or params.get("redirect_uri")
            request_identifier = params.get("request_identifier")
        except FileNotFoundError:
            print(f"Input file {input_file} not found.")
            return

    adapter = MastodonOAuth2Adapter()
    result = adapter.exchange_code_and_fetch_user_info(
        code=code,
        code_verifier=verifier,
        redirect_url=redirect,
        request_identifier=request_identifier,
    )
    print_table("Token Result", result.get("token", {}))
    print_table("User Info", result.get("userinfo", {}))

    if output:
        try:
            with open(output, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except FileNotFoundError:
            existing_data = {}

        existing_data.update(
            {"token": result.get("token", {}), "userinfo": result.get("userinfo", {})}
        )

        with open(output, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, indent=2)
        print(f"Output saved to {output}")


@cli.command("send-message")
@click.option("-f", "--token-file", required=True, help="File containing token JSON.")
@click.option("-m", "--message", required=True, help="Message to send.")
@click.option(
    "-o", "--output", default=None, help="File to save refreshed token if different."
)
def send_message(token_file, message, output):
    """Send a message using the Mastodon OAuth2 Adapter."""
    try:
        with open(token_file, "r", encoding="utf-8") as f:
            token = json.load(f).get("token")
            if not token:
                print(f"Token key not found in {token_file}.")
                return
    except FileNotFoundError:
        print(f"Token file {token_file} not found.")
        return

    adapter = MastodonOAuth2Adapter()
    try:
        result = adapter.send_message(token=token, message=message)
        print_table("Send Message Result", result)

        refreshed_token = result.get("refreshed_token")
        if output and refreshed_token != token:
            try:
                with open(output, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            except FileNotFoundError:
                existing_data = {}

            existing_data.update({"token": refreshed_token})

            with open(output, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=2)
            print(f"Refreshed token saved to {output}")
    except Exception as err:
        print(f"Failed to send message: {err}")


@cli.command("revoke")
@click.option("-f", "--token-file", required=True, help="File containing token JSON.")
@click.option(
    "-o", "--output", default=None, help="File to update after token revocation."
)
def revoke(token_file, output):
    """Revoke the OAuth2 token."""
    try:
        with open(token_file, "r", encoding="utf-8") as f:
            token = json.load(f).get("token")
            if not token:
                print(f"Token key not found in {token_file}.")
                return
    except FileNotFoundError:
        print(f"Token file {token_file} not found.")
        return

    adapter = MastodonOAuth2Adapter()
    try:
        result = adapter.revoke_token(token=token)
        print_table("Revoke Token Result", {"success": result})

        if output:
            try:
                with open(output, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            except FileNotFoundError:
                existing_data = {}

            existing_data.pop("token", None)

            with open(output, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=2)
            print(f"Token removed from {output}")
    except Exception as err:
        print(f"Failed to revoke token: {err}")


if __name__ == "__main__":
    cli()
