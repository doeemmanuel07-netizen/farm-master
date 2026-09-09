"""Integration tests for routers/dashboard.py -- Control Centre Dashboard (8 Sep 2026), shared by all four internal roles with role-scoped tiles. The specific property under test: one role never sees another role's tile keys."""

import pytest

from app.models import Role
from tests.conftest import login, auth_headers

pytestmark = pytest.mark.integration

TILE_KEYS_BY_ROLE = {
    Role.AGRONOMIST: {"matching_queue_open", "visits_scheduled", "unread_messages"},
    Role.LOGISTICS: {"dispatch_jobs_open", "trunking_scheduled"},
    Role.FINANCE: {"reconciliation_orders", "mofa_import_records"},
    Role.SUPER_ADMIN: {"pending_registrations", "total_users"},
}


@pytest.mark.parametrize("role", [Role.AGRONOMIST, Role.LOGISTICS, Role.FINANCE, Role.SUPER_ADMIN])
def test_each_internal_role_sees_only_its_own_tiles(client, roles, rate_config, role):
    token = login(client, roles[role].email)
    res = client.get("/dashboard/control-centre", headers=auth_headers(token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["role"] == role.value
    assert set(body["tiles"].keys()) == TILE_KEYS_BY_ROLE[role]

    # Negative check -- no other role's tile keys leak in.
    other_keys = set().union(*(v for k, v in TILE_KEYS_BY_ROLE.items() if k != role))
    leaked = other_keys & set(body["tiles"].keys())
    assert leaked == set(), f"{role.value} dashboard leaked another role's tile(s): {leaked}"


def test_shared_season_snapshot_is_identical_across_roles(client, roles, rate_config):
    tokens = {r: login(client, roles[r].email) for r in TILE_KEYS_BY_ROLE}
    snapshots = []
    for r, t in tokens.items():
        body = client.get("/dashboard/control-centre", headers=auth_headers(t)).json()
        snapshots.append((body["registered_farmers"], body["active_buyers"], body["volume_aggregated_tonnes"]))
    assert len(set(snapshots)) == 1


@pytest.mark.parametrize("wrong_role", [Role.BUYER, Role.FARMER, Role.VENDOR])
def test_portal_roles_cannot_reach_the_control_centre(client, roles, rate_config, wrong_role):
    token = login(client, roles[wrong_role].email)
    res = client.get("/dashboard/control-centre", headers=auth_headers(token))
    assert res.status_code == 403
