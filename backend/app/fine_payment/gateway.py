from __future__ import annotations

from typing import Any, Protocol

from .models import GatewayResult, PaymentRequest


class PaymentGatewayError(Exception):
    """Base class for explicit payment gateway failures."""


class GatewayNotConfigured(PaymentGatewayError):
    pass


class GatewayTimeout(PaymentGatewayError):
    pass


class InvalidGatewayResult(PaymentGatewayError):
    pass


class PaymentGateway(Protocol):
    def start_payment(self, request: PaymentRequest) -> GatewayResult | None:
        """Return a verified result, or None after the 30-second response window."""
        ...

    def check_status(self, payment_ref: str) -> GatewayResult | None:
        ...

    def verify_callback(self, payload: dict[str, Any]) -> GatewayResult:
        """Validate the provider callback and parse its verified payment result."""
        ...


class UnconfiguredPaymentGateway:
    def start_payment(self, request: PaymentRequest) -> GatewayResult | None:
        raise GatewayNotConfigured("ยังไม่ได้ตั้งค่าผู้ให้บริการ Payment Gateway")

    def check_status(self, payment_ref: str) -> GatewayResult | None:
        raise GatewayNotConfigured("ยังไม่ได้ตั้งค่าผู้ให้บริการ Payment Gateway")

    def verify_callback(self, payload: dict[str, Any]) -> GatewayResult:
        raise GatewayNotConfigured("ยังไม่ได้ตั้งค่าผู้ให้บริการ Payment Gateway")
