from datetime import date
from app.services.asaas_sandbox_observations import classify, cents

def test_classification():
    binding = dict(payment_id="pay_1", customer_id="cus_1", external_reference="ref", amount_cents=2700)
    data = dict(id="pay_1", customer="cus_1", externalReference="ref", value="27.00",
                netValue="26.10", billingType="PIX", deleted=False, refunds=[],
                status="RECEIVED", paymentDate=date.today().isoformat())
    assert classify(data, binding) == dict(outcome="sandbox_received", provider_status="RECEIVED",
                                          gross_cents=2700, net_cents=2610)
    for changes, expected in [
        (dict(value="26.99"), "divergence"),
        (dict(customer="cus_2"), "divergence"),
        (dict(status="CHARGEBACK_DISPUTE"), "chargeback_review"),
        (dict(status="REFUNDED"), "refund_review"),
        (dict(refunds=[{}]), "refund_review"),
        (dict(status="CONFIRMED"), "not_received"),
        (dict(netValue=None), "financial_review"),
        (dict(netValue="28.00"), "financial_review"),
        (dict(deleted=True), "deleted_review"),
    ]:
        assert classify(data | changes, binding)["outcome"] == expected
    assert cents("NaN") is None
    assert cents("27.001") is None
    assert cents("1e99") is None
