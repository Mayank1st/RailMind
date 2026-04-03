# JWT, password hashing (implement as auth grows)
import hmac
import hashlib

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from typing import Any

COMMON_PASSWORD_SET = [
    "Test@123",
    "Admin@123",
    "Admin@1234",
    "User@123",
    "Password@123",
    "Password@1234",
    "Welcome@123",
    "Welcome@1234",
    "Login@123",
    "Company@123",
    "Hello@123",
    "Love@123",
    "Iloveyou@123",
    "Pass@1234",
    "PassWord@1",
    "Test@1111",
    "Test@0000",
    "Rahul@123",
    "Amit@1234",
    "Neha@123",
    "Pooja@123",
    "Mayank@123",
    "Krishna@123",
    "Radhe@123",
    "Mahadev@123",
    "India@123",
    "Bharat@123",
    "Delhi@123",
    "Office@123",
    "Work@123",
    "User@2024",
    "Test@2024",
    "Admin@2024",
    "Password@2024",
]


#  Hash Sensistive Data

SECRET_KEY = "KYC_HMAC_SECRET"

ph = PasswordHasher(
    time_cost=3,
    memory_cost=102400,
    parallelism=4,
)


def encode_sensistive_data(plain_data:Any) -> str :
    return ph.hash(plain_data)

def verify_encoded_data(plain_data:Any,encoded_data:Any) -> bool :
    try:
        return ph.verify(encoded_data,plain_data)
    except VerifyMismatchError :
        return False

def hmac_kyc(value: str) -> str:
    return hmac.new(
        SECRET_KEY.encode(),
        value.encode(),
        hashlib.sha256
    ).hexdigest()