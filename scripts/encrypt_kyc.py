import os
import sys
from cryptography.fernet import Fernet

# Ensure the project root is on sys.path when running from scripts/
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)


KYC_ENCRYPTION_KEY = "twpksQQxkqKmap8_vSKabLOL9hKA0RNPB9wZm8kTpXo="


def encrypt(plain_value: str) -> str:
    fernet = Fernet(KYC_ENCRYPTION_KEY.encode())
    return fernet.encrypt(plain_value.encode()).decode()


def main() -> None:
    if len(sys.argv) > 1:
        plain_value = sys.argv[1]
    else:
        plain_value = input("Enter plain value to encrypt: ").strip()

    if not plain_value:
        print("Error: empty input")
        sys.exit(1)

    encrypted = encrypt(plain_value)
    print("\n─── Encryption Result ───")
    print(f"Plain:     {plain_value}")
    print(f"Encrypted: {encrypted}")
    print(f"Length:    {len(encrypted)} chars")


if __name__ == "__main__":
    main()
