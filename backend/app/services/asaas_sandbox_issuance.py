"""Sandbox charge creation; callers MUST persist reservation before calling."""
from datetime import date
from decimal import Decimal, InvalidOperation
import re
import httpx
from app.services.asaas_reconciliation import BASE, PaymentUnavailable


def issue_charge(*, customer_id, billing_type, amount_cents, due_date, reference, api_key, client=None):
    if (not api_key or not re.fullmatch(r"cus_[A-Za-z0-9_-]{1,100}", customer_id)
            or billing_type not in {"PIX", "BOLETO"} or type(amount_cents) is not int
            or not 0 < amount_cents <= 100000000
            or date.fromisoformat(due_date) < date.today()
            or not re.fullmatch(r"leadcob-sandbox-org-[0-9]+-invoice-[0-9]+", reference)):
        raise ValueError("Invalid sandbox issuance input")
    # Serialize exact decimal as JSON number, without binary float conversion.
    import json
    fields = dict(customer=customer_id, billingType=billing_type, dueDate=due_date,
                  externalReference=reference)
    body = json.dumps(fields)[:-1] + ',"value":' + format(Decimal(amount_cents)/100, ".2f") + "}"
    own = client is None
    client = client or httpx.Client(timeout=10, follow_redirects=False, trust_env=False)
    try:
        response = client.post(BASE + "/payments", content=body, headers={
            "access_token": api_key, "Content-Type": "application/json",
            "Accept": "application/json", "User-Agent": "LeadCobAI/1.0"})
        response.raise_for_status()
        data = response.json(parse_float=Decimal)
        if (not isinstance(data, dict) or not isinstance(data.get("id"), str)
                or not re.fullmatch(r"pay_[A-Za-z0-9_-]{1,100}", data["id"])
                or data.get("customer") != customer_id or data.get("billingType") != billing_type
                or data.get("externalReference") != reference or data.get("dueDate") != due_date
                or Decimal(str(data.get("value"))) * 100 != amount_cents
                or data.get("deleted") is not False or data.get("status") != "PENDING"):
            raise ValueError("Unexpected provider response")
        return data["id"]
    except (httpx.HTTPError, ValueError, InvalidOperation) as exc:
        raise PaymentUnavailable("Resultado incerto; não repetir emissão.") from exc
    finally:
        if own:
            client.close()
