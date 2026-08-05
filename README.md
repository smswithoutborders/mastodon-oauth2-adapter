# Mastodon OAuth2 Platform Adapter

This adapter provides a pluggable implementation for integrating Mastodon as a messaging platform. It is designed to work with [RelaySMS Publisher](https://github.com/smswithoutborders/RelaySMS-Publisher), enabling users to connect to Mastodon using OAuth2 authentication.

## Requirements

- **Python**: Version >=
  [3.8.10](https://www.python.org/downloads/release/python-3810/)
- **Python Virtual Environments**:
  [Documentation](https://docs.python.org/3/tutorial/venv.html)

## Dependencies

### On Ubuntu

Install the necessary system packages:

```bash
sudo apt install build-essential python3-dev
```

## Installation

1. **Create a virtual environment:**

   ```bash
   python3 -m venv venv
   ```

2. **Activate the virtual environment:**

   ```bash
   . venv/bin/activate
   ```

3. **Install the required Python packages:**

   ```bash
   pip install -r requirements.txt
   ```

## Configuration

### Step 1: Register Your Client Application

You can register a new client application using `cli.py`'s `register` command. This creates an OAuth2 application on your Mastodon server.

```bash
python3 cli.py register \
  -n "My Mastodon Client" \
  -r "https://example.com/callback/ https://localhost:8080/callback/" \
  -w "https://example.com" \
  -b "https://mastodon.social"
```

**Command Options:**

- `-n, --name`: Client application name
- `-r, --redirect-uris`: Redirect URIs (space-separated)
- `-w, --website`: Client website URL (optional)
- `-b, --base-url`: Mastodon instance to register with (optional, defaults to `https://mastodon.social`)
- `-i, --interactive`: Prompt for each field instead of requiring `-n`/`-r` as flags

Without `-i`, `--name` and `--redirect-uris` are required. With `-i`, missing fields (including `--website` and `--base-url`) are prompted for instead:

```bash
python3 cli.py register -i
```

> [!NOTE]
>
> The registration command automatically saves your client credentials to `credentials.json` in the project directory, including the `base_url` you registered against, so the adapter talks to the same instance at runtime.

#### Generated `credentials.json`

After successful registration, you'll get a `credentials.json` file with your client credentials:

```json
{
  "id": "12345",
  "name": "My Mastodon Client",
  "website": "https://example.com",
  "scopes": ["profile", "write:statuses"],
  "redirect_uris": ["https://example.com/callback/"],
  "vapid_key": "BM4h...XYZ",
  "redirect_uri": "https://example.com/callback/",
  "client_id": "abcd1234efgh5678",
  "client_secret": "wxyz9876abcd1234efgh5678ijkl9012",
  "client_secret_expires_at": 0,
  "base_url": "https://mastodon.social"
}
```

**Field Descriptions:**

- `id`: Unique identifier for your registered application
- `name`: The display name of your application
- `website`: Your application's website URL
- `scopes`: OAuth2 scopes your application can request (profile access and posting statuses)
- `redirect_uris`: Array of authorized redirect URLs for OAuth2 callbacks
- `vapid_key`: Vapid key for push notifications (if applicable)
- `redirect_uri`: Primary redirect URI (usually the first in `redirect_uris`)
- `client_id`: Your application's unique client identifier
- `client_secret`: Secret key for authenticating your application (keep this secure!)
- `client_secret_expires_at`: Expiration timestamp for the client secret (0 means no expiration)
- `base_url`: The Mastodon instance this client is registered with (optional; defaults to `https://mastodon.social` if omitted)
- `scope`: Optional override for the OAuth2 scopes requested at runtime (defaults to `["profile", "write:statuses"]` if omitted)

> [!NOTE]
>
> Credentials are loaded and validated by `config.py` into a typed `Credentials` object. Only `client_id`, `client_secret`, and `redirect_uris` are required; `base_url` and `scope` are optional overrides, letting the adapter target any Mastodon instance, not just `mastodon.social`.

### Step 2: Configure the Credentials File Path

Create or edit the `config.ini` file to specify the path to your credentials file:

```ini
[credentials]
path = ./credentials.json
```

## Testing

For exercising the OAuth2 flow without hand-crafting IPC JSON, use the interactive REPL in `tests/client.py`. The token is persisted to `tests/session.json`:

```bash
python -m tests.client
```

| Command        | Arguments                                | Description                                                    |
| -------------- | ----------------------------------------- | ---------------------------------------------------------------- |
| `auth_url`     | -                                          | Generate the OAuth2 authorization URL                            |
| `exchange`     | `<code>`                                   | Exchange an authorization code for a token, using the last `auth_url` session |
| `send_message` | `<message> [attachment_path ...]`          | Send a message using the stored token. Trailing arguments are read from disk and attached as media (up to 4). |
| `revoke`       | -                                          | Revoke the stored token                                          |
| `help`         | `[command]`                                | Show available commands, or detail for one command               |
| `quit`         | -                                          | Exit the client                                                  |

> [!WARNING]
>
> After revoking a token, the user will need to re-authenticate to use the adapter again.
