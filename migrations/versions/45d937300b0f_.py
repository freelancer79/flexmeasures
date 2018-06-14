"""empty message

Revision ID: 45d937300b0f
Revises: a328412b4623
Create Date: 2018-05-07 18:18:59.555454

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "45d937300b0f"
down_revision = "a328412b4623"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "measurement",
        sa.Column("datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["asset.id"]),
        sa.PrimaryKeyConstraint("datetime", "asset_id"),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("measurement")
    # ### end Alembic commands ###
