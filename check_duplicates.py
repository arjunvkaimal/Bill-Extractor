import os
import requests
from dotenv import load_dotenv
from collections import defaultdict
from zoho.auth import get_access_token
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def find_duplicates():
    load_dotenv(override=True)
    org_id = os.environ.get("ZOHO_ORG_ID")
    if not org_id:
        print("Missing ZOHO_ORG_ID in .env")
        return
        
    try:
        token = get_access_token()
    except Exception as e:
        print(f"Auth failed: {e}")
        return

    url = "https://www.zohoapis.in/books/v3/expenses"
    headers = {
        "Authorization": f"Zoho-oauthtoken {token}",
        "X-com-zoho-books-organizationid": org_id,
    }

    print("Fetching expenses from Zoho Books...")
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"Failed to fetch expenses: {resp.text}")
        return

    expenses = resp.json().get("expenses", [])
    
    # Group by (vendor_name, date, amount)
    grouped = defaultdict(list)
    for exp in expenses:
        key = (exp.get("vendor_name"), exp.get("date"), exp.get("total"))
        grouped[key].append(exp)

    duplicates_found = False
    print("\n--- Duplicate Analysis ---")
    for key, exps in grouped.items():
        if len(exps) > 1:
            duplicates_found = True
            print(f"\nPotential Duplicate Group: Vendor: {key[0]} | Date: {key[1]} | Amount: {key[2]}")
            for exp in exps:
                print(f"  - Expense ID: {exp.get('expense_id')} | Created At: {exp.get('created_time')}")

    if not duplicates_found:
        print("\nNo duplicates found!")

if __name__ == "__main__":
    find_duplicates()
