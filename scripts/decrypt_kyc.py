import os
import sys
from cryptography.fernet import Fernet, InvalidToken

# Ensure the project root is on sys.path when running from scripts/
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)


KYC_ENCRYPTION_KEY = "twpksQQxkqKmap8_vSKabLOL9hKA0RNPB9wZm8kTpXo="


def decrypt(encrypted_value: str) -> str:
    # fernet = Fernet(settings.KYC_ENCRYPTION_KEY.encode())
    fernet = Fernet(KYC_ENCRYPTION_KEY.encode())
    return fernet.decrypt(encrypted_value.encode()).decode()


def main() -> None:
    if len(sys.argv) > 1:
        encrypted_value = sys.argv[1]
    else:
        encrypted_value = input("Enter encrypted token to decrypt: ").strip()

    if not encrypted_value:
        print("Error: empty input")
        sys.exit(1)

    try:
        plain = decrypt(encrypted_value)
    except InvalidToken:
        print("Error: invalid token or wrong KYC_ENCRYPTION_KEY")
        sys.exit(1)

    print("\n─── Decryption Result ───")
    print(f"Encrypted: {encrypted_value}")
    print(f"Plain:     {plain}")


if __name__ == "__main__":
    main()
