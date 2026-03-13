// ════════════════════════════════════════════════════════════════
// SYSTEM CONFIG — Master Admin
// Carregado como módulo separado; só é executado na seção #configuracao
// ════════════════════════════════════════════════════════════════

/* global apiFetch, showAlert, setText */

// ── Navegação das abas internas ─────────────────────────────────
window.switchConfigTab = function (tabId, el) {
    document.querySelectorAll('#configuracao .config-tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('#configuracao .config-tab-panel').forEach(p => p.classList.remove('active'));
    el.classList.add('active');
    document.getElementById(tabId)?.classList.add('active');
};

// ── Load ───────────────────────────────────────────────────────────────
window.loadSystemConfig = async function () {
    try {
        const cfg = await apiFetch('/master/system-config');
        if (!cfg) return;

        const setV = (id, v) => { const el = document.getElementById(id); if (el) el.value = v ?? ''; };
        const setChk = (id, v) => { const el = document.getElementById(id); if (el) el.checked = (v === 'true' || v === true); };

        // Tab 1 — Credenciais
        setV('scOpenAIKey',       cfg.openai_api_key);
        setV('scOpenAIModel',     cfg.openai_model);
        setV('scEvolUrl',         cfg.evolution_api_url);
        setV('scEvolKey',         cfg.evolution_api_key);
        setV('scEvolInstance',    cfg.evolution_instance_name);
        setV('scVerifyToken',     cfg.verify_token);
        setV('scPublicUrl',       cfg.public_url);

        // Tab 2 — Tokens & Sessão
        setV('scAccessTTL',       cfg.access_token_expire_minutes);
        setV('scRefreshTTL',      cfg.refresh_token_expire_minutes);
        setChk('scDebug',         cfg.app_debug);
        updateTTLDisplay('scAccessTTL',  'scAccessTTLDisplay');
        updateTTLDisplay('scRefreshTTL', 'scRefreshTTLDisplay');

        // Tab 3 — SMTP
        setV('scSmtpServer',   cfg.smtp_server);
        setV('scSmtpPort',     cfg.smtp_port);
        setV('scSmtpUser',     cfg.smtp_user);
        setV('scSmtpPassword', cfg.smtp_password);

        // Tab 4 — CORS
        setV('scPublicUrlCors', cfg.public_url);
        renderCorsOrigins(cfg.backend_cors_origins);

    } catch (e) {
        showAlert('Erro ao carregar configurações: ' + e.message, 'error');
    }
};

// ── Save ───────────────────────────────────────────────────────────────
window.saveSystemConfig = async function (section) {
    const gV = id => document.getElementById(id)?.value?.trim() ?? '';
    const gChk = id => String(document.getElementById(id)?.checked ?? false);

    let configs = {};

    if (section === 'credentials') {
        configs = {
            openai_api_key:          gV('scOpenAIKey'),
            openai_model:            gV('scOpenAIModel'),
            evolution_api_url:       gV('scEvolUrl'),
            evolution_api_key:       gV('scEvolKey'),
            evolution_instance_name: gV('scEvolInstance'),
            verify_token:            gV('scVerifyToken'),
            public_url:              gV('scPublicUrl'),
        };
    } else if (section === 'session') {
        configs = {
            access_token_expire_minutes:  gV('scAccessTTL'),
            refresh_token_expire_minutes: gV('scRefreshTTL'),
            app_debug:                    gChk('scDebug'),
        };
    } else if (section === 'smtp') {
        configs = {
            smtp_server:   gV('scSmtpServer'),
            smtp_port:     gV('scSmtpPort'),
            smtp_user:     gV('scSmtpUser'),
            smtp_password: gV('scSmtpPassword'),
        };
    } else if (section === 'cors') {
        const origins = getCorsOrigins();
        configs = {
            backend_cors_origins: JSON.stringify(origins),
            public_url:           gV('scPublicUrlCors'),
        };
    }

    try {
        const res = await apiFetch('/master/system-config', {
            method: 'POST',
            body: JSON.stringify({ configs }),
        });
        if (res) showAlert(`✅ Configurações salvas! (${res.updated?.length ?? 0} chaves atualizadas)`, 'success');
    } catch (e) {
        showAlert('Erro ao salvar: ' + e.message, 'error');
    }
};

// ── Test connection ─────────────────────────────────────────────────────
window.testConfigKey = async function (key, inputId, btnId) {
    const btn = document.getElementById(btnId);
    const val = document.getElementById(inputId)?.value?.trim();
    if (!val) { showAlert('Preencha o campo antes de testar.', 'error'); return; }

    if (btn) { btn.disabled = true; btn.textContent = 'Testando...'; }
    try {
        const res = await apiFetch('/master/system-config/test-connection', {
            method: 'POST',
            body: JSON.stringify({ key, value: val }),
        });
        showAlert(res?.message ?? 'Sem resposta', res?.ok ? 'success' : 'error');
    } catch (e) {
        showAlert('Erro no teste: ' + e.message, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '⚡ Testar'; }
    }
};

// ── CORS origins ──────────────────────────────────────────────────────────
window.renderCorsOrigins = function (rawValue) {
    const list = document.getElementById('corsList');
    if (!list) return;
    let origins = [];
    try { origins = JSON.parse(rawValue || '[]'); } catch { origins = []; }
    list.innerHTML = origins.map((o, i) => `
        <div class="cors-item" data-origin="${o}">
            <span class="mono text-sm" style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${o}</span>
            <button class="btn btn-ghost btn-sm" style="color:var(--red);padding:0 .4rem" onclick="removeCorsOrigin(${i})">✕</button>
        </div>`).join('');
};

window.getCorsOrigins = function () {
    return [...document.querySelectorAll('#corsList .cors-item')].map(el => el.dataset.origin);
};

window.addCorsOrigin = function () {
    const input = document.getElementById('newCorsOrigin');
    const val = input?.value?.trim();
    if (!val) return;
    const origins = getCorsOrigins();
    if (origins.includes(val)) { showAlert('Origem já existe na lista.', 'error'); return; }
    renderCorsOrigins(JSON.stringify([...origins, val]));
    if (input) input.value = '';
};

window.removeCorsOrigin = function (idx) {
    const origins = getCorsOrigins();
    origins.splice(idx, 1);
    renderCorsOrigins(JSON.stringify(origins));
};

// ── TTL slider display ─────────────────────────────────────────────────────
window.updateTTLDisplay = function (sliderId, displayId) {
    const el = document.getElementById(sliderId);
    const disp = document.getElementById(displayId);
    if (!el || !disp) return;
    const mins = parseInt(el.value) || 0;
    if (mins < 60) disp.textContent = `${mins}m`;
    else if (mins < 1440) disp.textContent = `${(mins / 60).toFixed(1)}h`;
    else disp.textContent = `${(mins / 1440).toFixed(1)}d`;
};
