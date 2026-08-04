"""user_kyc: dedupe hash columns + document path

Revision ID: c9e1a4b7d306
Revises: b8d0f2c4e6a9
Create Date: 2026-08-01 12:00:00.000000

`user_kyc.aadhaar_number` / `pan_number` hold Fernet ciphertext, which is
randomised — encrypting the same Aadhaar twice yields different bytes. The
registration dedupe compared those columns for equality, so it never matched and
"KYC already linked to another account" (RM-AUTH-006) could not fire.

Adds `aadhaar_hash` / `pan_hash` (HMAC-SHA256 hex, deterministic, unique) and
backfills them from the existing ciphertext. The Fernet columns stay — they are
what makes the masked display possible.

Also adds `document_path` — the storage path of the OCR-captured KYC image in
the private bucket, so an admin can view the document when reviewing.

Backfill decrypts with the running environment's KYC_ENCRYPTION_KEY. A row that
cannot be decrypted (key rotated since it was written) is skipped and reported,
never fatal.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.config import settings
from app.core.security import decrypt_kyc, hmac_kyc

revision: str = "c9e1a4b7d306"
down_revision: Union[str, None] = "b8d0f2c4e6a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA

HASH_COLUMNS = (("aadhaar_number", "aadhaar_hash"), ("pan_number", "pan_hash"))


def upgrade() -> None:
    for _, hash_column in HASH_COLUMNS:
        op.add_column(
            "user_kyc",
            sa.Column(hash_column, sa.String(length=64), nullable=True),
            schema=SCHEMA,
        )
    op.add_column(
        "user_kyc",
        sa.Column("document_path", sa.Text(), nullable=True),
        schema=SCHEMA,
    )

    # ── Backfill from the existing ciphertext ────────────────────────────────
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            f"SELECT id, aadhaar_number, pan_number FROM {SCHEMA}.user_kyc "
            "WHERE aadhaar_number IS NOT NULL OR pan_number IS NOT NULL"
        )
    ).all()

    skipped = 0
    for row in rows:
        updates = {}
        for cipher_column, hash_column in HASH_COLUMNS:
            cipher = getattr(row, cipher_column)
            if not cipher:
                continue
            try:
                updates[hash_column] = hmac_kyc(decrypt_kyc(cipher))
            except (
                Exception
            ):  # noqa: BLE001 — a rotated key must not block the migration
                skipped += 1
        if updates:
            assignments = ", ".join(f"{col} = :{col}" for col in updates)
            connection.execute(
                sa.text(f"UPDATE {SCHEMA}.user_kyc SET {assignments} WHERE id = :id"),
                {**updates, "id": row.id},
            )

    print(
        f"  user_kyc backfill: {len(rows)} row(s) scanned, {skipped} value(s) skipped"
    )

    # Unique only after the backfill — a pre-existing duplicate would otherwise
    # abort the whole migration instead of surfacing as a data problem.
    for _, hash_column in HASH_COLUMNS:
        op.create_index(
            f"ix_user_kyc_{hash_column}",
            "user_kyc",
            [hash_column],
            unique=True,
            schema=SCHEMA,
        )


def downgrade() -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.user_kyc DROP COLUMN IF EXISTS document_path")
    for _, hash_column in HASH_COLUMNS:
        op.drop_index(
            f"ix_user_kyc_{hash_column}", table_name="user_kyc", schema=SCHEMA
        )
        op.drop_column("user_kyc", hash_column, schema=SCHEMA)
