"""add sgl2020 table

Revision ID: 2f29f98e533b
Revises: 6dd556a95d2b
Create Date: 2020-10-25 20:35:30.260165

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '2f29f98e533b'
down_revision = '6dd556a95d2b'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('sgl2020_tournament',
    sa.Column('episode_id', mysql.INTEGER(display_width=11), autoincrement=False, nullable=False),
    sa.Column('room_name', sa.String(length=100, collation='utf8_bin'), nullable=True),
    sa.Column('event', sa.String(length=45, collation='utf8_bin'), nullable=True),
    sa.Column('permalink', sa.String(length=200, collation='utf8_bin'), nullable=True),
    sa.Column('seed', sa.String(length=200, collation='utf8_bin'), nullable=True),
    sa.Column('status', sa.String(length=45, collation='utf8_bin'), nullable=True),
    sa.Column('created', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
    sa.Column('updated', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=True),
    sa.PrimaryKeyConstraint('episode_id'),
    sa.UniqueConstraint('room_name')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('sgl2020_tournament')
    # ### end Alembic commands ###