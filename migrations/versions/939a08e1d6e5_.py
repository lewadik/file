"""add file expirations [creates legacy files]

Revision ID: 939a08e1d6e5
Revises: 7e246705da6a
Create Date: 2022-11-22 12:16:32.517184

"""

# revision identifiers, used by Alembic.
revision = '939a08e1d6e5'
down_revision = '7e246705da6a'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('file', sa.Column('expiration', sa.BigInteger()))


def downgrade():
    op.drop_column('file', 'expiration')
