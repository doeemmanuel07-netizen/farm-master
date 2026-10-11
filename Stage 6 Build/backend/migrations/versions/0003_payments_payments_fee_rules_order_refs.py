"""payments fee rules order refs

Revision ID: 0003_payments
Revises: 0002_reference_data
Create Date: 2026-10-11 13:47:13.667050

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003_payments'
down_revision: Union[str, Sequence[str], None] = '0002_reference_data'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Payments behind a provider interface, fee rules, FM-#### references (11 Oct 2026)."""
    # A new ENUM value can't be added inside the transaction that later uses
    # it, so it runs in an autocommit block of its own.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE requirementstatus ADD VALUE IF NOT EXISTS 'DELIVERED'")

    op.execute("CREATE SEQUENCE IF NOT EXISTS buyer_requirement_ref_seq START WITH 1001")

    op.create_table('commitment_fee_rules',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('basis', sa.Enum('PER_TONNE', 'PERCENT_OF_VALUE', name='feebasis'), nullable=False),
    sa.Column('rate', sa.Float(), nullable=False),
    sa.Column('minimum_amount', sa.Float(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.add_column('buyer_requirements', sa.Column('reference', sa.String(), nullable=True))
    op.add_column('buyer_requirements', sa.Column('crop_variety_id', sa.String(), nullable=True))
    op.add_column('buyer_requirements', sa.Column('spec_notes', sa.Text(), nullable=True))
    op.add_column('buyer_requirements', sa.Column('delivery_by', sa.Date(), nullable=True))
    op.create_unique_constraint('buyer_requirements_reference_key', 'buyer_requirements', ['reference'])
    op.create_foreign_key('buyer_requirements_crop_variety_id_fkey', 'buyer_requirements', 'crop_varieties', ['crop_variety_id'], ['id'])

    sa.Enum('MTN_MOMO', 'TELECEL_CASH', 'AT_MONEY', 'CARD', name='paymentnetwork').create(op.get_bind(), checkfirst=True)
    op.add_column('commitment_fee_payments', sa.Column('provider', sa.String(), nullable=True))
    op.add_column('commitment_fee_payments', sa.Column('network', sa.Enum('MTN_MOMO', 'TELECEL_CASH', 'AT_MONEY', 'CARD', name='paymentnetwork', create_type=False), nullable=True))
    op.add_column('commitment_fee_payments', sa.Column('payer_phone', sa.String(), nullable=True))
    op.add_column('commitment_fee_payments', sa.Column('provider_ref', sa.String(), nullable=True))
    op.add_column('commitment_fee_payments', sa.Column('checkout_url', sa.String(), nullable=True))
    op.add_column('commitment_fee_payments', sa.Column('failure_reason', sa.String(), nullable=True))
    op.add_column('commitment_fee_payments', sa.Column('webhook_payload', sa.Text(), nullable=True))
    op.add_column('commitment_fee_payments', sa.Column('paid_at', sa.DateTime(), nullable=True))
    op.add_column('commitment_fee_payments', sa.Column('updated_at', sa.DateTime(), nullable=True))
    op.create_unique_constraint('commitment_fee_payments_provider_ref_key', 'commitment_fee_payments', ['provider_ref'])

    # Pre-existing payments were all simulated mobile money: carry them over
    # into the new columns so the ops payments list reads them correctly.
    op.execute("""
        UPDATE commitment_fee_payments SET
            provider = 'sandbox',
            network = (CASE method WHEN 'vodafone' THEN 'TELECEL_CASH' WHEN 'airteltigo' THEN 'AT_MONEY'
                                   WHEN 'card' THEN 'CARD' ELSE 'MTN_MOMO' END)::paymentnetwork,
            provider_ref = transaction_ref,
            paid_at = CASE WHEN status = 'SUCCESS' THEN created_at END
        WHERE provider IS NULL
    """)


def downgrade() -> None:
    """Postgres can't drop a single ENUM value; DELIVERED stays on requirementstatus."""
    op.drop_constraint('commitment_fee_payments_provider_ref_key', 'commitment_fee_payments', type_='unique')
    for col in ('updated_at', 'paid_at', 'webhook_payload', 'failure_reason', 'checkout_url',
                'provider_ref', 'payer_phone', 'network', 'provider'):
        op.drop_column('commitment_fee_payments', col)
    sa.Enum(name='paymentnetwork').drop(op.get_bind(), checkfirst=True)
    op.drop_constraint('buyer_requirements_crop_variety_id_fkey', 'buyer_requirements', type_='foreignkey')
    op.drop_constraint('buyer_requirements_reference_key', 'buyer_requirements', type_='unique')
    for col in ('delivery_by', 'spec_notes', 'crop_variety_id', 'reference'):
        op.drop_column('buyer_requirements', col)
    op.drop_table('commitment_fee_rules')
    sa.Enum(name='feebasis').drop(op.get_bind(), checkfirst=True)
    op.execute("DROP SEQUENCE IF EXISTS buyer_requirement_ref_seq")
