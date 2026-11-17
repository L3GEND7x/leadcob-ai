import httpx
import pytest
from datetime import date
from app.services.asaas_reconciliation import fetch_payment,verify_payment,PaymentUnavailable


def test_sandbox_payment_verification():
    data=dict(id='pay_123',externalReference='invoice-1',customer='cus_1',
              value=27,status='RECEIVED',deleted=False,refunds=[],
              paymentDate=date.today().isoformat(),billingType='PIX')
    def handler(req):
        assert str(req.url)=='https://api-sandbox.asaas.com/v3/payments/pay_123'
        assert req.headers['access_token']=='sandbox-test'
        assert req.method=='GET'
        return httpx.Response(200,json=data)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result=fetch_payment('pay_123','sandbox-test',client)
        args=dict(payment_id='pay_123',external_reference='invoice-1',customer_id='cus_1',amount_cents=2700)
        assert verify_payment(result,**args)
        for change in [dict(value=26.99),dict(status='CONFIRMED'),dict(customer='cus_2'),
                       dict(externalReference='other'),dict(deleted=True),dict(refunds=[{}])]:
            assert not verify_payment(result|change,**args)
        with pytest.raises(PaymentUnavailable):
            fetch_payment('../bad','sandbox-test',client)


def test_provider_failure():
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(401))) as client:
        with pytest.raises(PaymentUnavailable):
            fetch_payment('pay_123','sandbox-test',client)
