"""Integration tests for routers/mofa.py -- MoFA Compliance Report export + (8 Sep 2026) import half."""

import pytest

from app.models import Role, GradeResult
from tests.conftest import login, auth_headers
from tests.factories import make_delivered_graded_pickup, make_undelivered_pickup

pytestmark = pytest.mark.integration


def test_compliance_report_excludes_pickup_with_no_buyer_link_even_when_graded(client, roles, rate_config, db_session, make_user):
    from app.models import FulfilmentIntake, DispatchJobStatus
    from datetime import datetime

    farmer = make_user(Role.FARMER)
    finance = roles[Role.FINANCE]
    pickup, job = make_undelivered_pickup(db_session, farmer, requirement=None)
    job.status = DispatchJobStatus.DELIVERED
    job.delivered_at = datetime.utcnow()
    db_session.add(FulfilmentIntake(harvest_pickup_request_id=pickup.id, weigh_in_kg=1000.0, grade=GradeResult.GRADE_1, graded_by=finance.id))
    db_session.commit()

    token = login(client, finance.email)
    report = client.get("/mofa/compliance-report", headers=auth_headers(token)).json()
    assert report == []


def test_compliance_report_includes_reject_and_buyer_linked_row(client, roles, rate_config, db_session, make_user):
    from tests.factories import make_requirement

    buyer = make_user(Role.BUYER)
    farmer = make_user(Role.FARMER)
    finance = roles[Role.FINANCE]
    req = make_requirement(db_session, buyer)
    make_delivered_graded_pickup(db_session, farmer, finance, requirement=req, weigh_in_kg=980.0, grade=GradeResult.REJECT)

    token = login(client, finance.email)
    report = client.get("/mofa/compliance-report", headers=auth_headers(token)).json()
    assert len(report) == 1
    assert report[0]["grade"] == "Reject"


def test_export_csv_returns_real_csv_with_four_confirmed_columns(client, roles, rate_config, db_session, make_user):
    from tests.factories import make_requirement

    buyer = make_user(Role.BUYER)
    farmer = make_user(Role.FARMER)
    finance = roles[Role.FINANCE]
    req = make_requirement(db_session, buyer)
    make_delivered_graded_pickup(db_session, farmer, finance, requirement=req, weigh_in_kg=1000.0, grade=GradeResult.GRADE_1)

    token = login(client, finance.email)
    res = client.get("/mofa/compliance-report/export.csv", headers=auth_headers(token))
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert res.text.splitlines()[0] == "Volume (kg),Quality Grade,Buyer,Delivery Date"


def test_export_pdf_returns_a_real_pdf(client, roles, rate_config, db_session, make_user):
    from tests.factories import make_requirement

    buyer = make_user(Role.BUYER)
    farmer = make_user(Role.FARMER)
    finance = roles[Role.FINANCE]
    req = make_requirement(db_session, buyer)
    make_delivered_graded_pickup(db_session, farmer, finance, requirement=req, weigh_in_kg=1000.0, grade=GradeResult.GRADE_1)

    token = login(client, finance.email)
    res = client.get("/mofa/compliance-report/export.pdf", headers=auth_headers(token))
    assert res.status_code == 200
    assert res.content[:5] == b"%PDF-"


@pytest.mark.simulated
def test_import_record_round_trip_is_a_real_manual_record_not_a_stub(client, roles, rate_config):
    token = login(client, roles[Role.FINANCE].email)
    create = client.post("/mofa/import-records", json={"buyer_name": "Ghana School Feeding Programme", "verified": True}, headers=auth_headers(token))
    assert create.status_code == 200, create.text
    assert create.json()["verified"] is True
    assert create.json()["imported_by_name"] == roles[Role.FINANCE].full_name

    listed = client.get("/mofa/import-records", headers=auth_headers(token)).json()
    assert any(r["buyer_name"] == "Ghana School Feeding Programme" for r in listed)


def test_import_record_rejects_blank_buyer_name(client, roles, rate_config):
    token = login(client, roles[Role.FINANCE].email)
    res = client.post("/mofa/import-records", json={"buyer_name": "   "}, headers=auth_headers(token))
    assert res.status_code == 422


@pytest.mark.parametrize("wrong_role", [Role.LOGISTICS, Role.VENDOR, Role.FARMER, Role.SUPER_ADMIN, Role.AGRONOMIST])
def test_mofa_routes_blocked_for_non_finance_roles(client, roles, rate_config, wrong_role):
    token = login(client, roles[wrong_role].email)
    for path in ["/mofa/compliance-report", "/mofa/import-records"]:
        res = client.get(path, headers=auth_headers(token))
        assert res.status_code == 403
