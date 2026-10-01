"""add card_registration_requests table

Revision ID: c083fe7de714
Revises: 518593eef512
Create Date: 2026-09-28 14:08:57.245884

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c083fe7de714'
down_revision: Union[str, Sequence[str], None] = '518593eef512'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cardregistrationstatus') THEN
            CREATE TYPE cardregistrationstatus AS ENUM ('PENDING', 'APPROVED', 'REJECTED');
        END IF;
    END$$;

    CREATE TABLE IF NOT EXISTS card_registration_requests (
        request_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        card_uid VARCHAR NOT NULL,
        device_id UUID REFERENCES device(device_id),
        room_id UUID REFERENCES room(room_id),
        mac_address VARCHAR,
        status cardregistrationstatus NOT NULL DEFAULT 'PENDING',
        assigned_user_id UUID REFERENCES users(user_id),
        note VARCHAR,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ,
        processed_by UUID REFERENCES users(user_id)
    );

    CREATE INDEX IF NOT EXISTS ix_card_registration_requests_card_uid ON card_registration_requests(card_uid);
    CREATE INDEX IF NOT EXISTS ix_card_registration_requests_mac_address ON card_registration_requests(mac_address);
    CREATE INDEX IF NOT EXISTS ix_card_registration_requests_status ON card_registration_requests(status);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS card_registration_requests CASCADE;")
