from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config,pool
from production.tables import metadata
config=context.config

def run_migrations_online():
    engine=engine_from_config(config.get_section(config.config_ini_section),prefix='sqlalchemy.',poolclass=pool.NullPool)
    with engine.connect() as c:
        context.configure(connection=c,target_metadata=metadata,compare_type=True)
        with context.begin_transaction():context.run_migrations()
    engine.dispose()
if context.is_offline_mode():
    context.configure(url=config.get_main_option('sqlalchemy.url'),target_metadata=metadata,literal_binds=True)
    with context.begin_transaction():context.run_migrations()
else:run_migrations_online()
