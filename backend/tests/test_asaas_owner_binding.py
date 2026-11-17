from app.api.routes_commercial_admin import SandboxBindingIn, sandbox_match, sandbox_reference
import pytest
from pydantic import ValidationError


def test_sandbox_binding_validation():
    payload = SandboxBindingIn(customer_id='cus_1', payment_id='pay_1')
    reference = sandbox_reference(10, 20)
    assert reference != sandbox_reference(11, 20)
    data = dict(id='pay_1', customer='cus_1', externalReference=reference,
                value=27, deleted=False, refunds=[], billingType='PIX', status='PENDING')
    assert sandbox_match(data, payload, reference, 2700)
    for change in (
        dict(value=26.99), dict(value='NaN'), dict(customer='cus_2'),
        dict(id='pay_2'), dict(externalReference='other'), dict(deleted=True),
        dict(refunds=[{}]), dict(billingType='CREDIT_CARD'), dict(status='REFUNDED'),
    ):
        assert not sandbox_match(data | change, payload, reference, 2700)
    with pytest.raises(ValidationError):
        SandboxBindingIn(customer_id='cus_1', payment_id='../bad')
    with pytest.raises(ValidationError):
        SandboxBindingIn(customer_id='cus_1', payment_id='pay_1', amount_cents=1)
