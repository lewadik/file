"""add file expirations [creates legacy files]

Revision ID: 939a08e1d6e5
Revises: 7e246705da6a
Create Date: 2022-11-22 12:16:32.517184

"""

# revision identifiers, used by Alembic.
revision = '939a08e1d6e5'
down_revision = '7e246705da6a'

from alembic import op
from flask import current_app
from flask_sqlalchemy import SQLAlchemy
from pathlib import Path
import sqlalchemy as sa
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import Session

import os
import time

""" For a file of a given size, determine the largest allowed lifespan of that file

Based on the current app's configuration:  Specifically, the MAX_CONTENT_LENGTH, as well
as FHOST_{MIN,MAX}_EXPIRATION.

This lifespan may be shortened by a user's request, but no files should be allowed to
expire at a point after this number.

Value returned is a duration in milliseconds.
"""
def get_max_lifespan(filesize: int) -> int:
    min_exp = current_app.config.get("FHOST_MIN_EXPIRATION", 30 * 24 * 60 * 60 * 1000)
    max_exp = current_app.config.get("FHOST_MAX_EXPIRATION", 365 * 24 * 60 * 60 * 1000)
    max_size = current_app.config.get("MAX_CONTENT_LENGTH", 256 * 1024 * 1024)
    return min_exp + int((-max_exp + min_exp) * (filesize / max_size - 1) ** 3)

db = SQLAlchemy(current_app.__weakref__())

# Representation of the updated (future) File table
UpdatedFile = sa.table('file',
    # We only need to describe the columns that are relevent to us
    sa.column('id', db.Integer),
    sa.column('expiration', db.BigInteger)
)

Base = automap_base()

def upgrade():
    op.add_column('file', sa.Column('expiration', sa.BigInteger()))

    bind = op.get_bind()
    Base.prepare(autoload_with=bind)
    File = Base.classes.file
    session = Session(bind=bind)

    storage = Path(current_app.config["FHOST_STORAGE_PATH"])
    current_time = time.time() * 1000;

    # List of file hashes which have not expired yet
    # This could get really big for some servers
    unexpired_files = set(os.listdir(storage))

    # Calculate an expiration date for all existing files
    files = session.scalars(
            sa.select(File)
            .where(
                sa.not_(File.removed)
            )
        )
    for file in files:
        if file.sha256 in unexpired_files:
            file_path = storage / file.sha256
            stat = os.stat(file_path)
            max_age = get_max_lifespan(stat.st_size) # How long the file is allowed to live, in ms
            file_birth = stat.st_mtime * 1000 # When the file was created, in ms
            op.execute(
                sa.update(UpdatedFile)
                    .where(UpdatedFile.c.id == file.id)
                    .values({'expiration': int(file_birth + max_age)})
            )

def downgrade():
    op.drop_column('file', 'expiration')
