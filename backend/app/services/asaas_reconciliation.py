"""Read-only sandbox adapter. Never issues charges or recognizes payment locally."""
import re
from decimal import Decimal, InvalidOperation
from datetime import date
import httpx

BASE = 'https://api-sandbox.asaas.com/v3'


class PaymentUnavailable(Exception):
    pass


def fetch_payment(payment_id, api_key, client=None):
    if not re.fullmatch(r'pay_[A-Za-z0-9_-]{1,100}', payment_id) or not api_key:
        raise PaymentUnavailable('Consulta indisponível.')
    own=client is None
    client=client or httpx.Client(timeout=10,follow_redirects=False,trust_env=False)
    try:
        response=client.get(BASE+'/payments/'+payment_id,headers={
            'access_token':api_key,'Accept':'application/json','User-Agent':'LeadCobAI/1.0'})
        response.raise_for_status()
        data=response.json(parse_float=Decimal)
        if not isinstance(data,dict) or data.get('id')!=payment_id:
            raise ValueError('unexpected response')
        return data
    except (httpx.HTTPError,ValueError) as exc:
        raise PaymentUnavailable('Consulta ao provedor indisponível.') from exc
    finally:
        if own:
            client.close()


def verify_payment(data, *, payment_id, external_reference, customer_id, amount_cents):
    """Fail closed: exact gross amount, binding, received status and no refunds."""
    try:
        amount=Decimal(str(data['value']))
        if not amount.is_finite() or amount*100!=amount_cents:
            return False
        paid=date.fromisoformat(data['paymentDate'])
        return (data['id']==payment_id and data['externalReference']==external_reference
                and data['customer']==customer_id and data['status']=='RECEIVED'
                and data.get('deleted') is False and not data.get('refunds')
                and paid<=date.today() and data.get('billingType') in {'PIX','BOLETO','CREDIT_CARD'})
    except (KeyError,TypeError,ValueError,InvalidOperation):
        return False
