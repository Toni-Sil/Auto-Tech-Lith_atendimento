// ═══════════════════════════════════════════════════════════════
// SYSTEM CONFIG — Master Admin · Auto Tech Lith
// Carregado junto ao master.js
// ═══════════════════════════════════════════════════════════════

// ── Aba ativa ─────────────────────────────────────────────────
window.switchSysTab = function (tab, el) {
    document.querySelectorAll('.sys-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.sys-panel').forEach(p => p.classList.remove('active'));
    el.classList.add('active');
    document.getElementById('syspanel-' + tab)?.classList.add('active');
};

// ── Carregar configurações ─────────────────────────────────────
window.loadSystemConfig = async function () {
    try {
        const cfg = await apiFetch('/master/system-config');
        if (!cfg) return;

        const sv = (id, v) => { const el = document.getElementById(id); if (el) el.value = v ?? ''; };
        const sc = (id, v) => { const el = document.getElementById(id); if (el) el.checked = !!v; };

        // APIs
        sv('scOpenAiKey', cfg.openai_api_key);
        sv('scOpenAiModel', cfg.openai_model);
        sv('scEvolUrl', cfg.evolution_api_url);
        sv('scEvolKey', cfg.evolution_api_key);
        sv('scVerifyToken', cfg.verify_token);
        sv('scPublicUrl', cfg.public_url);

        // Sessão
        sv('scAccessExp', cfg.access_token_expire_minutes);
        sv('scRefreshExp', cfg.refresh_token_expire_minutes);
        sc('scDebug', cfg.app_debug);
        sv('scCors', cfg.backend_cors_origins);
        sv('scWhitelist', cfg.rate_limit_whitelist);

        // SMTP
        sv('scSmtpServer', cfg.smtp_server);
        sv('scSmtpPort', cfg.smtp_port);
        sv('scSmtpUser', cfg.smtp_user);

        // Preview badge debug
        const badge = document.getElementById('scDebugBadge');
        if (badge) {
            badge.textContent = cfg.app_debug ? '🟡 DEBUG ON' : '🟢 PRODUÇÃO';
            badge.className = 'badge ' + (cfg.app_debug ? 'warn' : 'active');
        }
    } catch (e) {
        showAlert('Erro ao carregar configurações do sistema: ' + e.message, 'error');
    }
};

// ── Salvar configurações ────────────────────────────────────────
window.saveSystemConfig = async function () {
    const gv = id => document.getElementById(id)?.value?.trim() ?? null;
    const gb = id => document.getElementById(id)?.checked ?? false;
    const gi = id => { const v = parseInt(document.getElementById(id)?.value); return isNaN(v) ? null : v; };

    const payload = {
        openai_api_key: gv('scOpenAiKey') || null,
        openai_model: gv('scOpenAiModel') || null,
        evolution_api_url: gv('scEvolUrl') || null,
        evolution_api_key: gv('scEvolKey') || null,
        verify_token: gv('scVerifyToken') || null,
        public_url: gv('scPublicUrl') || null,
        access_token_expire_minutes: gi('scAccessExp'),
        refresh_token_expire_minutes: gi('scRefreshExp'),
        app_debug: gb('scDebug'),
        backend_cors_origins: gv('scCors') || null,
        rate_limit_whitelist: gv('scWhitelist') || null,
        smtp_server: gv('scSmtpServer') || null,
        smtp_port: gi('scSmtpPort'),
        smtp_user: gv('scSmtpUser') || null,
        smtp_password: gv('scSmtpPassword') || null,
    };

    // Remove nulls para não sobrescrever campos não alterados
    Object.keys(payload).forEach(k => payload[k] === null && delete payload[k]);

    const btn = document.getElementById('scSaveBtn');
    if (btn) { btn.disabled = true; btn.textContent = '💾 Salvando...'; }

    try {
        const res = await apiFetch('/master/system-config', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        if (res) {
            showAlert('✅ Configurações salvas! ' + (res.message || ''), 'success');
            loadSystemConfig(); // Recarregar para refletir mascaramento
        }
    } catch (e) {
        showAlert('Erro ao salvar: ' + e.message, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '💾 Salvar Configurações'; }
    }
};

// ── Testar conexão OpenAI ───────────────────────────────────────
window.testOpenAI = async function () {
    const btn = document.getElementById('btnTestOpenAI');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Testando...'; }
    try {
        const res = await apiFetch('/master/test/openai', { method: 'POST' });
        if (res?.status === 'ok') showAlert('✅ OpenAI OK — modelo: ' + (res.model || '?'), 'success');
        else showAlert('❌ Erro OpenAI: ' + (res?.detail || 'Falhou'), 'error');
    } catch (e) {
        showAlert('❌ OpenAI inacessível: ' + e.message, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '⚡ Testar OpenAI'; }
    }
};

// ── Testar conexão Evolution API ────────────────────────────────
window.testEvolution = async function () {
    const btn = document.getElementById('btnTestEvol');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Testando...'; }
    try {
        const res = await apiFetch('/master/test/evolution', { method: 'POST' });
        if (res?.status === 'ok') showAlert('✅ Evolution API OK!', 'success');
        else showAlert('❌ Erro Evolution: ' + (res?.detail || 'Falhou'), 'error');
    } catch (e) {
        showAlert('❌ Evolution inacessível: ' + e.message, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '⚡ Testar Evolution'; }
    }
};

// ── Testar SMTP ─────────────────────────────────────────────────
window.testSMTP = async function () {
    const btn = document.getElementById('btnTestSMTP');
    const dest = prompt('Enviar e-mail de teste para:');
    if (!dest) return;
    if (btn) { btn.disabled = true; btn.textContent = '📧 Enviando...'; }
    try {
        const res = await apiFetch('/master/test/smtp', {
            method: 'POST',
            body: JSON.stringify({ email: dest })
        });
        if (res?.status === 'ok') showAlert('✅ E-mail de teste enviado para ' + dest, 'success');
        else showAlert('❌ Erro SMTP: ' + (res?.detail || 'Falhou'), 'error');
    } catch (e) {
        showAlert('❌ SMTP erro: ' + e.message, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '📧 Testar SMTP'; }
    }
};

// Expor para o nav
window.loadSystemConfig = window.loadSystemConfig;
