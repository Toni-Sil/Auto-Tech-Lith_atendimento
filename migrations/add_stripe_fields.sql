-- Migration: adicionar campos Stripe na tabela tenants
-- Executar após alembic upgrade head

ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS stripe_customer_id     VARCHAR,
    ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR,
    ADD COLUMN IF NOT EXISTS stripe_plan            VARCHAR,
    ADD COLUMN IF NOT EXISTS stripe_status          VARCHAR DEFAULT 'inactive';

-- Index para lookup rápido por subscription_id (usado nos webhooks)
CREATE INDEX IF NOT EXISTS idx_tenants_stripe_subscription
    ON tenants (stripe_subscription_id);

-- Index para lookup por customer_id
CREATE INDEX IF NOT EXISTS idx_tenants_stripe_customer
    ON tenants (stripe_customer_id);

COMMENT ON COLUMN tenants.stripe_customer_id     IS 'Stripe Customer ID (cus_...)';
COMMENT ON COLUMN tenants.stripe_subscription_id IS 'Stripe Subscription ID (sub_...)';
COMMENT ON COLUMN tenants.stripe_plan            IS 'Plano ativo: starter | pro | scale';
COMMENT ON COLUMN tenants.stripe_status          IS 'Status Stripe: active | past_due | canceled | payment_failed';
