"""
Zoho OAuth authentication — refresh-token flow.

Exchanges a stored refresh token for a short-lived access token
via the Zoho Accounts API.
"""

import logging
import os

import requests

logger = logging.getLogger(__name__)

# Default to US datacenter; change for .in, .eu, .com.au, etc.
ZOHO_ACCOUNTS_URL = "https://accounts.zoho.com/oauth/v2/token"


class ZohoAuthError(Exception):
    """Raised when Zoho OAuth token refresh fails."""
    pass


def get_access_token() -> str:
    """
    Exchange the refresh token for a new access token.

    Requires these environment variables:
        ZOHO_CLIENT_ID
        ZOHO_CLIENT_SECRET
        ZOHO_REFRESH_TOKEN

    Returns:
        The access token string.

    Raises:
        ZohoAuthError: If the token refresh fails.
        EnvironmentError: If required env vars are missing.
    """
    client_id = os.environ.get("ZOHO_CLIENT_ID")
    client_secret = os.environ.get("ZOHO_CLIENT_SECRET")
    refresh_token = os.environ.get("ZOHO_REFRESH_TOKEN")

    missing = []
    if not client_id:
        missing.append("ZOHO_CLIENT_ID")
    if not client_secret:
        missing.append("ZOHO_CLIENT_SECRET")
    if not refresh_token:
        missing.append("ZOHO_REFRESH_TOKEN")

    if missing:
        raise EnvironmentError(
            f"Missing required Zoho environment variable(s): {', '.join(missing)}"
        )

    logger.info("Refreshing Zoho access token...")

    resp = requests.post(
        ZOHO_ACCOUNTS_URL,
        data={
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )

    if resp.status_code != 200:
        raise ZohoAuthError(
            f"Zoho token refresh failed (HTTP {resp.status_code}): {resp.text}"
        )

    body = resp.json()
    access_token = body.get("access_token")

    if not access_token:
        error_msg = body.get("error", "unknown error")
        raise ZohoAuthError(
            f"Zoho token refresh returned no access_token: {error_msg}. "
            f"Full response: {body}"
        )

    logger.info("Zoho access token obtained successfully.")
    return access_token
