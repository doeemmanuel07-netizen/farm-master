"""
Unit tests for app/reporting.py -- both the MoFA Compliance Report's row
computation/export rendering and the Reporting dashboard's revenue-stream
computation (added 8 Sep 2026). Deferred revenue streams must never carry
a fabricated value -- that's the specific property under test here.
"""

import pytest

from app.models import Role, GradeResult, UserStatus, DispatchJobStatus, FulfilmentIntake
from app.reporting import get_compliance_rows, to_csv_bytes, to_pdf_bytes, get_reporting_dashboard
from tests.factories import make_requirement, make_delivered_graded_pickup, make_undelivered_pickup

pytestmark = pytest.mark.unit


def test_compliance_rows_exclude_pickup_with_no_buyer_link(db_session, rate_config, make_user):
    farmer = make_user(Role.FARMER)
    finance = make_user(Role.FINANCE)
    pickup, job = make_undelivered_pickup(db_session, farmer, requirement=None)
    from datetime import datetime

    job.status = DispatchJobStatus.DELIVERED
    job.delivered_at = datetime.utcnow()
    db_session.add(FulfilmentIntake(harvest_pickup_request_id=pickup.id, weigh_in_kg=1000.0, grade=GradeResult.GRADE_1, graded_by=finance.id))
    db_session.commit()

    rows = get_compliance_rows(db_session)
    assert rows == []


def test_compliance_rows_include_reject_grade(db_session, rate_config, make_user):
    buyer = make_user(Role.BUYER)
    farmer = make_user(Role.FARMER)
    finance = make_user(Role.FINANCE)
    req = make_requirement(db_session, buyer)
    make_delivered_graded_pickup(db_session, farmer, finance, requirement=req, weigh_in_kg=500.0, grade=GradeResult.REJECT)
    rows = get_compliance_rows(db_session)
    assert len(rows) == 1
    assert rows[0].grade == "Reject"


def test_csv_export_has_exactly_four_confirmed_columns(db_session, rate_config, make_user):
    buyer = make_user(Role.BUYER)
    farmer = make_user(Role.FARMER)
    finance = make_user(Role.FINANCE)
    req = make_requirement(db_session, buyer)
    make_delivered_graded_pickup(db_session, farmer, finance, requirement=req, weigh_in_kg=1000.0, grade=GradeResult.GRADE_1)
    rows = get_compliance_rows(db_session)
    csv_bytes = to_csv_bytes(rows)
    text = csv_bytes.decode("utf-8")
    header = text.splitlines()[0]
    assert header == "Volume (kg),Quality Grade,Buyer,Delivery Date"


def test_pdf_export_produces_a_real_pdf_file(db_session, rate_config, make_user):
    buyer = make_user(Role.BUYER)
    farmer = make_user(Role.FARMER)
    finance = make_user(Role.FINANCE)
    req = make_requirement(db_session, buyer)
    make_delivered_graded_pickup(db_session, farmer, finance, requirement=req, weigh_in_kg=1000.0, grade=GradeResult.GRADE_1)
    rows = get_compliance_rows(db_session)
    pdf_bytes = to_pdf_bytes(rows)
    assert pdf_bytes[:5] == b"%PDF-"


def test_dashboard_deferred_streams_never_carry_a_fabricated_value(db_session, rate_config, make_user):
    dashboard = get_reporting_dashboard(db_session)
    deferred = [r for r in dashboard.revenue_streams if r.deferred_phase]
    assert len(deferred) == 3
    for stream in deferred:
        assert stream.value is None


def test_dashboard_live_streams_carry_a_value_not_a_deferred_phase(db_session, rate_config, make_user):
    dashboard = get_reporting_dashboard(db_session)
    live = [r for r in dashboard.revenue_streams if not r.deferred_phase]
    assert len(live) == 3
    for stream in live:
        assert stream.value is not None


def test_dashboard_registered_farmers_excludes_suspended(db_session, rate_config, make_user):
    make_user(Role.FARMER, status=UserStatus.ACTIVE)
    make_user(Role.FARMER, status=UserStatus.SUSPENDED)
    dashboard = get_reporting_dashboard(db_session)
    assert dashboard.registered_farmers == 1


def test_dashboard_volume_aggregated_excludes_reject(db_session, rate_config, make_user):
    buyer = make_user(Role.BUYER)
    farmer = make_user(Role.FARMER)
    finance = make_user(Role.FINANCE)
    req = make_requirement(db_session, buyer)
    make_delivered_graded_pickup(db_session, farmer, finance, requirement=req, weigh_in_kg=1000.0, grade=GradeResult.GRADE_1)
    make_delivered_graded_pickup(db_session, farmer, finance, requirement=req, weigh_in_kg=500.0, grade=GradeResult.REJECT)
    dashboard = get_reporting_dashboard(db_session)
    assert dashboard.volume_aggregated_tonnes == 1.0
