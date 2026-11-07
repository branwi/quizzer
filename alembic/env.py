from logging.config import fileConfig

import sqlalchemy as sa

from alembic import context
from app import models  # noqa: F401
from app.config import get_settings
from app.database import Base, UTCDateTime, make_engine

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)


def render_item(kind, item, _context):
    if kind == "type" and isinstance(item, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


if context.is_offline_mode():
    context.configure(
        url=get_settings().database_url,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = make_engine(get_settings().database_url)
    try:
        with engine.begin() as connection:
            if connection.dialect.name == "sqlite":
                connection.execute(sa.text("BEGIN IMMEDIATE"))
            context.configure(
                connection=connection,
                target_metadata=Base.metadata,
                compare_type=True,
                render_item=render_item,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
