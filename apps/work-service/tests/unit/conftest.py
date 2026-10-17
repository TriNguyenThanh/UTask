from types import SimpleNamespace
import pytest

@pytest.fixture
def classroom_http(settings, monkeypatch):
    settings.CLASSROOM_BASE_URL = 'http://classroom:8000'
    settings.CLASSROOM_WORK_SERVICE_KEY = 'test-classroom-key'
    state = {'status': 200, 'data': {}, 'calls': []}

    def request(method, url, **kwargs):
        state['calls'].append((method, url, kwargs))
        if 'error' in state:
            raise state['error']
        return SimpleNamespace(status_code=state['status'], json=lambda: {'success': True, 'data': state['data']})
    monkeypatch.setattr('infrastructure.classroom.requests.request', request)
    return state
