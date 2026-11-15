
from pydantic import BaseModel, EmailStr, Field


class SignupPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class PaymentVerifyPayload(BaseModel):
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
