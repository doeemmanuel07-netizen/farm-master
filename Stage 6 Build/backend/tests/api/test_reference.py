"""Reference data (CEO demo brief §2A-C, §3): public stats/crops/regions, /auth/me profile line, and Super Admin activation toggles."""

import pytest

from app.models import Role, BuyerType, FarmerCrop
from tests.conftest import login, auth_headers

pytestmark = pytest.mark.integration


def test_public_stats_are_computed_from_the_database(client, rate_config, reference_data):
    res = client.get("/api/public/stats")
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "coordinated_portals": 3,
        "fulfilment_centres": 16,
        "active_fulfilment_centres": 1,
        "revenue_streams": 6,
        "head_office": "Tema",
    }


def test_pilot_config_exposes_only_maize_and_greater_accra(client, reference_data):
    crops = client.get("/api/public/crops").json()
    assert [c["name"] for c in crops] == ["Maize"]
    assert [v["name"] for v in crops[0]["varieties"]] == ["Obatanpa"]
    regions = client.get("/api/public/regions").json()
    assert [r["name"] for r in regions] == ["Greater Accra"]


def test_activating_a_crop_opens_it_for_ordering_without_code_change(client, roles, reference_data):
    token = login(client, roles[Role.SUPER_ADMIN].email)
    soy = reference_data["crops"]["Soybean"]
    res = client.put(f"/admin/crops/{soy.id}", json={"is_active_for_ordering": True}, headers=auth_headers(token))
    assert res.status_code == 200 and res.json()["is_active_for_ordering"] is True
    assert {c["name"] for c in client.get("/api/public/crops").json()} == {"Maize", "Soybean"}
    actions = [e["action"] for e in client.get("/admin/audit-log", headers=auth_headers(token)).json()]
    assert "crop_updated" in actions


def test_crop_reference_price_must_be_positive(client, roles, reference_data):
    token = login(client, roles[Role.SUPER_ADMIN].email)
    maize = reference_data["crops"]["Maize"]
    res = client.put(f"/admin/crops/{maize.id}", json={"reference_price_per_tonne": 0}, headers=auth_headers(token))
    assert res.status_code == 422


def test_duplicate_variety_is_rejected(client, roles, reference_data):
    token = login(client, roles[Role.SUPER_ADMIN].email)
    maize = reference_data["crops"]["Maize"]
    assert client.post(f"/admin/crops/{maize.id}/varieties", json={"name": "Abontem"}, headers=auth_headers(token)).status_code == 200
    assert client.post(f"/admin/crops/{maize.id}/varieties", json={"name": "obatanpa"}, headers=auth_headers(token)).status_code == 409


def test_region_toggle_and_hq_centre_cannot_be_deactivated(client, roles, reference_data):
    token = login(client, roles[Role.SUPER_ADMIN].email)
    eastern = reference_data["regions"]["Eastern"]
    assert client.put(f"/admin/regions/{eastern.id}", json={"is_active": True}, headers=auth_headers(token)).json()["is_active"]
    centres = client.get("/admin/fulfilment-centres", headers=auth_headers(token)).json()
    assert len(centres) == 16 and centres[0]["is_hq"] and centres[0]["town"] == "Tema"
    res = client.put(f"/admin/fulfilment-centres/{centres[0]['id']}", json={"is_active": False}, headers=auth_headers(token))
    assert res.status_code == 409


@pytest.mark.parametrize("role", [Role.FINANCE, Role.AGRONOMIST, Role.FARMER, Role.BUYER])
def test_reference_admin_is_super_admin_only(client, roles, reference_data, role):
    token = login(client, roles[role].email)
    maize = reference_data["crops"]["Maize"]
    assert client.put(f"/admin/crops/{maize.id}", json={"is_active_for_ordering": False}, headers=auth_headers(token)).status_code == 403


def test_me_builds_the_portal_header_line(client, db_session, make_user, reference_data):
    farmer = make_user(Role.FARMER, full_name="Kwabena Asante")
    farmer.region_id = reference_data["regions"]["Eastern"].id
    farmer.farmer_union_id = reference_data["unions"]["Nsawam Farmer Union"].id
    db_session.add(FarmerCrop(farmer_id=farmer.id, crop_id=reference_data["crops"]["Maize"].id))
    buyer = make_user(Role.BUYER, organisation_name="Ministry of Food & Agriculture")
    buyer.buyer_type = BuyerType.INSTITUTIONAL
    buyer.mofa_verified = True
    db_session.commit()

    me = client.get("/auth/me", headers=auth_headers(login(client, farmer.email))).json()
    assert me["profile_line"] == "Kwabena Asante · Nsawam Farmer Union · Eastern Region"
    assert me["crops"] == ["Maize"]
    me = client.get("/auth/me", headers=auth_headers(login(client, buyer.email))).json()
    assert me["profile_line"] == "Ministry of Food & Agriculture · Institutional buyer"
    assert me["mofa_verified"] is True


def test_me_requires_auth(client):
    assert client.get("/auth/me").status_code == 401
