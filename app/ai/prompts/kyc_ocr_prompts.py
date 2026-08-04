from app.domain.kyc.constants.kyc import DocumentType

# Shared rules — the same for every document. The overriding instruction is that a
# guessed digit is worse than a null: the user is shown these values to confirm, and
# a plausible-looking wrong Aadhaar number is exactly what nobody proof-reads.
COMMON_RULES = """      ━━━ RULES ━━━
      - Return ONLY raw JSON. No markdown, no code fences, no commentary.
      - Read ONLY what is printed on the card. Never infer, complete or correct a value.
      - If a field is blurred, cropped, covered or not present -> null.
      - NEVER guess a digit or a character. A null is correct; a wrong number is not.
      - Do not transcribe the address block, the QR code or any other text.
      - If the image is not the document type asked for, set every field to null."""


def aadhaar_ocr_prompt() -> str:
    return f"""You are reading a photograph of an Indian Aadhaar card.

      Extract exactly these four fields.

      | Field         | What to read                                                |
      |---------------|-------------------------------------------------------------|
      | name          | The cardholder's name as printed (English line only)         |
      | aadhaar_number| The 12-digit number. Strip spaces -> "123412341234"          |
      | date_of_birth | DOB / Year of Birth, as YYYY-MM-DD. Year only -> YYYY-01-01  |
      | gender        | MALE or FEMALE or OTHER                                      |

{COMMON_RULES}
      - Indian cards print dates as DD/MM/YYYY. "12/04/1995" is 12 April 1995
        -> "1995-04-12". It is NEVER 4 December. If the order is ambiguous
        (both parts <= 12) and nothing on the card settles it, return null.
      - The Aadhaar number is exactly 12 digits. If you can read fewer, return null.
      - Aadhaar cards print Hindi and English. Use the English line for the name.

      ━━━ OUTPUT ━━━
      {{"name": "<text or null>", "aadhaar_number": "<12 digits or null>",
        "date_of_birth": "<YYYY-MM-DD or null>", "gender": "<MALE|FEMALE|OTHER or null>"}}

      ━━━ YOUR RESPONSE (JSON only) ━━━"""


def pan_ocr_prompt() -> str:
    return f"""You are reading a photograph of an Indian PAN card.

      Extract exactly these four fields.

      | Field         | What to read                                                |
      |---------------|-------------------------------------------------------------|
      | name          | The cardholder's name as printed                             |
      | pan_number    | The 10-character PAN, e.g. ABCDE1234F. Uppercase, no spaces  |
      | date_of_birth | Date of Birth, as YYYY-MM-DD                                 |
      | father_name   | Father's Name, if the card prints one                        |

{COMMON_RULES}
      - Indian cards print dates as DD/MM/YYYY. "12/04/1995" is 12 April 1995
        -> "1995-04-12". It is NEVER 4 December. If the order is ambiguous
        (both parts <= 12) and nothing on the card settles it, return null.
      - PAN is exactly 5 letters, 4 digits, 1 letter. If it doesn't read that way, null.
      - Newer PAN cards omit the father's name — that is a legitimate null.

      ━━━ OUTPUT ━━━
      {{"name": "<text or null>", "pan_number": "<10 chars or null>",
        "date_of_birth": "<YYYY-MM-DD or null>", "father_name": "<text or null>"}}

      ━━━ YOUR RESPONSE (JSON only) ━━━"""


PROMPT_BUILDERS = {
    DocumentType.AADHAAR.value: aadhaar_ocr_prompt,
    DocumentType.PAN.value: pan_ocr_prompt,
}


def kyc_ocr_prompt(document_type: str) -> str:
    """Extraction prompt for a document type. KeyError is impossible from the
    router — `document_type` is already validated against the DocumentType enum."""
    return PROMPT_BUILDERS[document_type]()
