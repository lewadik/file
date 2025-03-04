"""add URL secret

Revision ID: e2e816056589
Revises: 0659d7b9eea8
Create Date: 2022-12-01 02:16:15.976864

"""

# revision identifiers, used by Alembic.
revision = 'e2e816056589'
down_revision = '0659d7b9eea8'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('file', sa.Column('secret', sa.String(), nullable=True))


def downgrade():
    op.drop_column('file', 'secret')
