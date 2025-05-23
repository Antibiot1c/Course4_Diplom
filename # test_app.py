# test_app.py
import pytest
from app import app

@pytest.fixture
def client():
    return app.test_client()


def test_index(client):
    resp = client.get('/')
    assert resp.status_code == 200
    assert b'Порівняння тарифів служб доставки' in resp.data


def test_compare_invalid_weight(client):
    resp = client.post('/compare', data={
        'sender': 'Київ', 'receiver': 'Львів',
        'weight': 'abc', 'date': '2025-05-21', 'option': 'Найдешевший'
    })
    assert resp.status_code == 400
    assert b'Невірний формат ваги' in resp.data


def test_compare_invalid_date(client):
    resp = client.post('/compare', data={
        'sender': 'Київ', 'receiver': 'Львів',
        'weight': '1.5', 'date': '2020-01-01', 'option': 'Найдешевший'
    })
    assert resp.status_code == 400
    assert b'Дата не може бути в минулому' in resp.data
