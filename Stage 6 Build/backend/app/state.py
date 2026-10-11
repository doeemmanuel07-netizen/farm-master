"""
State-transition rules (CEO demo brief §8: "proper status enums and
state-transition functions for orders, allocations and jobs -- no free-text
statuses"). Every status change on these entities goes through
transition(), which refuses anything not in the table below, so an illegal
jump (e.g. a buyer order straight from MATCHING to DELIVERED) is a 409
everywhere rather than a per-router check that might be forgotten.
"""

from fastapi import HTTPException

from .models import (
    RequirementStatus as R, DispatchJobStatus as D, TrunkingStatus as T, OpportunityStatus as O,
    InputOrderStatus as I,
)

ALLOWED = {
    R: {
        R.DRAFT: {R.PENDING_PAYMENT},
        R.PENDING_PAYMENT: {R.MATCHING},
        R.MATCHING: {R.PRODUCTION},
        R.PRODUCTION: {R.AGGREGATION},
        R.AGGREGATION: {R.SHIPMENT},
        R.SHIPMENT: {R.DELIVERED},
        R.DELIVERED: set(),
    },
    D: {D.ASSIGNED: {D.EN_ROUTE}, D.EN_ROUTE: {D.DELIVERED}, D.DELIVERED: set()},
    T: {T.SCHEDULED: {T.DISPATCHED}, T.DISPATCHED: {T.DELIVERED}, T.DELIVERED: set()},
    O: {O.OPEN: {O.ACCEPTED}, O.ACCEPTED: set()},
    I: {I.PENDING: {I.CONFIRMED, I.DECLINED}, I.CONFIRMED: set(), I.DECLINED: set()},
}


class InvalidTransition(HTTPException):
    def __init__(self, current, target):
        super().__init__(status_code=409, detail=f"Can't move from '{current.value}' to '{target.value}'.")


def can_transition(current, target) -> bool:
    return target in ALLOWED[type(current)].get(current, set())


def transition(obj, target, field: str = "status"):
    """Sets obj.<field> = target if the move is allowed, else raises a 409."""
    current = getattr(obj, field)
    if not can_transition(current, target):
        raise InvalidTransition(current, target)
    setattr(obj, field, target)
    return obj
