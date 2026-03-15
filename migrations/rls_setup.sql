-- ============================================================
-- RLS Setup — Auto Tech Lith SaaS
-- Sprint 1: Row-Level Security para isolamento entre tenants
--
-- Executar UMA VEZ após as migrations do Alembic.
-- Requer superuser ou role com BYPASSRLS para rodar.
-- ============================================================

-- Função helper que o PostgreSQL usa para obter o tenant atual
CREATE OR REPLACE FUNCTION current_tenant_id() RETURNS INTEGER AS $$
  SELECT current_setting('app.current_tenant', true)::INTEGER;
$$ LANGUAGE sql STABLE;

-- ────────────────────────────────────────────────
-- TABELAS DE NEGÓCIO — habilitar RLS
-- ────────────────────────────────────────────────

-- tickets
ALTER TABLE tickets ENABLE ROW LEVEL SECURITY;
ALTER TABLE tickets FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_tickets ON tickets;
CREATE POLICY tenant_isolation_tickets ON tickets
  USING (tenant_id = current_tenant_id())
  WITH CHECK (tenant_id = current_tenant_id());

-- conversations
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_conversations ON conversations;
CREATE POLICY tenant_isolation_conversations ON conversations
  USING (tenant_id = current_tenant_id())
  WITH CHECK (tenant_id = current_tenant_id());

-- customers
ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE customers FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_customers ON customers;
CREATE POLICY tenant_isolation_customers ON customers
  USING (tenant_id = current_tenant_id())
  WITH CHECK (tenant_id = current_tenant_id());

-- leads
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_leads ON leads;
CREATE POLICY tenant_isolation_leads ON leads
  USING (tenant_id = current_tenant_id())
  WITH CHECK (tenant_id = current_tenant_id());

-- agent_profiles
ALTER TABLE agent_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_profiles FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_agent_profiles ON agent_profiles;
CREATE POLICY tenant_isolation_agent_profiles ON agent_profiles
  USING (tenant_id = current_tenant_id())
  WITH CHECK (tenant_id = current_tenant_id());

-- meetings
ALTER TABLE meetings ENABLE ROW LEVEL SECURITY;
ALTER TABLE meetings FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_meetings ON meetings;
CREATE POLICY tenant_isolation_meetings ON meetings
  USING (tenant_id = current_tenant_id())
  WITH CHECK (tenant_id = current_tenant_id());

-- products
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE products FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_products ON products;
CREATE POLICY tenant_isolation_products ON products
  USING (tenant_id = current_tenant_id())
  WITH CHECK (tenant_id = current_tenant_id());

-- automation_rules
ALTER TABLE automation_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE automation_rules FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_automation_rules ON automation_rules;
CREATE POLICY tenant_isolation_automation_rules ON automation_rules
  USING (tenant_id = current_tenant_id())
  WITH CHECK (tenant_id = current_tenant_id());

-- vault_credentials
ALTER TABLE vault_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE vault_credentials FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_vault_credentials ON vault_credentials;
CREATE POLICY tenant_isolation_vault_credentials ON vault_credentials
  USING (tenant_id = current_tenant_id())
  WITH CHECK (tenant_id = current_tenant_id());

-- api_keys
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_api_keys ON api_keys;
CREATE POLICY tenant_isolation_api_keys ON api_keys
  USING (tenant_id = current_tenant_id())
  WITH CHECK (tenant_id = current_tenant_id());

-- ────────────────────────────────────────────────
-- TABELAS GLOBAIS — SEM RLS (acesso irrestrito)
-- ────────────────────────────────────────────────
-- tenants         → acesso via auth layer
-- butler_logs     → plataforma-wide
-- usage_logs      → plataforma-wide
-- admin_users     → auth layer controla

-- ────────────────────────────────────────────────
-- VERIFICAÇÃO
-- ────────────────────────────────────────────────
SELECT
  schemaname,
  tablename,
  rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN (
    'tickets', 'conversations', 'customers', 'leads',
    'agent_profiles', 'meetings', 'products',
    'automation_rules', 'vault_credentials', 'api_keys'
  )
ORDER BY tablename;
-- Todas devem mostrar rowsecurity = true
