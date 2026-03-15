-- =============================================================================
-- Sprint 1: Row-Level Security — Isolamento de Tenant
-- Aplicar APÓS todas as migrations de schema existentes
-- =============================================================================

-- Habilitar RLS nas tabelas críticas de negócio
ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE tickets ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE meetings ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE lead_interactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE automation_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_ai_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_quotas ENABLE ROW LEVEL SECURITY;
ALTER TABLE vault_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE butler_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE meetings ENABLE ROW LEVEL SECURITY;

-- =============================================================================
-- Função auxiliar: extrai tenant_id do contexto da transação
-- Definida via SET LOCAL app.current_tenant = '123' antes de cada query
-- =============================================================================
CREATE OR REPLACE FUNCTION current_tenant_id() RETURNS INTEGER AS $$
BEGIN
    RETURN NULLIF(current_setting('app.current_tenant', true), '')::INTEGER;
EXCEPTION
    WHEN OTHERS THEN RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

-- =============================================================================
-- Políticas RLS por tabela
-- Padrão: SELECT/INSERT/UPDATE/DELETE filtrado por tenant_id
-- =============================================================================

-- customers
CREATE POLICY tenant_isolation_customers ON customers
    USING (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

-- tickets
CREATE POLICY tenant_isolation_tickets ON tickets
    USING (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

-- conversations
CREATE POLICY tenant_isolation_conversations ON conversations
    USING (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

-- meetings
CREATE POLICY tenant_isolation_meetings ON meetings
    USING (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

-- leads
CREATE POLICY tenant_isolation_leads ON leads
    USING (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

-- lead_interactions
CREATE POLICY tenant_isolation_lead_interactions ON lead_interactions
    USING (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

-- products
CREATE POLICY tenant_isolation_products ON products
    USING (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

-- automation_rules
CREATE POLICY tenant_isolation_automation_rules ON automation_rules
    USING (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

-- agent_profiles
CREATE POLICY tenant_isolation_agent_profiles ON agent_profiles
    USING (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

-- tenant_ai_configs
CREATE POLICY tenant_isolation_ai_configs ON tenant_ai_configs
    USING (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

-- tenant_quotas
CREATE POLICY tenant_isolation_quotas ON tenant_quotas
    USING (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

-- vault_credentials
CREATE POLICY tenant_isolation_vault ON vault_credentials
    USING (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

-- butler_logs (tenant pode ver apenas seus logs; NULL = plataforma)
CREATE POLICY tenant_isolation_butler_logs ON butler_logs
    USING (tenant_id IS NULL OR tenant_id = current_tenant_id());

-- usage_logs
CREATE POLICY tenant_isolation_usage_logs ON usage_logs
    USING (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

-- notifications
CREATE POLICY tenant_isolation_notifications ON notifications
    USING (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

-- =============================================================================
-- Superuser / service role bypassa RLS (para o Butler platform-level)
-- Em produção: app_user NÃO deve ser superuser
-- =============================================================================
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
-- REVOKE ALL ON tenants FROM app_user; -- tenants gerenciados só pelo backend

-- =============================================================================
-- Testar isolamento:
-- SET app.current_tenant = '1'; SELECT * FROM tickets; -- só tickets do tenant 1
-- SET app.current_tenant = '2'; SELECT * FROM tickets; -- só tickets do tenant 2
-- =============================================================================
