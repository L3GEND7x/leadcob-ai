"""Operator-run probe against an existing sandbox payment; never creates charges."""
import argparse
import json
import os
from app.services.asaas_reconciliation import fetch_payment, PaymentUnavailable
from app.services.asaas_sandbox_observations import classify


def probe(payment_id, customer_id, reference, amount_cents, api_key, client=None):
    if not api_key or amount_cents <= 0:
        raise ValueError("Missing sandbox configuration")
    data = fetch_payment(payment_id, api_key, client)
    result = classify(data, {"payment_id": payment_id, "customer_id": customer_id,
                            "external_reference": reference, "amount_cents": amount_cents})
    return {"environment": "sandbox", **result,
            "binding_matches": result["outcome"] != "divergence",
            "production_ready": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payment-id", required=True)
    parser.add_argument("--customer-id", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--amount-cents", required=True, type=int)
    args = parser.parse_args()
    try:
        result = probe(args.payment_id, args.customer_id, args.reference,
                       args.amount_cents, os.environ.get("ASAAS_SANDBOX_API_KEY", ""))
    except (PaymentUnavailable, ValueError):
        print(json.dumps({"environment": "sandbox", "probe": "failed"}))
        return 1
    print(json.dumps(result))
    return 0 if result["binding_matches"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
