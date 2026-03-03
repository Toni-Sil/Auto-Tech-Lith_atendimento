// =============================================================
// AGENT PROFILES — Agentes independentes por perfil
// =============================================================
let profilesData = [];
let editingProfileId = null;

const CHANNEL_LABELS = {
    whatsapp: '📱 WhatsApp',
    telegram: '✈️ Telegram',
    web: '🌐 Web Chat',
    instagram: '📸 Instagram',
    email: '📧 E-mail',
};

async function loadProfiles() {
    try {
        const res = await authFetch(`${API_BASE}/profiles`);
        if (!res) return;
        profilesData = await res.json();
        renderProfiles();
    } catch (e) {
        console.error('Erro ao carregar perfis:', e);
    }
}

function renderProfiles() {
    const container = document.getElementById('profilesList');
    if (!profilesData.length) {
        container.innerHTML = `
            <div style="grid-column:1/-1;text-align:center;padding:4rem 2rem;color:var(--text-muted);">
                <div style="font-size:3rem;margin-bottom:1rem;">🤖</div>
                <p style="font-size:1rem;font-weight:600;margin:0 0 0.5rem;">Nenhum agente criado ainda</p>
                <p style="font-size:0.85rem;margin:0;">Clique em "+ Novo Agente" para criar seu primeiro agente personalizado.</p>
            </div>`;
        return;
    }
    container.innerHTML = profilesData.map(p => {
        const avatar = p.agent_avatar || '🤖';
        const displayName = p.agent_name_display || p.name;
        const channel = CHANNEL_LABELS[p.channel] || '📱 WhatsApp';
        return `
        <div class="agent-card${p.is_active ? ' is-active' : ''}">
            ${p.is_active ? '<div class="active-badge-pill">● Ativo</div>' : ''}
            <div class="agent-card-header">
                <div class="agent-avatar-big">${avatar}</div>
                <div>
                    <div class="agent-card-title">${displayName}</div>
                    <div class="agent-card-subtitle">${p.name} · ${channel}</div>
                </div>
            </div>
            <div class="agent-card-body">
                <p class="agent-card-desc">${p.objective || 'Objetivo não definido para este agente.'}</p>
                <div class="agent-card-tags">
                    <span class="agent-tag">${p.niche}</span>
                <div class="agent-card-tags">
                    <span class="agent-tag">${p.niche}</span>
                    <span class="agent-tag">${p.tone}</span>
                    <span class="agent-tag">Formalidade: ${p.formality}</span>
                    <span class="agent-tag">Autonomia: ${p.autonomy_level}</span>
                </div>
            </div>
            <div class="agent-card-footer">
                <button class="btn-secondary btn-sm" onclick="editProfile(${p.id})">✏️ Editar</button>
                ${!p.is_active
                ? `<button class="btn-primary btn-sm" onclick="activateProfile(${p.id})" style="margin-left:auto;">⚡ Ativar</button>`
                : `<span style="margin-left:auto;font-size:0.75rem;color:var(--success);font-weight:600;">✅ Respondendo agora</span>`}
            </div>
        </div>`;
    }).join('');
}

function openProfileModal() {
    editingProfileId = null;
    document.getElementById('profileModalTitle').textContent = 'Novo Agente';
    document.getElementById('profileModalEmoji').textContent = '🤖';
    document.getElementById('profileAvatar').value = '🤖';
    document.getElementById('profileAgentName').value = '';
    document.getElementById('profileName').value = '';
    document.getElementById('profileChannel').value = 'whatsapp';
    document.getElementById('profileNiche').value = 'geral';
    document.getElementById('profileTone').value = 'neutro';
    document.getElementById('profileFormality').value = 'equilibrado';
    document.getElementById('profileAutonomy').value = 'equilibrada';
    document.getElementById('profileObjective').value = '';
    document.getElementById('profileAudience').value = '';
    document.getElementById('profileDataCollect').value = '';
    document.getElementById('profileConstraints').value = '';
    document.getElementById('profilePrompt').value = '';
    document.getElementById('btnDeleteProfile').style.display = 'none';
    document.getElementById('profileModal').classList.add('active');
}

function editProfile(id) {
    const p = profilesData.find(x => x.id === id);
    if (!p) return;
    editingProfileId = id;
    document.getElementById('profileModalTitle').textContent = 'Editar Agente';
    const avatar = p.agent_avatar || '🤖';
    document.getElementById('profileModalEmoji').textContent = avatar;
    document.getElementById('profileAvatar').value = avatar;
    document.getElementById('profileAgentName').value = p.agent_name_display || '';
    document.getElementById('profileName').value = p.name;
    document.getElementById('profileChannel').value = p.channel || 'whatsapp';
    document.getElementById('profileNiche').value = p.niche;
    document.getElementById('profileTone').value = p.tone;
    document.getElementById('profileFormality').value = p.formality;
    document.getElementById('profileAutonomy').value = p.autonomy_level;
    document.getElementById('profileObjective').value = p.objective || '';
    document.getElementById('profileAudience').value = p.target_audience || '';
    document.getElementById('profileDataCollect').value = (p.data_to_collect || []).join(', ');
    document.getElementById('profileConstraints').value = p.constraints || '';
    document.getElementById('profilePrompt').value = p.base_prompt || '';
    document.getElementById('btnDeleteProfile').style.display = 'block';
    document.getElementById('profileModal').classList.add('active');
}

function closeProfileModal() {
    document.getElementById('profileModal').classList.remove('active');
}

async function saveProfile(e) {
    e.preventDefault();
    const dataCollectRaw = document.getElementById('profileDataCollect').value;
    const dataToCollect = dataCollectRaw ? dataCollectRaw.split(',').map(s => s.trim()).filter(Boolean) : [];
    const body = {
        name: document.getElementById('profileName').value,
        agent_name_display: document.getElementById('profileAgentName').value,
        agent_avatar: document.getElementById('profileAvatar').value || '🤖',
        channel: document.getElementById('profileChannel').value,
        niche: document.getElementById('profileNiche').value,
        tone: document.getElementById('profileTone').value,
        formality: document.getElementById('profileFormality').value,
        autonomy_level: document.getElementById('profileAutonomy').value,
        objective: document.getElementById('profileObjective').value,
        target_audience: document.getElementById('profileAudience').value,
        data_to_collect: dataToCollect,
        constraints: document.getElementById('profileConstraints').value,
        base_prompt: document.getElementById('profilePrompt').value,
    };
    const method = editingProfileId ? 'PUT' : 'POST';
    const url = editingProfileId ? `${API_BASE}/profiles/${editingProfileId}` : `${API_BASE}/profiles`;
    try {
        const res = await authFetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        if (!res || !res.ok) throw new Error('Falha');
        showAlert(editingProfileId ? '✅ Agente atualizado!' : '✅ Agente criado!', 'success');
        closeProfileModal();
        loadProfiles();
    } catch {
        showAlert('❌ Erro ao salvar agente', 'error');
    }
}

async function activateProfile(id) {
    try {
        const res = await authFetch(`${API_BASE}/profiles/${id}/activate`, { method: 'POST' });
        if (!res || !res.ok) throw new Error('Falha');
        showAlert('⚡ Agente ativado! Respostas serão com este agente.', 'success');
        loadProfiles();
    } catch {
        showAlert('❌ Erro ao ativar agente', 'error');
    }
}

async function deleteProfileFromModal() {
    if (!editingProfileId || !confirm('Excluir este agente?')) return;
    try {
        await authFetch(`${API_BASE}/profiles/${editingProfileId}`, { method: 'DELETE' });
        showAlert('Agente excluído.', 'success');
        closeProfileModal();
        loadProfiles();
    } catch {
        showAlert('Erro ao excluir. Certifique-se que não está ativo.', 'error');
    }
}

// =============================================================
// WEBHOOKS & APIs — com abas e tipos
// =============================================================
let webhooksData = [];
let editingWebhookId = null;
let currentWebhookTab = 'webhooks';

/**
 * Alterna entre as abas Webhook (saída) e API (entrada)
 */
function switchWebhookTab(tab) {
    currentWebhookTab = tab;
    document.getElementById('tabWebhooks').classList.toggle('active', tab === 'webhooks');
    document.getElementById('tabApis').classList.toggle('active', tab === 'apis');
    document.getElementById('webhookPanel').style.display = tab === 'webhooks' ? '' : 'none';
    document.getElementById('apiPanel').style.display = tab === 'apis' ? '' : 'none';

    const btn = document.getElementById('btnNewWebhook');
    if (tab === 'apis') {
        btn.textContent = '+ Nova Integração (API)';
    } else {
        btn.textContent = '+ Novo Webhook';
    }
    renderWebhooks();
}

async function loadWebhooks() {
    try {
        const res = await authFetch(`${API_BASE}/webhooks`);
        if (!res) return;
        webhooksData = await res.json();
        renderWebhooks();
    } catch (e) {
        console.error('Erro ao carregar webhooks:', e);
    }
}

function renderWebhooks() {
    const isApiTab = currentWebhookTab === 'apis';
    const filtered = webhooksData.filter(w => {
        const t = w.type || 'webhook';
        return isApiTab ? t === 'api' : t !== 'api';
    });
    const bodyId = isApiTab ? 'apisBody' : 'webhooksBody';
    const tbody = document.getElementById(bodyId);
    if (!tbody) return;

    if (!filtered.length) {
        const label = isApiTab ? 'integração (API)' : 'webhook';
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text-faint);padding:2rem;">Nenhum ${label} configurado ainda.</td></tr>`;
        return;
    }
    tbody.innerHTML = filtered.map(w => {
        const statusColor = w.last_test_status === 'ok' ? 'var(--success)' : w.last_test_status === 'error' ? 'var(--danger)' : 'var(--text-faint)';
        const statusText = w.last_test_status === 'ok' ? '✅ OK' : w.last_test_status === 'error' ? '❌ Erro' : '—';
        const lastTest = w.last_tested_at ? new Date(w.last_tested_at).toLocaleString('pt-BR') : 'Nunca';
        return `<tr>
            <td><strong>${w.name}</strong></td>
            <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-muted);font-size:0.82rem;" title="${w.url}">${w.url}</td>
            <td><span style="font-family:monospace;background:var(--content-bg);padding:2px 7px;border-radius:5px;font-size:0.8rem;">${w.method}</span></td>
            <td>${w.is_active ? '<span class="badge active">Ativo</span>' : '<span class="badge inactive">Inativo</span>'}</td>
            <td><span style="color:${statusColor};font-size:0.82rem;">${statusText}</span><div style="font-size:0.72rem;color:var(--text-faint);">${lastTest}</div></td>
            <td><div style="display:flex;gap:6px;">
                <button class="btn-secondary btn-sm" onclick="editWebhook(${w.id})">Editar</button>
                <button class="btn-secondary btn-sm" onclick="quickTestWebhook(${w.id})">Testar</button>
            </div></td>
        </tr>`;
    }).join('');
}

function updateWebhookModalType() {
    const type = document.getElementById('webhookType').value;
    const hint = document.getElementById('webhookTypeHint');
    const icon = document.getElementById('webhookModalIcon');
    if (type === 'api') {
        icon.textContent = '🔌';
        hint.className = 'info-banner purple';
        hint.innerHTML = '<strong>API / Integração (Entrada):</strong> Um sistema externo (CRM, formulário, app) vai chamar uma URL deste servidor para enviar dados ao agente. Documente aqui para controle e monitoramento.';
    } else {
        icon.textContent = '🔔';
        hint.className = 'info-banner blue';
        hint.innerHTML = '<strong>Webhook (Saída):</strong> Este sistema vai notificar a URL acima quando eventos acontecerem (nova mensagem, reunião agendada, etc.). Configure a URL do seu sistema receptor.';
    }
}

function openWebhookModal() {
    editingWebhookId = null;
    document.getElementById('webhookModalTitle').textContent = 'Novo Webhook / API';
    document.getElementById('webhookType').value = currentWebhookTab === 'apis' ? 'api' : 'webhook';
    document.getElementById('webhookName').value = '';
    document.getElementById('webhookUrl').value = '';
    document.getElementById('webhookMethod').value = 'POST';
    document.getElementById('webhookToken').value = '';
    document.getElementById('webhookEvents').value = '';
    document.getElementById('webhookActive').checked = true;
    document.getElementById('btnDeleteWebhook').style.display = 'none';
    document.getElementById('webhookTestResult').style.display = 'none';
    updateWebhookModalType();
    document.getElementById('webhookModal').classList.add('active');
}

function editWebhook(id) {
    const w = webhooksData.find(x => x.id === id);
    if (!w) return;
    editingWebhookId = id;
    document.getElementById('webhookModalTitle').textContent = 'Editar';
    document.getElementById('webhookType').value = w.type || 'webhook';
    document.getElementById('webhookName').value = w.name;
    document.getElementById('webhookUrl').value = w.url;
    document.getElementById('webhookMethod').value = w.method;
    document.getElementById('webhookToken').value = w.token || '';
    document.getElementById('webhookEvents').value = (w.events || []).join(', ');
    document.getElementById('webhookActive').checked = w.is_active;
    document.getElementById('btnDeleteWebhook').style.display = 'block';
    document.getElementById('webhookTestResult').style.display = 'none';
    updateWebhookModalType();
    document.getElementById('webhookModal').classList.add('active');
}

function closeWebhookModal() {
    document.getElementById('webhookModal').classList.remove('active');
}

async function saveWebhook(e) {
    e.preventDefault();
    const eventsRaw = document.getElementById('webhookEvents').value;
    const body = {
        name: document.getElementById('webhookName').value,
        url: document.getElementById('webhookUrl').value,
        method: document.getElementById('webhookMethod').value,
        token: document.getElementById('webhookToken').value || null,
        events: eventsRaw ? eventsRaw.split(',').map(s => s.trim()).filter(Boolean) : [],
        is_active: document.getElementById('webhookActive').checked,
        type: document.getElementById('webhookType').value,
    };
    const method = editingWebhookId ? 'PUT' : 'POST';
    const url = editingWebhookId ? `${API_BASE}/webhooks/${editingWebhookId}` : `${API_BASE}/webhooks`;
    try {
        const res = await authFetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        if (!res || !res.ok) throw new Error('Falha');
        showAlert(editingWebhookId ? '✅ Atualizado!' : '✅ Criado com sucesso!', 'success');
        closeWebhookModal();
        loadWebhooks();
    } catch {
        showAlert('❌ Erro ao salvar', 'error');
    }
}

async function testCurrentWebhook() {
    if (!editingWebhookId) { showAlert('Salve primeiro para testar.', 'error'); return; }
    await quickTestWebhook(editingWebhookId, true);
}

async function quickTestWebhook(id, showInModal = false) {
    try {
        const res = await authFetch(`${API_BASE}/webhooks/${id}/test`, { method: 'POST' });
        const result = await res.json();
        if (showInModal) {
            const el = document.getElementById('webhookTestResult');
            el.style.display = 'block';
            el.style.background = result.status === 'ok' ? '#d1fae5' : '#fee2e2';
            el.style.color = result.status === 'ok' ? '#065f46' : '#991b1b';
            el.textContent = result.status === 'ok'
                ? `✅ Conexão OK (HTTP ${result.http_status}): ${result.response || ''}`
                : `❌ Falha: ${result.message || result.response || 'Erro desconhecido'}`;
        } else {
            showAlert(result.status === 'ok' ? '✅ OK!' : `❌ ${result.message || 'Falha'}`, result.status === 'ok' ? 'success' : 'error');
            loadWebhooks();
        }
    } catch {
        showAlert('❌ Erro ao testar', 'error');
    }
}

async function deleteWebhookFromModal() {
    if (!editingWebhookId || !confirm('Excluir?')) return;
    try {
        await authFetch(`${API_BASE}/webhooks/${editingWebhookId}`, { method: 'DELETE' });
        showAlert('Excluído.', 'success');
        closeWebhookModal();
        loadWebhooks();
    } catch {
        showAlert('❌ Erro ao excluir', 'error');
    }
}

// =============================================================
// PROMPT WIZARD (8 steps)
// =============================================================
const WIZARD_STEPS = [
    {
        key: 'niche', label: 'Qual é o nicho do negócio?', type: 'select',
        options: [
            { v: 'geral', l: 'Geral / Outros' }, { v: 'imobiliario', l: '🏠 Imobiliário' },
            { v: 'saude', l: '⚕️ Saúde e Bem-estar' }, { v: 'educacao', l: '📚 Educação e Cursos' },
            { v: 'ecommerce', l: '🛒 E-commerce e Varejo' }, { v: 'tecnologia', l: '💻 Tecnologia / SaaS' },
            { v: 'financeiro', l: '💰 Financeiro e Seguros' }, { v: 'juridico', l: '⚖️ Jurídico / Advocacia' },
            { v: 'restaurante', l: '🍽️ Restaurante / Food' }, { v: 'automacao', l: '🤖 Automação e IA' },
        ]
    },
    {
        key: 'tone', label: 'Tom de comunicação do agente?', type: 'select',
        options: [
            { v: 'neutro', l: '😐 Neutro e Direto' }, { v: 'formal', l: '👔 Formal' },
            { v: 'semi-formal', l: '🤝 Semi-formal' }, { v: 'amigavel', l: '😊 Amigável' },
            { v: 'jovem', l: '🧢 Jovem / Informal' },
        ]
    },
    {
        key: 'formality', label: 'Nível de formalidade', type: 'select',
        options: [
            { v: 'muito_informal', l: 'Muito Informal' },
            { v: 'informal', l: 'Informal' },
            { v: 'equilibrado', l: 'Equilibrado' },
            { v: 'formal', l: 'Formal' },
            { v: 'muito_formal', l: 'Muito Formal' }
        ],
        default: 'equilibrado'
    },
    {
        key: 'autonomy_level', label: 'Autonomia do agente', type: 'select',
        options: [
            { v: 'estrita', l: 'Nenhuma (Estritamente ao script)' },
            { v: 'orientada', l: 'Orientada (Sugestões simples)' },
            { v: 'equilibrada', l: 'Equilibrada (Resolve a maioria sozinho)' },
            { v: 'proativa', l: 'Proativa (Toma iniciativa)' },
            { v: 'independente', l: 'Independente (Alta liberdade/negociação)' }
        ],
        default: 'equilibrada'
    },
    { key: 'company_name', label: 'Nome da empresa', type: 'text', placeholder: 'Ex: Studio Criativo XYZ' },
    { key: 'agent_name', label: 'Nome do agente virtual', type: 'text', placeholder: 'Ex: Sofia, Max, Luna...' },
    { key: 'objective', label: 'Objetivo principal do atendimento?', type: 'textarea', placeholder: 'Ex: Qualificar leads e agendar reuniões de briefing.' },
    { key: 'data_to_collect', label: 'Dados a coletar (separados por vírgula)', type: 'text', placeholder: 'Ex: Nome, E-mail, Empresa, Orçamento' },
];

let wizardStep = 0;
let wizardAnswers = {};

function initWizard() {
    wizardStep = 0;
    wizardAnswers = {};
    document.getElementById('wizardPreview').style.display = 'none';
    renderWizardStep();
}

function renderWizardStep() {
    const step = WIZARD_STEPS[wizardStep];
    const total = WIZARD_STEPS.length;
    const progress = Math.round(((wizardStep + 1) / (total + 1)) * 100);
    document.getElementById('wizardProgressBar').style.width = `${progress}%`;
    document.getElementById('wizardBack').style.display = wizardStep > 0 ? 'block' : 'none';
    document.getElementById('wizardNext').textContent = wizardStep === total - 1 ? '✨ Gerar Prompt' : 'Próximo →';

    const currentVal = wizardAnswers[step.key] ?? step.default ?? '';
    let inputHtml = '';
    if (step.type === 'select') {
        inputHtml = `<select id="wizardInput" style="width:100%;padding:0.75rem;border:1.5px solid var(--border);border-radius:8px;font-size:1rem;">
            ${step.options.map(o => `<option value="${o.v}" ${currentVal === o.v ? 'selected' : ''}>${o.l}</option>`).join('')}
        </select>`;
    } else if (step.type === 'range') {
        inputHtml = `<div style="text-align:center;">
            <input type="range" id="wizardInput" min="${step.min}" max="${step.max}" value="${currentVal}" oninput="document.getElementById('wizardRangeVal').textContent=this.value" style="width:100%;accent-color:var(--accent);">
            <div style="font-size:2.5rem;font-weight:800;color:var(--accent);margin-top:0.5rem;" id="wizardRangeVal">${currentVal}</div>
        </div>`;
    } else if (step.type === 'textarea') {
        inputHtml = `<textarea id="wizardInput" rows="4" placeholder="${step.placeholder || ''}" style="width:100%;padding:0.75rem;border:1.5px solid var(--border);border-radius:8px;font-size:1rem;">${currentVal}</textarea>`;
    } else {
        inputHtml = `<input type="text" id="wizardInput" placeholder="${step.placeholder || ''}" value="${currentVal}" style="width:100%;padding:0.75rem;border:1.5px solid var(--border);border-radius:8px;font-size:1rem;">`;
    }

    document.getElementById('wizardStep').innerHTML = `
        <div style="color:var(--text-faint);font-size:0.78rem;margin-bottom:0.5rem;">Passo ${wizardStep + 1} de ${total}</div>
        <h3 style="margin:0 0 1.2rem;font-size:1.05rem;">${step.label}</h3>
        ${inputHtml}`;
}

function wizardNext() {
    const step = WIZARD_STEPS[wizardStep];
    const input = document.getElementById('wizardInput');
    wizardAnswers[step.key] = input ? input.value : '';
    if (wizardStep === WIZARD_STEPS.length - 1) { generateWizardPrompt(); }
    else { wizardStep++; renderWizardStep(); }
}

function wizardBack() {
    if (wizardStep > 0) { wizardStep--; renderWizardStep(); }
}

async function generateWizardPrompt() {
    document.getElementById('wizardNext').textContent = 'Gerando...';
    document.getElementById('wizardNext').disabled = true;
    try {
        const payload = { ...wizardAnswers, formality: wizardAnswers.formality || 'equilibrado', autonomy_level: wizardAnswers.autonomy_level || 'equilibrada' };
        if (typeof payload.data_to_collect === 'string') {
            payload.data_to_collect = payload.data_to_collect.split(',').map(s => s.trim()).filter(Boolean);
        }
        if (!payload.data_to_collect || !payload.data_to_collect.length) payload.data_to_collect = null;
        const res = await authFetch(`${API_BASE}/prompts/generate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if (!res || !res.ok) throw new Error('Falha');
        const data = await res.json();
        document.getElementById('wizardPromptOutput').textContent = data.prompt;
        document.getElementById('wizardPreview').style.display = 'block';
        document.getElementById('wizardPreview').scrollIntoView({ behavior: 'smooth' });
    } catch {
        showAlert('❌ Erro ao gerar prompt. Verifique se o servidor está online.', 'error');
    } finally {
        document.getElementById('wizardNext').textContent = '✨ Gerar Prompt';
        document.getElementById('wizardNext').disabled = false;
    }
}

function copyWizardPrompt() {
    navigator.clipboard.writeText(document.getElementById('wizardPromptOutput').textContent);
    showAlert('📋 Prompt copiado!', 'success');
}

function saveWizardAsProfile() {
    const prompt = document.getElementById('wizardPromptOutput').textContent;
    document.getElementById('profileAgentName').value = wizardAnswers.agent_name || 'Agente';
    document.getElementById('profileName').value = `${wizardAnswers.agent_name || 'Agente'} - ${wizardAnswers.company_name || 'Novo'}`;
    document.getElementById('profileAvatar').value = '🤖';
    document.getElementById('profileModalEmoji').textContent = '🤖';
    document.getElementById('profileChannel').value = 'whatsapp';
    document.getElementById('profileNiche').value = wizardAnswers.niche || 'geral';
    document.getElementById('profileTone').value = wizardAnswers.tone || 'neutro';
    document.getElementById('profileFormality').value = wizardAnswers.formality || 'equilibrado';
    document.getElementById('profileAutonomy').value = wizardAnswers.autonomy_level || 'equilibrada';
    document.getElementById('profileObjective').value = wizardAnswers.objective || '';
    document.getElementById('profileDataCollect').value = Array.isArray(wizardAnswers.data_to_collect) ? wizardAnswers.data_to_collect.join(', ') : (wizardAnswers.data_to_collect || '');
    document.getElementById('profilePrompt').value = prompt;
    document.getElementById('profileModalTitle').textContent = 'Salvar Agente do Wizard';
    document.getElementById('btnDeleteProfile').style.display = 'none';
    editingProfileId = null;
    document.getElementById('profileModal').classList.add('active');
}
