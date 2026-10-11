"""
PaymentProvider interface (CEO demo brief §2D, §5.1).

Every payment in the app goes through one of these drivers. A driver can
only *start* a payment (initiate) and *read* a provider's callback
(parse_webhook). It never marks anything paid itself: app/payments/service.py
does that, and only in response to a webhook the driver has verified as
genuinely coming from the provider. The client is never trusted to say a
payment succeeded.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Mapping, Optional

from ..models import PaymentNetwork


class PaymentProviderError(RuntimeError):
    """The provider rejected or couldn't be reached for an initiate call."""


class WebhookVerificationError(RuntimeError):
    """A webhook failed signature or shape checks -- never acted on."""


@dataclass
class InitiateRequest:
    reference: str  # our own unique reference, echoed back by the provider
    amount: float  # GHS
    network: PaymentNetwork
    payer_phone: Optional[str]
    payer_email: str
    description: str
    callback_url: str


@dataclass
class InitiateResult:
    provider_ref: str
    status: str = "pending"  # pending | failed
    checkout_url: Optional[str] = None  # card payments: hosted page to redirect to
    display_text: str = ""  # what to tell the payer next, e.g. "Approve the prompt on your phone"
    failure_reason: Optional[str] = None


@dataclass
class WebhookEvent:
    provider_ref: str
    status: str  # success | failed
    amount: Optional[float] = None
    failure_reason: Optional[str] = None
    raw: Mapping = field(default_factory=dict)


class PaymentProvider(ABC):
    name: str = "base"

    @abstractmethod
    def initiate(self, req: InitiateRequest) -> InitiateResult:
        ...

    @abstractmethod
    def parse_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookEvent:
        """Verify the callback came from the provider, then normalise it. Raises WebhookVerificationError."""
        ...

    def supports(self, network: PaymentNetwork) -> bool:
        return True
