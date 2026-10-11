"""State-transition tables (brief §8): every allowed move works, everything else is a 409."""

import pytest

from app.models import (
    RequirementStatus as R, DispatchJobStatus as D, TrunkingStatus as T, OpportunityStatus as O, InputOrderStatus as I,
)
from app.state import ALLOWED, InvalidTransition, can_transition, transition

pytestmark = pytest.mark.unit


class Obj:
    def __init__(self, status):
        self.status = status


def test_buyer_order_lifecycle_is_strictly_linear():
    path = [R.DRAFT, R.PENDING_PAYMENT, R.MATCHING, R.PRODUCTION, R.AGGREGATION, R.SHIPMENT, R.DELIVERED]
    o = Obj(path[0])
    for nxt in path[1:]:
        transition(o, nxt)
    assert o.status == R.DELIVERED
    for a in R:
        for b in R:
            expected = path.index(b) == path.index(a) + 1
            assert can_transition(a, b) == expected, (a, b)


@pytest.mark.parametrize("enum_cls", [R, D, T, O, I])
def test_every_status_has_a_row(enum_cls):
    assert set(ALLOWED[enum_cls]) == set(enum_cls)


def test_illegal_move_is_409_and_leaves_state_unchanged():
    o = Obj(D.ASSIGNED)
    with pytest.raises(InvalidTransition) as exc:
        transition(o, D.DELIVERED)
    assert exc.value.status_code == 409 and o.status == D.ASSIGNED
    assert can_transition(I.PENDING, I.DECLINED) and not can_transition(I.DECLINED, I.CONFIRMED)
    assert not can_transition(O.ACCEPTED, O.OPEN)
