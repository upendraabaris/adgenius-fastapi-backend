"""
Razorpay Auto-Debit Webhook Simulator
Run this script to simulate an automatic monthly recurring charge (next month billing cycle).

Usage:
    python simulate_auto_debit.py <subscription_id>

Example:
    python simulate_auto_debit.py sub_test_xxxxxx
"""
import sys
import json
import requests

def simulate(subscription_id: str):
    url = "http://localhost:8000/api/payments/webhook"
    
    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": "local_mock_signature" # Bypasses webhook secret check locally
    }
    
    payload = {
        "entity": "event",
        "account_id": "acc_BF12345",
        "event": "subscription.charged",
        "contains": ["subscription", "payment"],
        "payload": {
            "subscription": {
                "entity": {
                    "id": subscription_id,
                    "plan_id": "plan_starter_placeholder",
                    "status": "active",
                    "quantity": 1,
                    "total_count": 12,
                    "paid_count": 2,
                    "notes": {
                        "plan": "starter"
                    }
                }
            },
            "payment": {
                "entity": {
                    "id": "pay_mock_recurring_123",
                    "amount": 1000,
                    "currency": "INR",
                    "status": "captured",
                    "order_id": "order_mock_recurring_123"
                }
            }
        },
        "created_at": 1618917822
    }
    
    print(f"Sending simulated 'subscription.charged' webhook for: {subscription_id}...")
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            print("Success! Server responded with:")
            print(json.dumps(response.json(), indent=2))
            print("\nThe user's active subscription expiry has been extended by 30 days and AI credits replenished!")
        else:
            print(f"Failed: Status Code {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Connection Error: Make sure your FastAPI backend server is running on http://localhost:8000\nError: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Error: Missing subscription_id parameter!")
        print("Usage: python simulate_auto_debit.py <subscription_id>")
        sys.exit(1)
        
    sub_id = sys.argv[1]
    simulate(sub_id)
