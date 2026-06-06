from uuid import UUID
from pydantic import BaseModel, model_validator

from app.core.constants.payment import (
    PaymentMethod,
)


class PaymentInitiateRequest(BaseModel):
    booking_id: UUID


class PaymentProcessRequest(BaseModel):
    payment_id: UUID
    payment_method: PaymentMethod
    card_number: str | None = None
    card_cvv: str | None = None
    card_holder_name: str | None = None
    upi_id: str | None = None
    netbanking_user: str | None = None
    netbanking_password: str | None = None

    @model_validator(mode="after")
    def validate_method_fields(self):
        if self.payment_method == PaymentMethod.CARD:
            if not self.card_number or not self.card_cvv:
                raise ValueError("card_number and card_cvv required for CARD payment")
        elif self.payment_method == PaymentMethod.UPI:
            if not self.upi_id:
                raise ValueError("upi_id required for UPI payment")
        elif self.payment_method == PaymentMethod.NETBANKING:
            if not self.netbanking_user or not self.netbanking_password:
                raise ValueError("netbanking credentials required")
        return self
