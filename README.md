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

You can register a new client application using the CLI's `register` command. This creates an OAuth2 application on your Mastodon server.

```bash
python3 mastodon_cli.py register \
  -n "My Mastodon Client" \
  -r "https://example.com/callback/ https://localhost:8080/callback/" \
  -w "https://example.com"
```

**Command Options:**

- `-n, --name`: Client application name
- `-r, --redirect-uris`: Redirect URIs (space-separated)
- `-w, --website`: Client website URL (optional)

> [!NOTE]
>
> The registration command automatically saves your client credentials to `credentials.json` in the project directory.

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
  "client_secret_expires_at": 0
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

### Step 2: Configure the Credentials File Path

Create or edit the `config.ini` file to specify the path to your credentials file:

```ini
[credentials]
path = ./credentials.json
```

## Using the CLI

> [!NOTE]
>
> Use the `--help` flag with any command to see the available parameters and their descriptions.

### 1. **Generate Authorization URL**

Use the `auth-url` command to generate the OAuth2 authorization URL.

```bash
python3 mastodon_cli.py auth-url -o session.json
```

- `-o`: Save the output to `session.json`.

### 2. **Exchange Authorization Code**

Use the `exchange` command to exchange the authorization code for tokens and user info.

```bash
python3 mastodon_cli.py exchange -c auth_code -o session.json -f session.json
```

- `-c`: Authorization code.
- `-o`: Save the output to `session.json`.
- `-f`: Read parameters from `session.json`.

### 3. **Send a Message**

Use the `send-message` command to send a message using the adapter.

```bash
python3 mastodon_cli.py send-message -f session.json -m "Hello, Mastodon!" -o session.json
```

- `-f`: Read parameters from `session.json`.
- `-m`: Message to send.
- `-o`: Save the output to `session.json`.

### 4. **Revoke Token**

Use the `revoke` command to revoke the OAuth2 token and invalidate the user's session.

```bash
python3 mastodon_cli.py revoke -f session.json -o session.json
```

- `-f`: Read token from `session.json`.
- `-o`: Update the file by removing the revoked token.

> [!WARNING]
>
> After revoking a token, the user will need to re-authenticate to use the adapter again. The revoked token will be removed from the output file if specified.
