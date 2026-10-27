"""Initial production schema; future schema changes require new revisions."""
from alembic import op
from production.tables import metadata
revision='0001_initial'
down_revision=None
branch_labels=None
depends_on=None

def upgrade():metadata.create_all(bind=op.get_bind())

def downgrade():
    raise RuntimeError('Destructive clinical data migration deliberately prohibited')
