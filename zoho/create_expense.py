"""
Zoho Books — create an expense entry from an extraction result dict.
"""

import logging
import os
from datetime import date

import requests

from zoho.auth import get_access_token

logger = logging.getLogger(__name__)

# Default to US datacenter
ZOHO_BOOKS_BASE_URL = "https://www.zohoapis.in/books/v3"


class ZohoExpenseError(Exception):
    """Raised when creating a Zoho Books expense fails."""
    pass

def _get_or_create_vendor(vendor_name: str, access_token: str, org_id: str) -> str | None:
    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}",
        "X-com-zoho-books-organizationid": org_id,
        "Content-Type": "application/json",
    }
    # 1. Try to find the vendor
    search_url = f"{ZOHO_BOOKS_BASE_URL}/contacts"
    resp = requests.get(search_url, params={"contact_name": vendor_name, "contact_type": "vendor"}, headers=headers)
    if resp.status_code == 200:
        contacts = resp.json().get("contacts", [])
        if contacts:
            return contacts[0]["contact_id"]
    
    # 2. If not found, create it
    payload = {"contact_name": vendor_name, "contact_type": "vendor"}
    resp = requests.post(search_url, json=payload, headers=headers)
    if resp.status_code in (200, 201):
        return resp.json().get("contact", {}).get("contact_id")
    
    logger.warning("Failed to create vendor '%s': %s", vendor_name, resp.text)
    return None

def create_expense(extraction: dict, access_token: str | None = None) -> str:
    """
    Create an expense entry in Zoho Books from an extraction result.

    Args:
        extraction: dict with vendor_name, date, amount, currency,
                    invoice_number, gst_details.
        access_token: Optional pre-fetched access token. If None,
                      a new one is obtained via refresh-token flow.

    Returns:
        The created expense_id as a string.

    Raises:
        ZohoExpenseError: If the API call fails.
        EnvironmentError: If required env vars are missing.
    """
    org_id = os.environ.get("ZOHO_ORG_ID")
    account_id = os.environ.get("ZOHO_EXPENSE_ACCOUNT_ID")
    paid_through_id = os.environ.get("ZOHO_PAID_THROUGH_ACCOUNT_ID")

    missing = []
    if not org_id:
        missing.append("ZOHO_ORG_ID")
    if not account_id:
        missing.append("ZOHO_EXPENSE_ACCOUNT_ID")
    if not paid_through_id:
        missing.append("ZOHO_PAID_THROUGH_ACCOUNT_ID")
    if missing:
        raise EnvironmentError(
            f"Missing required Zoho environment variable(s): {', '.join(missing)}"
        )

    if access_token is None:
        access_token = get_access_token()

    # Build description from available fields
    desc_parts = []
    if extraction.get("invoice_number"):
        desc_parts.append(f"Invoice: {extraction['invoice_number']}")
    if extraction.get("gst_details"):
        desc_parts.append(f"GST: {extraction['gst_details']}")
    description = "Bill extraction — " + ", ".join(desc_parts) if desc_parts else "Bill extraction"

    # Determine expense date
    expense_date = extraction.get("date")
    if not expense_date:
        expense_date = date.today().isoformat()

    payload = {
        "date": expense_date,
        "amount": extraction.get("amount") or 0.0,
        "account_id": account_id,
        "paid_through_account_id": paid_through_id,
        "description": description,
        "reference_number": extraction.get("invoice_number") or "",
        "currency_code": extraction.get("currency") or "INR",
    }

    # Handle vendor creation/lookup
    vendor_name = extraction.get("vendor_name")
    if vendor_name:
        contact_id = _get_or_create_vendor(vendor_name, access_token, org_id)
        if contact_id:
            payload["vendor_id"] = contact_id

    url = f"{ZOHO_BOOKS_BASE_URL}/expenses"
    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}",
        "X-com-zoho-books-organizationid": org_id,
        "Content-Type": "application/json",
    }

    logger.info(
        "Creating Zoho expense: vendor=%s, amount=%s %s, date=%s",
        payload.get("vendor_name", "N/A"),
        payload.get("currency_code"),
        payload.get("amount"),
        payload.get("date"),
    )

    resp = requests.post(url, json=payload, headers=headers, timeout=30)

    if resp.status_code not in (200, 201):
        raise ZohoExpenseError(
            f"Zoho expense creation failed (HTTP {resp.status_code}): {resp.text}"
        )

    body = resp.json()

    if body.get("code") != 0:
        raise ZohoExpenseError(
            f"Zoho API error: code={body.get('code')}, message={body.get('message')}"
        )

    expense = body.get("expense", {})
    expense_id = expense.get("expense_id", "")

    if not expense_id:
        raise ZohoExpenseError(
            f"Zoho returned success but no expense_id. Response: {body}"
        )

    logger.info("Created Zoho expense: %s", expense_id)
    return expense_id
