"""add file management token

Revision ID: 0659d7b9eea8
Revises: 939a08e1d6e5
Create Date: 2022-11-30 01:06:53.362973

"""

# revision identifiers, used by Alembic.
revision = '0659d7b9eea8'
down_revision = '939a08e1d6e5'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('file', sa.Column('mgmt_token', sa.String(), nullable=True))


def downgrade():
    op.drop_column('file', 'mgmt_token')
