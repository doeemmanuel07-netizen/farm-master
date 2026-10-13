"""Stakeholder feedback: anyone can post from any page; only Super Admin can read or export it."""

import pytest

from app.models import Role
from app.routers import feedback as feedback_router
from tests.conftest import login, auth_headers

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _reset_throttle():
    feedback_router._recent.clear()
    yield
    feedback_router._recent.clear()


def test_anonymous_feedback_is_saved_with_its_portal(client, roles):
    res = client.post("/api/feedback", json={
        "page": "/buyer?x=1", "category": "suggestion", "message": "  Show the fee before I submit.  ", "name": "Ama, GSFP",
    })
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["portal"] == "Buyer"
    assert body["page"] == "/buyer"
    assert body["message"] == "Show the fee before I submit."
    assert body["user_role"] is None


def test_signed_in_feedback_records_the_author(client, roles):
    token = login(client, roles[Role.FARMER].email)
    res = client.post("/api/feedback", headers=auth_headers(token),
                      json={"page": "/farmer", "category": "praise", "message": "Clear formula steps."})
    assert res.status_code == 201
    assert res.json()["user_role"] == "farmer"
    assert res.json()["user_name"] == roles[Role.FARMER].full_name


@pytest.mark.parametrize("page,portal", [
    ("/", "Overview"), ("/marketplace", "Vendor"), ("/vendor-dashboard-flow", "Vendor"),
    ("/control-centre-flow", "Control Centre"), ("/harvest-pickup-flow", "Farmer"),
])
def test_portal_is_derived_from_the_page(page, portal):
    assert feedback_router.portal_for(page) == portal


def test_invalid_feedback_is_rejected(client):
    assert client.post("/api/feedback", json={"page": "/", "category": "spam", "message": "hello"}).status_code == 422
    assert client.post("/api/feedback", json={"page": "/", "category": "question", "message": "   "}).status_code == 422


def test_only_super_admin_can_read_and_export(client, roles):
    client.post("/api/feedback", json={"page": "/", "category": "question", "message": "Who runs logistics?"})
    assert client.get("/api/feedback").status_code == 401
    buyer = login(client, roles[Role.BUYER].email)
    assert client.get("/api/feedback", headers=auth_headers(buyer)).status_code == 403
    admin = login(client, roles[Role.SUPER_ADMIN].email)
    listed = client.get("/api/feedback", headers=auth_headers(admin))
    assert listed.status_code == 200
    assert any(r["message"] == "Who runs logistics?" for r in listed.json())
    csv = client.get("/api/feedback/export.csv", headers=auth_headers(admin))
    assert csv.status_code == 200
    assert csv.headers["content-type"].startswith("text/csv")
    assert "Who runs logistics?" in csv.text


def test_posting_is_rate_limited_per_address(client):
    for _ in range(feedback_router.MAX_PER_HOUR):
        assert client.post("/api/feedback", json={"page": "/", "category": "praise", "message": "Nice work"}).status_code == 201
    assert client.post("/api/feedback", json={"page": "/", "category": "praise", "message": "Nice work"}).status_code == 429


def test_every_page_carries_the_feedback_button(client):
    for path in ("/", "/farmer", "/buyer", "/marketplace", "/vendor-dashboard-flow", "/control-centre-flow", "/feedback"):
        res = client.get(path)
        assert res.status_code == 200
        assert "/static/assets/feedback.js" in res.text, path
