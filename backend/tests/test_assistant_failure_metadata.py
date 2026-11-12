from app.api.routes_assistant import failure_metadata


class ProviderError(Exception):
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body


def test_known_provider_code_is_safe_to_log():
    error = ProviderError(429, {'code': 'insufficient_quota', 'message': 'private provider detail'})
    assert failure_metadata(error) == {
        'type': 'ProviderError', 'status': 429, 'code': 'insufficient_quota',
    }
    error.body = {'code': 'project_spend_limit_exceeded'}
    assert failure_metadata(error)['code'] == 'project_spend_limit_exceeded'


def test_arbitrary_provider_data_is_not_logged():
    error = ProviderError(200, {'code': {'secret': 'sensitive'}, 'message': 'private provider detail'})
    assert failure_metadata(error) == {
        'type': 'ProviderError', 'status': None, 'code': None,
    }
    error.body = {'code': 'unexpected_or_user_supplied_value'}
    assert failure_metadata(error)['code'] is None
