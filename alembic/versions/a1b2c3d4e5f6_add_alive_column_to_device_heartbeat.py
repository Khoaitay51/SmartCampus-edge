"""add_alive_column_to_device_heartbeat

Revision ID: a1b2c3d4e5f6
Revises: 4d2736916ddc
Create Date: 2026-09-04 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '4d2736916ddc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add alive column to device_heartbeat table."""
    op.add_column(
        'device_heartbeat',
        sa.Column('alive', sa.Boolean(), nullable=False, server_default=sa.text('true')),
    )


def downgrade() -> None:
    """Remove alive column from device_heartbeat table."""
    op.drop_column('device_heartbeat', 'alive')
