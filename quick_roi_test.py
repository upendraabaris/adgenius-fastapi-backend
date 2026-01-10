#!/usr/bin/env python3
"""
Quick ROI calculation test
"""

def calculate_roi(spend, revenue):
    """Same function as in dashboard.py"""
    if spend == 0:
        return "0%"
    roi = ((revenue - spend) / spend) * 100
    sign = "+" if roi >= 0 else ""
    return f"{sign}{roi:.0f}%"

# Test cases
test_cases = [
    {"spend": 1000, "revenue": 1500, "expected": "+50%"},
    {"spend": 2000, "revenue": 800, "expected": "-60%"},
    {"spend": 1000, "revenue": 1000, "expected": "+0%"},
    {"spend": 0, "revenue": 500, "expected": "0%"},
    {"spend": 500, "revenue": 1000, "expected": "+100%"},
]

print("🧮 ROI Calculation Tests:")
print("=" * 40)

for i, test in enumerate(test_cases, 1):
    result = calculate_roi(test["spend"], test["revenue"])
    status = "✅" if result == test["expected"] else "❌"
    
    print(f"Test {i}: {status}")
    print(f"  Spend: ₹{test['spend']}")
    print(f"  Revenue: ₹{test['revenue']}")
    print(f"  Expected: {test['expected']}")
    print(f"  Got: {result}")
    print()

print("💡 Manual Verification Formula:")
print("ROI = ((Revenue - Spend) / Spend) × 100")
print("\nExample: Spend=₹1000, Revenue=₹1500")
print("ROI = ((1500 - 1000) / 1000) × 100 = +50%")