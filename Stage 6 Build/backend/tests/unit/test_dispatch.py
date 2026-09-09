"""
Unit tests for app/dispatch.py -- the single call site for creating a
DispatchJob from any of its three real sources. Asserts exactly one
source FK is ever set per job (models.DispatchJob's own documented
invariant) and that direction is assigned correctly for each source.
"""

import pytest

from app.models import Role, DispatchDirection, DispatchJobStatus, DispatchJob
from app.dispatch import create_dispatch_job, create_inbound_dispatch_job, create_input_order_dispatch_job
from tests.factories import make_confirmed_mechanisation_request, make_product, make_confirmed_input_order

pytestmark = pytest.mark.unit


def test_mechanisation_job_is_outbound_with_only_that_fk_set(db_session, rate_config, make_user):
    vendor = make_user(Role.VENDOR)
    from app.models import MechanisationRequest, MechanisationRequestStatus

    req = MechanisationRequest(
        vendor_id=vendor.id, farmer_name="X", service="Ploughing", area_acres=1.0,
        requested_by_date="2026-09-30", status=MechanisationRequestStatus.PENDING,
    )
    db_session.add(req)
    db_session.commit()

    job = create_dispatch_job(db_session, req)
    assert job.direction == DispatchDirection.OUTBOUND
    assert job.mechanisation_request_id == req.id
    assert job.harvest_pickup_request_id is None
    assert job.input_order_id is None
    assert job.status == DispatchJobStatus.ASSIGNED


def test_harvest_pickup_job_is_inbound_with_only_that_fk_set(db_session, rate_config, make_user):
    from app.models import HarvestPickupRequest

    farmer = make_user(Role.FARMER)
    pickup = HarvestPickupRequest(farmer_id=farmer.id, quantity_ready_tonnes=1.0, preferred_pickup_date="2026-09-20")
    db_session.add(pickup)
    db_session.commit()

    job = create_inbound_dispatch_job(db_session, pickup)
    assert job.direction == DispatchDirection.INBOUND
    assert job.harvest_pickup_request_id == pickup.id
    assert job.mechanisation_request_id is None
    assert job.input_order_id is None


def test_input_order_job_is_outbound_with_only_that_fk_set(db_session, rate_config, make_user):
    farmer = make_user(Role.FARMER)
    vendor = make_user(Role.VENDOR)
    product = make_product(db_session, vendor)
    order = make_confirmed_input_order(db_session, farmer, vendor, product, quantity=2.0)

    job = db_session.query(DispatchJob).filter(DispatchJob.input_order_id == order.id).one()
    assert job.direction == DispatchDirection.OUTBOUND
    assert job.input_order_id == order.id
    assert job.mechanisation_request_id is None
    assert job.harvest_pickup_request_id is None
