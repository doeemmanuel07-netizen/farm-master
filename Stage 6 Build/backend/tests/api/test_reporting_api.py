"""Integration tests for routers/reporting.py -- Reporting Dashboard endpoint (8 Sep 2026). Revenue-stream computation itself is covered in tests/unit/test_reporting_calc.py; this file is the routing/RBAC layer."""

import pytest

from app.models import Role
from tests.conftest import login, auth_headers

pytestmark = pytest.mark.integration


def test_dashboard_reachable_by_finance(client, roles, rate_config):
    token = login(client, roles[Role.FINANCE].email)
    res = client.get("/reporting/dashboard", headers=auth_headers(token))
    assert res.status_code == 200
    body = res.json()
    assert len(body["revenue_streams"]) == 6


@pytest.mark.parametrize("wrong_role", [Role.LOGISTICS, Role.VENDOR, Role.FARMER, Role.SUPER_ADMIN, Role.AGRONOMIST, Role.BUYER])
def test_dashboard_blocked_for_every_other_role(client, roles, rate_config, wrong_role):
    token = login(client, roles[wrong_role].email)
    res = client.get("/reporting/dashboard", headers=auth_headers(token))
    assert res.status_code == 403
