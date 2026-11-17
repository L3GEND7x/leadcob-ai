from datetime import date, timedelta
import json
import httpx
import pytest
from app.services.asaas_sandbox_issuance import issue_charge
from app.services.asaas_reconciliation import PaymentUnavailable


def test_issue_charge_exact_payload_and_no_retry():
    due = (date.today() + timedelta(days=1)).isoformat()
    args = dict(customer_id="cus_1", billing_type="PIX", amount_cents=2701,
                due_date=due, reference="leadcob-sandbox-org-1-invoice-2", api_key="test")
    calls = []
    def handler(req):
        calls.append(req)
        assert str(req.url) == "https://api-sandbox.asaas.com/v3/payments"
        assert req.method == "POST"
        data = json.loads(req.content)
        assert data["value"] == 27.01
        return httpx.Response(200, json=data | dict(id="pay_1", deleted=False, status="PENDING"))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert issue_charge(**args, client=client) == "pay_1"
    assert len(calls) == 1
    def timeout(req):
        calls.append(req)
        raise httpx.ReadTimeout("uncertain")
    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(PaymentUnavailable):
            issue_charge(**args, client=client)
    assert len(calls) == 2
