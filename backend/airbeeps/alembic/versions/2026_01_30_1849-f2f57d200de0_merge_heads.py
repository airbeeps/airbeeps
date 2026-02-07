"""merge_heads

Revision ID: f2f57d200de0
Revises: tr4c35t0r4g3y, m0d3l_4n4lyt1c5
Create Date: 2026-01-30 18:49:01.384798

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import fastapi_users_db_sqlalchemy.generics


# revision identifiers, used by Alembic.
revision: str = "f2f57d200de0"
down_revision: Union[str, Sequence[str], None] = ("tr4c35t0r4g3y", "m0d3l_4n4lyt1c5")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
