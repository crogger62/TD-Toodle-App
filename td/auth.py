import json
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
import sys

import requests


AUTH_BASE = "https://api.toodledo.com/3/account"
TASKS_SCOPE = "basic tasks write"
DEFAULT_REDIRECT_PORT = 8765

ENV_CLIENT_ID = "TOODLEDO_CLIENT_ID"
ENV_CLIENT_SECRET = "TOODLEDO_CLIENT_SECRET"
ENV_ACCESS_TOKEN = "TOODLEDO_ACCESS_TOKEN"
ENV_REFRESH_TOKEN = "TOODLEDO_REFRESH_TOKEN"
ENV_EXPIRES_AT = "TOODLEDO_EXPIRES_AT"
ENV_REDIRECT_PORT = "TOODLEDO_REDIRECT_PORT"


class OAuthResult:
    def __init__(self) -> None:
        self.code = None
        self.state = None
        self.error = None


class OAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        result: OAuthResult = self.server.oauth_result
        result.code = (params.get("code") or [None])[0]
        result.state = (params.get("state") or [None])[0]
        result.error = (params.get("error") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h1>Login complete</h1>"
            b"<p>You may close this window.</p></body></html>"
        )
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, format, *args):  # noqa: A002
        return


def _get_redirect_port() -> int:
    value = os.getenv(ENV_REDIRECT_PORT)
    if value:
        try:
            port = int(value)
        except ValueError as exc:
            raise ValueError(f"{ENV_REDIRECT_PORT} must be an integer") from exc
        if not (1 <= port <= 65535):
            raise ValueError(f"{ENV_REDIRECT_PORT} must be between 1 and 65535")
        return port
    return DEFAULT_REDIRECT_PORT


def _build_redirect_uri(port: int) -> str:
    return f"http://127.0.0.1:{port}/"


def _require_client_credentials() -> tuple[str, str]:
    client_id = os.getenv(ENV_CLIENT_ID)
    client_secret = os.getenv(ENV_CLIENT_SECRET)
    if not client_id or not client_secret:
        raise RuntimeError(
            f"Missing client credentials. Set {ENV_CLIENT_ID} and {ENV_CLIENT_SECRET}."
        )
    return client_id, client_secret


def _authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": TASKS_SCOPE,
        "state": state,
    }
    return f"{AUTH_BASE}/authorize.php?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"


def _exchange_token(
    client_id: str, client_secret: str, code: str, redirect_uri: str
) -> dict:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }
    response = requests.post(
        f"{AUTH_BASE}/token.php",
        data=data,
        auth=(client_id, client_secret),
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    _raise_if_error(payload)
    return payload


def _refresh_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    response = requests.post(
        f"{AUTH_BASE}/token.php",
        data=data,
        auth=(client_id, client_secret),
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    _raise_if_error(payload)
    return payload


def _raise_if_error(payload: dict) -> None:
    if "errorCode" in payload and payload.get("errorCode"):
        message = payload.get("errorDesc") or payload.get("error")
        raise RuntimeError(f"Toodledo API error {payload.get('errorCode')}: {message}")


def _run_oauth_flow(client_id: str, client_secret: str) -> dict:
    port = _get_redirect_port()
    redirect_uri = _build_redirect_uri(port)
    state = secrets.token_urlsafe(16)
    httpd = HTTPServer(("127.0.0.1", port), OAuthHandler)
    httpd.oauth_result = OAuthResult()

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    auth_url = _authorize_url(client_id, redirect_uri, state)
    print("Opening browser for login...")
    print(auth_url)
    webbrowser.open(auth_url)

    start = time.time()
    timeout_seconds = 300
    while thread.is_alive() and time.time() - start < timeout_seconds:
        time.sleep(0.1)

    timed_out = time.time() - start >= timeout_seconds
    if thread.is_alive():
        httpd.shutdown()
        thread.join(timeout=5)
    httpd.server_close()

    result = httpd.oauth_result
    if timed_out and not result.code:
        raise RuntimeError("Timed out waiting for authorization response.")
    if result.error:
        raise RuntimeError(f"Authorization error: {result.error}")
    if not result.code:
        raise RuntimeError("Authorization code not received.")
    if result.state != state:
        raise RuntimeError("Invalid OAuth state returned.")

    return _exchange_token(client_id, client_secret, result.code, redirect_uri)


def _normalize_token_response(payload: dict) -> dict:
    expires_in = int(payload.get("expires_in") or 0)
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    scope = payload.get("scope")
    if not access_token or not refresh_token or not expires_in:
        raise RuntimeError("Token response missing required fields.")
    tokens = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": int(time.time()) + expires_in,
    }
    if scope:
        tokens["scope"] = scope
    return tokens


def _token_storage_dir() -> str:
    if os.name == "nt":
        base = os.getenv("APPDATA")
        if not base:
            base = os.path.expanduser("~\\AppData\\Roaming")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.getenv("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "toodledo-cli")


def _token_storage_path() -> str:
    return os.path.join(_token_storage_dir(), "tokens.json")


def token_storage_path() -> str:
    return _token_storage_path()


def delete_token_file() -> bool:
    path = _token_storage_path()
    if not os.path.exists(path):
        return False
    os.remove(path)
    return True


def load_tokens_from_file() -> Optional[dict]:
    path = _token_storage_path()
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    expires_at = data.get("expires_at")
    scope = data.get("scope")
    if not access_token or not refresh_token or not expires_at:
        raise RuntimeError("Token file missing required fields.")
    try:
        expires_at_int = int(expires_at)
    except ValueError as exc:
        raise ValueError("Token file expires_at must be epoch seconds.") from exc
    tokens = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at_int,
    }
    if scope:
        tokens["scope"] = scope
    return tokens


def save_tokens_to_file(tokens: dict) -> None:
    path = _token_storage_path()
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(tokens, handle, indent=2, sort_keys=True)
    os.replace(temp_path, path)
    if os.name != "nt":
        os.chmod(path, 0o600)


def _try_save_tokens(tokens: dict) -> None:
    try:
        save_tokens_to_file(tokens)
    except Exception as exc:  # noqa: BLE001
        print(f"Warning: failed to save tokens to disk: {exc}")


def load_tokens_from_env() -> Optional[dict]:
    access_token = os.getenv(ENV_ACCESS_TOKEN)
    refresh_token = os.getenv(ENV_REFRESH_TOKEN)
    expires_at = os.getenv(ENV_EXPIRES_AT)
    if not access_token or not refresh_token or not expires_at:
        return None
    try:
        expires_at_int = int(expires_at)
    except ValueError as exc:
        raise ValueError(f"{ENV_EXPIRES_AT} must be epoch seconds.") from exc
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at_int,
    }


def ensure_tokens() -> dict:
    tokens = load_tokens_from_env()
    if tokens is None:
        tokens = load_tokens_from_file()
    if tokens is None:
        client_id, client_secret = _require_client_credentials()
        payload = _run_oauth_flow(client_id, client_secret)
        tokens = _normalize_token_response(payload)
        _try_save_tokens(tokens)
        return tokens

    if tokens["expires_at"] - time.time() <= 300:
        client_id, client_secret = _require_client_credentials()
        payload = _refresh_token(
            client_id, client_secret, tokens["refresh_token"]
        )
        tokens = _normalize_token_response(payload)
        _try_save_tokens(tokens)
    return tokens


def refresh_on_failure(tokens: dict, error: Exception) -> dict:
    if not tokens.get("refresh_token"):
        raise error
    client_id, client_secret = _require_client_credentials()
    payload = _refresh_token(client_id, client_secret, tokens["refresh_token"])
    tokens = _normalize_token_response(payload)
    _try_save_tokens(tokens)
    return tokens


def format_env_exports(tokens: dict) -> str:
    return json.dumps(
        {
            ENV_ACCESS_TOKEN: tokens["access_token"],
            ENV_REFRESH_TOKEN: tokens["refresh_token"],
            ENV_EXPIRES_AT: tokens["expires_at"],
        },
        indent=2,
        sort_keys=True,
    )
