
from pydantic import BaseModel, Field
from uuid import UUID


class ClientPayload(BaseModel):
    client_id: UUID


class PaymentVerifyPayload(BaseModel):

    client_id: UUID

    razorpay_order_id: str = Field(
        min_length=5,
        max_length=100
    )

    razorpay_payment_id: str = Field(
        min_length=5,
        max_length=100
    )

    razorpay_signature: str = Field(
        min_length=20,
        max_length=200
    )
