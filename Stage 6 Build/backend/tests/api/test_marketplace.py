"""
Farmer marketplace on listings (CEO demo brief §6.1, decision D1): the
demo catalogue by tab, multi-vendor cart split, dates for equipment and
services, stock reservation and restore, wallet debit and reversal, the
agronomist-visit task, and the vendor -> logistics handoff.
"""

from datetime import date, timedelta

import pytest

from app.models import Role, ListingCategory, Listing, ListingStatus, InputOrder
from tests.conftest import login, auth_headers

pytestmark = pytest.mark.integration


@pytest.fixture()
def market(db_session, make_user, rate_config, roles):
    from app.marketplace import seed_marketplace
    for name in ("Seeds", "Fertilizer", "Equipment", "Services", "Other"):
        db_session.add(ListingCategory(name=name, slug=name.lower()))
    db_session.commit()
    third_party = make_user(Role.VENDOR, email="vendor@farmmaster.test", organisation_name="Kwame's Agro Supplies")
    seed_marketplace(db_session)
    farmer = make_user(Role.FARMER, full_name="Kwabena Asante")
    return {"farmer": farmer, "vendor": third_party}


def _items(client, token, kind=None):
    q = f"?kind={kind}" if kind else ""
    return client.get(f"/farmer/marketplace{q}", headers=auth_headers(token)).json()


def _by_title(cat, title):
    return next(i for i in cat["items"] if i["title"] == title)


def test_demo_catalogue_by_tab(client, market):
    token = login(client, market["farmer"].email)
    cat = _items(client, token)
    assert [t["label"] for t in cat["tabs"]] == ["Seeds & Inputs", "Equipment Rental", "Mechanisation Services"]
    assert cat["delivery_sla_days"] == 2
    inputs = _items(client, token, "input")["items"]
    assert {i["title"] for i in inputs} >= {"Improved Maize Seed (Obatanpa)", "NPK 15-15-15 Fertiliser", "Crop Protection — Fungicide"}
    equip = _items(client, token, "equipment")["items"]
    assert [(i["title"], i["price"], i["unit"]) for i in equip] == [
        ("Water pump set — day rate", 150.0, "per day"), ("Motorised planter — day rate", 280.0, "per day"),
        ("Tractor with plough — day rate", 650.0, "per day")]
    tractor = equip[2]
    assert tractor["vendor_name"] == "Farm Master Services" and tractor["vendor_owned"] and tractor["needs_date"]
    assert tractor["icon"] == "tractor" and tractor["quantity_noun"] == "days"
    seed = _by_title(cat, "Improved Maize Seed (Obatanpa)")
    assert seed["vendor_name"] == "Kwame's Agro Supplies" and not seed["vendor_owned"] and not seed["needs_date"]


def test_multi_vendor_cart_splits_per_vendor_and_debits_wallet(client, market, db_session):
    token = login(client, market["farmer"].email)
    cat = _items(client, token)
    npk, tractor = _by_title(cat, "NPK 15-15-15 Fertiliser"), _by_title(cat, "Tractor with plough — day rate")
    when = (date.today() + timedelta(days=5)).isoformat()
    res = client.post("/farmer/marketplace/orders", json={"lines": [
        {"listing_id": npk["id"], "quantity": 2},
        {"listing_id": tractor["id"], "quantity": 1, "requested_date": when},
        {"listing_id": npk["id"], "quantity": 1},  # re-add merges into the same line
    ]}, headers=auth_headers(token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["message"] == "Order routed to Farm Master logistics — estimated farm-gate delivery in 2 days."
    assert body["total"] == 3 * 265 + 650
    assert len(body["orders"]) == 2 and len({o["checkout_ref"] for o in body["orders"]}) == 1
    by_vendor = {o["vendor_name"]: o for o in body["orders"]}
    assert by_vendor["Kwame's Agro Supplies"]["lines"][0]["quantity"] == 3
    assert by_vendor["Farm Master Services"]["lines"][0]["requested_date"] == when
    assert db_session.query(Listing).filter(Listing.id == npk["id"]).first().quantity_available == 197
    wallet = client.get("/farmer/wallet/summary", headers=auth_headers(token)).json()
    assert wallet["input_costs"] == 3 * 265 + 650


@pytest.mark.parametrize("line,code", [
    ({"quantity": 1}, 422),                                      # equipment needs a date
    ({"quantity": 1, "requested_date": "2020-01-01"}, 422),      # in the past
    ({"quantity": 0, "requested_date": "2099-01-01"}, 422),
])
def test_equipment_line_validation(client, market, line, code):
    token = login(client, market["farmer"].email)
    tractor = _by_title(_items(client, token), "Tractor with plough — day rate")
    res = client.post("/farmer/marketplace/orders", json={"lines": [dict(line, listing_id=tractor["id"])]}, headers=auth_headers(token))
    assert res.status_code == code


def test_stock_limit_inactive_listing_and_empty_cart(client, market, db_session):
    token = login(client, market["farmer"].email)
    fungicide = _by_title(_items(client, token), "Crop Protection — Fungicide")
    assert client.post("/farmer/marketplace/orders", json={"lines": [{"listing_id": fungicide["id"], "quantity": 81}]},
                       headers=auth_headers(token)).status_code == 409
    assert client.post("/farmer/marketplace/orders", json={"lines": []}, headers=auth_headers(token)).status_code == 422
    listing = db_session.query(Listing).filter(Listing.id == fungicide["id"]).first()
    listing.status = ListingStatus.ARCHIVED
    db_session.commit()
    assert client.post("/farmer/marketplace/orders", json={"lines": [{"listing_id": fungicide["id"], "quantity": 1}]},
                       headers=auth_headers(token)).status_code == 404


def test_buying_out_stock_marks_listing_out_of_stock_and_decline_restores(client, market, db_session):
    token = login(client, market["farmer"].email)
    fungicide = _by_title(_items(client, token), "Crop Protection — Fungicide")
    order = client.post("/farmer/marketplace/orders", json={"lines": [{"listing_id": fungicide["id"], "quantity": 80}]},
                        headers=auth_headers(token)).json()["orders"][0]
    listing = db_session.query(Listing).filter(Listing.id == fungicide["id"]).first()
    db_session.refresh(listing)
    assert listing.status == ListingStatus.OUT_OF_STOCK and listing.quantity_available == 0

    vendor_token = login(client, market["vendor"].email)
    incoming = client.get("/vendor/input-orders", headers=auth_headers(vendor_token)).json()
    assert any(o["id"] == order["id"] and o["lines"][0]["product_name"] == "Crop Protection — Fungicide" for o in incoming)
    assert client.post(f"/vendor/input-orders/{order['id']}/decline", headers=auth_headers(vendor_token)).status_code == 200
    db_session.refresh(listing)
    assert listing.status == ListingStatus.ACTIVE and listing.quantity_available == 80
    wallet = client.get("/farmer/wallet/summary", headers=auth_headers(token)).json()
    assert wallet["input_costs"] == 0


def test_vendor_confirm_hands_off_to_logistics_with_anonymised_event(client, market, roles, db_session):
    token = login(client, market["farmer"].email)
    seed = _by_title(_items(client, token), "Improved Maize Seed (Obatanpa)")
    order = client.post("/farmer/marketplace/orders", json={"lines": [{"listing_id": seed["id"], "quantity": 2}]},
                        headers=auth_headers(token)).json()["orders"][0]
    vendor_token = login(client, market["vendor"].email)
    confirmed = client.post(f"/vendor/input-orders/{order['id']}/confirm", headers=auth_headers(vendor_token)).json()
    assert confirmed["dispatch_status"] == "assigned"
    logi = login(client, roles[Role.LOGISTICS].email)
    job = next(j for j in client.get("/logistics/jobs", headers=auth_headers(logi)).json() if j["job_type"] == "input_order")
    client.post(f"/logistics/jobs/{job['id']}/dispatch", json={"tricycle_label": "#4"}, headers=auth_headers(logi))
    texts = [i["text"] for i in client.get("/api/public/activity").json()]
    assert "Live: Tricycle #4 en route with seeds for 1 farm." in texts
    assert client.post(f"/vendor/input-orders/{order['id']}/confirm", headers=auth_headers(vendor_token)).status_code == 409


def test_agronomist_visit_creates_a_farm_visit_task(client, market, roles):
    token = login(client, market["farmer"].email)
    visit = _by_title(_items(client, token), "Agronomist farm visit")
    when = date.today() + timedelta(days=3)
    client.post("/farmer/marketplace/orders", json={"lines": [{"listing_id": visit["id"], "quantity": 1, "requested_date": when.isoformat()}]},
                headers=auth_headers(token))
    agro = login(client, roles[Role.AGRONOMIST].email)
    tasks = client.get("/ops/agronomist-tasks", headers=auth_headers(agro)).json()
    task = next(t for t in tasks if t["kind"] == "farm_visit")
    assert task["farmer_name"] == "Kwabena Asante" and task["due_at"].startswith(when.isoformat())


@pytest.mark.parametrize("role", [Role.BUYER, Role.VENDOR, Role.FINANCE])
def test_marketplace_is_farmer_only(client, market, roles, role):
    token = login(client, roles[role].email)
    assert client.get("/farmer/marketplace", headers=auth_headers(token)).status_code == 403
