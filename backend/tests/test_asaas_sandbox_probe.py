from datetime import date
import httpx
from app.services.asaas_sandbox_probe import probe


def test_probe_uses_only_sandbox_get_and_detects_divergence():
    requests = []
    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        assert str(request.url) == "https://api-sandbox.asaas.com/v3/payments/pay_test"
        return httpx.Response(200, json=dict(id="pay_test", customer="cus_test",
            externalReference="ref", value=27, netValue=26, deleted=False,
            billingType="PIX", status="RECEIVED", paymentDate=date.today().isoformat()))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = probe("pay_test", "cus_test", "ref", 2700, "test-key", client)
        assert result["outcome"] == "sandbox_received"
        assert result["production_ready"] is False
        assert probe("pay_test", "cus_test", "ref", 2701, "test-key", client)["binding_matches"] is False
    assert len(requests) == 2
