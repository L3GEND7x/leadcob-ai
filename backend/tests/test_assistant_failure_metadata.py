from app.api.routes_assistant import failure_metadata


class ProviderError(Exception):
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body


def test_known_provider_code_is_safe_to_log():
    error = ProviderError(429, {'code': 'insufficient_quota', 'message': 'private provider detail'})
    assert failure_metadata(error) == {
        'type': 'ProviderError', 'status': 429, 'code': 'insufficient_quota', 'provider_type': None,
    }
    error.body = {'code': 'project_spend_limit_exceeded'}
    assert failure_metadata(error)['code'] == 'project_spend_limit_exceeded'
    error.body = {'code': 'credit_balance_exhausted', 'type': 'insufficient_quota'}
    assert failure_metadata(error)['code'] == 'credit_balance_exhausted'
    assert failure_metadata(error)['provider_type'] == 'insufficient_quota'


def test_arbitrary_provider_data_is_not_logged():
    error = ProviderError(200, {'code': {'secret': 'sensitive'}, 'message': 'private provider detail'})
    assert failure_metadata(error) == {
        'type': 'ProviderError', 'status': None, 'code': None, 'provider_type': None,
    }
    error.body = {'code': 'unexpected_or_user_supplied_value', 'type': 'private_or_unexpected_value'}
    assert failure_metadata(error)['code'] is None
    assert failure_metadata(error)['provider_type'] is None
