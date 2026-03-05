// ═══════════════════════════════════════════════════════════════
// MASTER ADMIN JS — Auto Tech Lith SaaS Platform
// ═══════════════════════════════════════════════════════════════

const apiBase = (window.location.port === '8080')
    ? `http://${window.location.hostname}:8000`
    : '';
const API = apiBase + '/api/v1';
const AUTH_URL = '/login.html';

// ── Auth & Guard ─────────────────────────────────────────────────
// ── Auth & Guard ─────────────────────────────────────────────────
// With HttpOnly cookies, JS cannot read the token. 
// We rely on the backend to validate the session.
function getToken() { return localStorage.getItem('token'); }

async function checkMasterAuth() {
    try {
        const user = await apiFetch('/auth/me');
        if (!user) { window.location.href = AUTH_URL; return false; }
        const role = (user.role || '').toLowerCase();
        const isMaster = (role === 'owner' || role === 'master_admin');
        if (!isMaster) { window.location.href = AUTH_URL; return false; }
        return true;
    } catch (_) { window.location.href = AUTH_URL; return false; }
}

function authHeaders() {
    // Header 'Authorization' is now optional if cookie is present.
    // We send it only if we still have a token in localStorage (migration phase).
    const headers = { 'Content-Type': 'application/json' };
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    return headers;
}

async function apiFetch(path, opts = {}) {
    opts.headers = { ...authHeaders(), ...(opts.headers || {}) };
    opts.credentials = 'include'; // REQUIRED for cookies
    if (!opts.cache) opts.cache = 'no-store';

    let r = await fetch(API + path, opts);

    if (r.status === 401 && path !== '/auth/refresh') {
        // Try refresh
        const refreshed = await fetch(API + '/auth/refresh', { method: 'POST', credentials: 'include' });
        if (refreshed.ok) {
            // Retry original request
            r = await fetch(API + path, opts);
        } else {
            localStorage.removeItem('token');
            window.location.href = AUTH_URL;
            return null;
        }
    }

    if (r.status === 401) {
        localStorage.removeItem('token');
        window.location.href = AUTH_URL;
        return null;
    }
    if (r.status === 403) {
        // 403 on master endpoints = stale/wrong session, redirect to login
        const body = await r.text();
        if (body.includes('Master Admin access required')) {
            localStorage.removeItem('token');
            window.location.href = AUTH_URL;
            return null;
        }
        throw new Error(`403: ${body}`);
    }
    if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
    if (r.status === 204) return null;
    return r.json();
}

function logout() {
    localStorage.removeItem('token');
    window.location.href = AUTH_URL;
}

// ── Toast & Loading & Modals ─────────────────────────────────────
function showAlert(msg, type = 'success') {
    const container = document.getElementById('alertContainer');
    if (!container) return; // Prevent errors if container is missing
    const el = document.createElement('div');
    el.className = `alert ${type}`;
    el.textContent = msg;
    container.appendChild(el);
    setTimeout(() => el.remove(), 4500);
}

function setButtonLoading(btn, isLoading) {
    if (!btn) return;
    if (isLoading) {
        btn.classList.add('loading');
        if (!btn.querySelector('.spinner')) {
            const spinner = document.createElement('div');
            spinner.className = 'spinner';
            btn.appendChild(spinner);
        }
    } else {
        btn.classList.remove('loading');
    }
}

function confirmAction(message, onConfirm) {
    const modal = document.getElementById('confirmModal');
    if (!modal) {
        // Fallback to native if modal is not present
        if (confirm(message)) onConfirm();
        return;
    }
    document.getElementById('confirmMessage').textContent = message;

    const btnCancel = document.getElementById('confirmCancelBtn');
    const btnConfirm = document.getElementById('confirmOkBtn');

    // Cleanup previous listeners to avoid multiple triggers
    const parentCancel = btnCancel.parentNode;
    const newCancel = btnCancel.cloneNode(true);
    const newConfirm = btnConfirm.cloneNode(true);
    parentCancel.replaceChild(newCancel, btnCancel);
    parentCancel.replaceChild(newConfirm, btnConfirm);

    newCancel.onclick = () => {
        modal.classList.remove('active');
    };

    newConfirm.onclick = () => {
        modal.classList.remove('active');
        onConfirm();
    };

    modal.classList.add('active');
}


// ── Live Clock ───────────────────────────────────────────────────
function startClock() {
    const el = document.getElementById('liveClock');
    if (!el) return;
    const tick = () => {
        const now = new Date();
        el.textContent = now.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' });
    };
    tick();
    setInterval(tick, 1000);
}

// ── Navigation ───────────────────────────────────────────────────
function initNav() {
    document.querySelectorAll('.nav-item[data-target]').forEach(item => {
        item.addEventListener('click', () => {
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.querySelectorAll('.view-section').forEach(s => s.classList.remove('active'));
            item.classList.add('active');
            const target = item.dataset.target;
            window.location.hash = target;
            const section = document.getElementById(target);
            if (section) {
                section.classList.add('active');
                document.getElementById('pageTitle').textContent = item.textContent.trim();
            }

            // Auto close mobile sidebar if open
            if (window.innerWidth <= 992) {
                toggleMobileSidebar();
            }

            // Lazy-load section data
            if (target === 'dashboard') loadDashboard();
            if (target === 'tenants') loadTenants();
            if (target === 'tickets') loadTickets();
            if (target === 'logs') loadAuditLogs();
            if (target === 'faturamento') loadBilling();
            if (target === 'infra') loadInfra();
            if (target === 'kb') renderKB();

            // Butler Agent Sections
            if (target === 'butler-status') loadButlerStatus();
            if (target === 'butler-logs') loadButlerLogs();
            if (target === 'butler-churn') loadButlerChurn();
            if (target === 'butler-billing') loadButlerBilling();
            if (target === 'butler-scheduler') loadSchedulerJobs();

            // Additional Master sections
            if (target === 'leads') loadLeads();
            document.title = `Auto Tech Lith | ${item.textContent.trim()}`;
            if (target === 'quotas') loadQuotas();
            if (target === 'abuse') loadAbuseAlerts();
            if (target === 'internal-finance') loadFinancial();
            if (target === 'internal-ai') loadInternalAIConfig();
            if (target === 'whatsapp') loadWhatsAppInstances();
            if (target === 'configuracao') {
                loadAccountConfig();
                loadWebhooks();
            }
        });
    });
}

// ── DOMContentLoaded ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    if (!await checkMasterAuth()) return;
    startClock();
    initNav();
    loadUser();

    // UX-001: Deep Linking (Handle Hash)
    const hash = window.location.hash.substring(1);
    if (hash) {
        const item = document.querySelector(`.nav-item[data-target="${hash}"]`);
        if (item) item.click();
        else loadDashboard();
    } else {
        loadDashboard();
    }

    // Auto-refresh dashboard every 60s
    setInterval(loadDashboard, 60000);
});

function toggleMobileSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.getElementById('mobileSidebarOverlay');
    if (!sidebar || !overlay) return;

    sidebar.classList.toggle('mobile-open');
    if (sidebar.classList.contains('mobile-open')) {
        overlay.classList.add('active');
    } else {
        overlay.classList.remove('active');
    }
}

// ── Export CSV & Submenu toggles ─────────────────────────────────
window.toggleSubmenu = function (el) {
    el.classList.toggle('collapsed');
    const submenu = el.nextElementSibling;
    if (submenu && submenu.classList.contains('nav-submenu')) {
        submenu.classList.toggle('collapsed');
    }
};

window.exportTableToCSV = function (tableId, filename) {
    const table = document.getElementById(tableId);
    if (!table) return showAlert('Tabela não encontrada para exportação.', 'error');

    let csv = [];
    const rows = table.querySelectorAll('tr');

    for (const row of rows) {
        let cols = row.querySelectorAll('td, th');
        let rowData = [];
        for (const col of cols) {
            let data = col.innerText.replace(/"/g, '""');
            rowData.push(`"${data}"`);
        }
        csv.push(rowData.join(','));
    }

    // Add BOM for Excel UTF-8 support
    const csvFile = new Blob([new Uint8Array([0xEF, 0xBB, 0xBF]), csv.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const downloadLink = document.createElement('a');
    downloadLink.download = `${filename}_${new Date().toISOString().slice(0, 10)}.csv`;
    downloadLink.href = window.URL.createObjectURL(csvFile);
    downloadLink.style.display = 'none';
    document.body.appendChild(downloadLink);
    downloadLink.click();
    downloadLink.remove();
};

// ── Load Current User ────────────────────────────────────────────
async function loadUser() {
    try {
        const user = await apiFetch('/auth/me');
        if (!user) return;
        const nameEl = document.getElementById('userNameDisplay');
        const roleEl = document.getElementById('userRoleDisplay');
        const avatarEl = document.getElementById('userAvatar');
        if (nameEl) nameEl.textContent = user.name || user.username;
        if (roleEl) roleEl.textContent = 'Master Admin';
        if (avatarEl) avatarEl.textContent = (user.name || 'M').charAt(0).toUpperCase();
    } catch (e) { console.error('loadUser', e); }
}

// ── DASHBOARD ────────────────────────────────────────────────────
async function loadDashboard() {
    try {
        const fetchAll = async () => {
            return await Promise.all([
                apiFetch('/master/kpis').catch(() => null),
                apiFetch('/master/tenants').catch(() => []),
                apiFetch('/master/churn-alerts').catch(() => []),
            ]);
        };

        let data;
        const cachedStr = sessionStorage.getItem('dashboard_cache');
        if (cachedStr) {
            try {
                data = JSON.parse(cachedStr);
                applyDashboardData(data[0], data[1], data[2]);
            } catch (e) { }
            // SWR Background Revalidation
            fetchAll().then(fresh => {
                sessionStorage.setItem('dashboard_cache', JSON.stringify(fresh));
                applyDashboardData(fresh[0], fresh[1], fresh[2]);
            });
        } else {
            data = await fetchAll();
            sessionStorage.setItem('dashboard_cache', JSON.stringify(data));
            applyDashboardData(data[0], data[1], data[2]);
        }
    } catch (e) { console.error('loadDashboard', e); }
}

function applyDashboardData(kpis, tenants, churn) {
    if (kpis) {
        setText('kpiTotalTenants', kpis.total_tenants ?? '—');
        setText('kpiActiveTenants', kpis.active_tenants ?? '—');
        setText('kpiInteractions', fmt(kpis.total_interactions_30d));
        setText('kpiChurnAlerts', kpis.churn_alert_count ?? 0);
        setText('kpiTotalCost', '$' + (kpis.total_cost_usd_30d ?? 0).toFixed(2));
        setText('kpiAvgTokens', fmt(kpis.avg_tokens_per_tenant ?? 0));
    }
    if (churn) renderChurnAlerts(churn);
    if (tenants) renderTopTenants(tenants);
    updateSystemStatus();
}

function renderChurnAlerts(churn) {
    const el = document.getElementById('dashChurnAlerts');
    if (!el) return;
    if (!churn || !churn.length) {
        el.innerHTML = '<p class="text-muted text-sm" style="text-align:center;padding:2rem;">✅ Sem alertas de churn esta semana</p>';
        return;
    }
    el.innerHTML = churn.map(c => `
        <div style="display:flex;justify-content:space-between;align-items:center;
            padding:0.75rem 0;border-bottom:1px solid var(--border);">
            <div>
                <span class="bold">${c.tenant_name || 'Tenant #' + c.tenant_id}</span>
                <span class="text-sm text-muted" style="margin-left:0.5rem;">${c.last_week_interactions} → ${c.this_week_interactions}</span>
            </div>
            <span class="badge danger">-${c.drop_percent}%</span>
        </div>`).join('');
}

function renderTopTenants(tenants) {
    const el = document.getElementById('dashTopTenants');
    if (!el || !tenants) return;
    const sorted = [...tenants].sort((a, b) => (b.interactions_30d || 0) - (a.interactions_30d || 0)).slice(0, 5);
    el.innerHTML = sorted.map((t, i) => `
        <div style="display:flex;align-items:center;gap:0.75rem;padding:0.6rem 0;
            border-bottom:1px solid var(--border);">
            <span style="font-size:1rem;font-weight:800;color:var(--accent);min-width:20px;">#${i + 1}</span>
            <div style="flex:1;">
                <div class="bold text-sm">${t.name}</div>
                <div class="text-muted" style="font-size:0.75rem;">${fmt(t.interactions_30d || 0)} msgs · $${(t.cost_usd_30d || 0).toFixed(4)}</div>
            </div>
            <span class="badge ${t.is_active ? 'active' : 'neutral'}">${t.is_active ? 'Ativo' : 'Inativo'}</span>
        </div>`).join('');
}

function updateSystemStatus() {
    // Simulated — will hook to real infra API when available
    const statuses = [
        { id: 'statusDb', label: 'PostgreSQL', status: 'online' },
        { id: 'statusApi', label: 'FastAPI', status: 'online' },
        { id: 'statusWorker', label: 'Workers', status: 'online' },
    ];
    statuses.forEach(s => {
        const el = document.getElementById(s.id);
        if (el) el.className = `badge ${s.status === 'online' ? 'active' : 'danger'}`;
    });
}

// ── TENANTS ──────────────────────────────────────────────────────
let _tenantsData = [];

async function loadTenants() {
    try {
        const tenants = await apiFetch('/master/tenants');
        _tenantsData = tenants || [];
        renderTenantsTable(_tenantsData);
    } catch (e) {
        showAlert('Erro ao carregar tenants: ' + e.message, 'error');
    }
}

function openTenantCreateModal() {
    const setV = (id, v) => {
        const el = document.getElementById(id);
        if (el) el.value = v || '';
    };
    setV('newTenantName', '');
    setV('newTenantSubdomain', '');
    setV('newAdminName', '');
    setV('newAdminEmail', '');
    setV('newAdminPhone', '');
    setV('newAdminPassword', '');
    setV('newTenantPlan', 'basic');
    setV('newTenantWA', 1);
    setV('newTenantDaily', 1000);
    setV('newTenantMonthly', 20000);
    const modal = document.getElementById('tenantCreateModal');
    if (modal) modal.classList.add('active');
}

function closeTenantCreateModal() {
    const modal = document.getElementById('tenantCreateModal');
    if (modal) modal.classList.remove('active');
}

async function saveNewTenant() {
    const tenantName = document.getElementById('newTenantName')?.value.trim();
    const subdomain = document.getElementById('newTenantSubdomain')?.value.trim();
    const adminName = document.getElementById('newAdminName')?.value.trim();
    const adminEmail = document.getElementById('newAdminEmail')?.value.trim();
    const adminPhone = document.getElementById('newAdminPhone')?.value.trim();
    const adminPassword = document.getElementById('newAdminPassword')?.value;
    const plan = document.getElementById('newTenantPlan')?.value || 'basic';
    const wa = parseInt(document.getElementById('newTenantWA')?.value) || 1;
    const daily = parseInt(document.getElementById('newTenantDaily')?.value) || 1000;
    const monthly = parseInt(document.getElementById('newTenantMonthly')?.value) || 20000;

    if (!tenantName || !subdomain || !adminName || !adminEmail || !adminPassword) {
        showAlert('Preencha os campos obrigatórios (tenant, subdomínio, usuário e senha).', 'error');
        return;
    }

    const payload = {
        tenant_name: tenantName,
        subdomain,
        admin_name: adminName,
        admin_email: adminEmail,
        admin_phone: adminPhone,
        admin_password: adminPassword,
        plan_tier: plan,
        max_whatsapp_instances: wa,
        max_messages_daily: daily,
        max_messages_monthly: monthly,
    };

    const btn = document.querySelector('#tenantCreateModal .btn-primary');
    setButtonLoading(btn, true);

    try {
        const res = await apiFetch('/master/tenants', {
            method: 'POST',
            body: JSON.stringify(payload),
        });
        if (!res) return;
        showAlert('✅ Conta criada com sucesso!', 'success');
        closeTenantCreateModal();
        loadTenants();
    } catch (e) {
        showAlert('Erro ao criar tenant: ' + e.message, 'error');
    } finally {
        setButtonLoading(btn, false);
    }
}

function renderTenantsTable(tenants) {
    const tbody = document.getElementById('tenantsBody');
    if (!tbody) return;
    if (!tenants.length) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-muted);padding:2rem;">Nenhum tenant encontrado</td></tr>';
        return;
    }
    tbody.innerHTML = tenants.map(t => `
        <tr style="cursor:pointer;" onclick="openTenantDrawer(${t.id})">
            <td><span class="bold">#${t.id}</span></td>
            <td><span class="bold" style="color:var(--text-primary);">${t.name}</span></td>
            <td><span class="mono">${t.subdomain || '—'}</span></td>
            <td><span class="badge ${t.is_active ? 'active' : 'neutral'}">${t.is_active ? '✓ Ativo' : 'Inativo'}</span></td>
            <td>${fmt(t.interactions_30d || 0)}</td>
            <td>${fmt(t.tokens_30d || 0)}</td>
            <td class="${(t.cost_usd_30d || 0) > 50 ? 'bold' : ''}">$${(t.cost_usd_30d || 0).toFixed(4)}</td>
            <td class="text-muted text-sm">${t.last_active ? t.last_active.slice(0, 16).replace('T', ' ') : '—'}</td>
            <td>
                <button class="btn btn-ghost btn-sm" onclick="event.stopPropagation(); openTenantModal(${t.id})">✏️ Editar</button>
                <button class="btn btn-ghost btn-danger btn-sm" onclick="event.stopPropagation(); deleteTenant(${t.id}, '${t.name?.replace(/'/g, "\\'") || ''}')">🗑️ Excluir</button>
            </td>
        </tr>`).join('');
}

function deleteTenant(id, name = '') {
    const label = name ? ` o tenant "${name}"` : '';
    confirmAction(`Tem certeza que deseja excluir definitivamente${label}? Esta ação não poderá ser desfeita.`, async () => {
        try {
            await apiFetch(`/master/tenants/${id}`, { method: 'DELETE' });
            showAlert('🗑️ Tenant excluído com sucesso.', 'info');
            loadTenants();
        } catch (e) {
            showAlert('Erro ao excluir tenant: ' + e.message, 'error');
        }
    });
}

async function openTenantModal(id) {
    try {
        const tenant = await apiFetch(`/master/tenants/${id}`);
        document.getElementById('editTenantId').value = tenant.id;
        document.getElementById('editTenantName').value = tenant.name || '';
        document.getElementById('editTenantStatus').value = tenant.status || 'pending';
        document.getElementById('editTenantIsActive').checked = !!tenant.is_active;
        document.getElementById('editTenantPlan').value = tenant.plan_tier || 'basic';
        document.getElementById('editTenantWA').value = tenant.max_whatsapp_instances || 1;
        document.getElementById('editTenantDaily').value = tenant.max_messages_daily || 1000;
        document.getElementById('editTenantMonthly').value = tenant.max_messages_monthly || 20000;

        document.getElementById('tenantModal').classList.add('active');
    } catch (e) {
        showAlert('Erro ao carregar detalhes do tenant: ' + e.message, 'error');
    }
}

function closeTenantModal() {
    document.getElementById('tenantModal').classList.remove('active');
}

async function saveTenantChanges() {
    const id = document.getElementById('editTenantId').value;
    if (!id) return;

    const payload = {
        name: document.getElementById('editTenantName').value,
        status: document.getElementById('editTenantStatus').value,
        is_active: document.getElementById('editTenantIsActive').checked,
        plan_tier: document.getElementById('editTenantPlan').value,
        max_whatsapp_instances: parseInt(document.getElementById('editTenantWA').value) || 1,
        max_messages_daily: parseInt(document.getElementById('editTenantDaily').value) || 1000,
        max_messages_monthly: parseInt(document.getElementById('editTenantMonthly').value) || 20000
    };

    const btn = document.querySelector('#tenantModal .btn-primary');
    setButtonLoading(btn, true);

    try {
        await apiFetch(`/master/tenants/${id}`, {
            method: 'PUT',
            body: JSON.stringify(payload)
        });
        showAlert('Tenant atualizado com sucesso!', 'success');
        closeTenantModal();
        loadTenants();
    } catch (e) {
        showAlert('Erro ao salvar tenant: ' + e.message, 'error');
    } finally {
        setButtonLoading(btn, false);
    }
}

function filterTenants(query) {
    const q = query.toLowerCase();
    const filtered = _tenantsData.filter(t =>
        t.name.toLowerCase().includes(q) || (t.subdomain || '').toLowerCase().includes(q));
    renderTenantsTable(filtered);
}

// ── TENANT DRAWER ────────────────────────────────────────────────
async function openTenantDrawer(tenantId) {
    const tenant = _tenantsData.find(t => t.id === tenantId);
    if (!tenant) return;

    document.getElementById('drawerTenantName').textContent = tenant.name;
    document.getElementById('drawerTenantId').textContent = '#' + tenant.id;

    // Fill stats
    document.getElementById('dtInteractions').textContent = fmt(tenant.interactions_30d || 0);
    document.getElementById('dtTokens').textContent = fmt(tenant.tokens_30d || 0);
    document.getElementById('dtCost').textContent = '$' + (tenant.cost_usd_30d || 0).toFixed(4);
    document.getElementById('dtStatus').innerHTML = `<span class="badge ${tenant.is_active ? 'active' : 'neutral'}">${tenant.is_active ? 'Ativo' : 'Inativo'}</span>`;

    document.getElementById('tenantDrawer').classList.add('active');
    document.getElementById('drawerBackdrop').classList.add('active');

    // Load usage logs for this tenant
    try {
        const usage = await apiFetch(`/usage/summary?days=30`).catch(() => null);
        // Show in drawer (simplified — full data would require per-tenant endpoint)
    } catch (_) { }
}

function closeTenantDrawer() {
    document.getElementById('tenantDrawer').classList.remove('active');
    document.getElementById('drawerBackdrop').classList.remove('active');
}

// ── TICKETS ──────────────────────────────────────────────────────
async function loadTickets() {
    try {
        const tickets = await apiFetch('/tickets').catch(() => []);
        const tbody = document.getElementById('ticketsBody');
        if (!tbody) return;
        if (!tickets || !tickets.length) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:2rem;">Nenhum ticket encontrado</td></tr>';
            return;
        }
        tbody.innerHTML = tickets.map(t => `<tr>
            <td>#${t.id}</td>
            <td>${t.customer_name || '—'}</td>
            <td>${t.subject}</td>
            <td><span class="badge ${priorityBadge(t.priority)}">${t.priority || 'normal'}</span></td>
            <td><span class="badge ${statusBadge(t.status)}">${t.status || 'aberto'}</span></td>
            <td class="text-muted text-sm">${new Date(t.created_at).toLocaleDateString('pt-BR')}</td>
            <td><button class="btn btn-ghost btn-sm" onclick="viewTicket(${t.id})">Ver</button></td>
        </tr>`).join('');
    } catch (e) { showAlert('Erro ao carregar tickets', 'error'); }
}

function priorityBadge(p) {
    return { high: 'danger', medium: 'warn', low: 'info' }[p] || 'neutral';
}
function statusBadge(s) {
    return { open: 'active', closed: 'neutral', pending: 'warn' }[s] || 'neutral';
}
function viewTicket(id) { showAlert('Detalhe de ticket em breve (#' + id + ')', 'info'); }

// ── AUDIT LOGS ───────────────────────────────────────────────────
async function loadAuditLogs() {
    const tbody = document.getElementById('logsBody');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:2rem;"><span class=\"skeleton\"></span></td></tr>';
    try {
        // Future: apiFetch('/audit-logs?limit=100')
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:2rem;">API de logs em integração. Disponível em breve.</td></tr>';
    } catch (e) { console.error(e); }
}

// ── BILLING ──────────────────────────────────────────────────────
async function loadBilling() {
    try {
        const tenants = await apiFetch('/master/tenants').catch(() => []);
        const tbody = document.getElementById('billingBody');
        if (!tbody) return;
        if (!tenants || !tenants.length) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--text-muted);">Sem dados de faturamento</td></tr>';
            return;
        }
        const total = tenants.reduce((sum, t) => sum + (t.cost_usd_30d || 0), 0);
        tbody.innerHTML = tenants.map(t => {
            const cost = t.cost_usd_30d || 0;
            const pct = total > 0 ? ((cost / total) * 100).toFixed(1) : 0;
            return `<tr>
                <td><span class="bold" style="color:var(--text-primary);">${t.name}</span></td>
                <td>${fmt(t.interactions_30d || 0)}</td>
                <td>${fmt(t.tokens_30d || 0)}</td>
                <td><strong style="color:var(--green);">$${cost.toFixed(4)}</strong></td>
                <td>
                    <div style="display:flex;align-items:center;gap:0.5rem;">
                        <div class="progress-bar" style="flex:1;max-width:100px;">
                            <div class="progress-fill" style="width:${pct}%"></div>
                        </div>
                        <span class="text-sm text-muted">${pct}%</span>
                    </div>
                </td>
            </tr>`;
        }).join('');

        // Update total
        const totalEl = document.getElementById('billingTotal');
        if (totalEl) totalEl.textContent = '$' + total.toFixed(4);
    } catch (e) { showAlert('Erro ao carregar faturamento', 'error'); }
}

// ── INFRASTRUCTURE ───────────────────────────────────────────────
async function loadInfra() {
    const services = [
        { name: 'Auto Tech DB (Postgres)', icon: '🗄️', version: '15.4', status: 'online', cpu: '5%', mem: '150MB / 2GB' },
        { name: 'Auto Tech Backend', icon: '⚡', version: '1.0', status: 'online', cpu: '8%', mem: '180MB / 1GB' },
        { name: 'Evolution API', icon: '📱', version: '2.3.7', status: 'online', cpu: '10%', mem: '180MB / 512MB' },
        { name: 'Evolution Postgres', icon: '🗄️', version: '15', status: 'online', cpu: '2%', mem: '110MB / 512MB' },
        { name: 'Evolution Redis', icon: '🔴', version: '7.2', status: 'online', cpu: '1%', mem: '40MB / 256MB' },
        { name: 'Traefik Proxy', icon: '🔄', version: 'Dokploy', status: 'online', cpu: '1%', mem: '25MB / 128MB' },
    ];

    const grid = document.getElementById('infraGrid');
    if (!grid) return;
    grid.innerHTML = services.map(s => {
        const cpuNum = parseFloat(s.cpu);
        const fillClass = cpuNum > 80 ? 'danger' : cpuNum > 50 ? 'warn' : '';
        return `
        <div class="infra-card">
            <div class="infra-card-title">
                <span>${s.icon}</span>
                <span>${s.name}</span>
                <span class="badge ${s.status === 'online' ? 'active' : s.status === 'warn' ? 'warn' : 'danger'}" style="margin-left:auto;font-size:0.68rem;">
                    <span class="status-dot ${s.status}"></span>${s.status}
                </span>
            </div>
            <div class="infra-value">${s.cpu}</div>
            <div class="infra-sub">CPU · ${s.mem} RAM · v${s.version}</div>
            <div class="progress-bar">
                <div class="progress-fill ${fillClass}" style="width:${cpuNum}%"></div>
            </div>
        </div>`;
    }).join('');
}

// ── KNOWLEDGE BASE ───────────────────────────────────────────────
const KB_ARTICLES = [
    { q: 'Como criar um novo tenant (lojista)?', a: 'Acesse Configurações → Tenants → Novo Tenant. Preencha nome, subdomínio e plano. O sistema cria automaticamente os recursos isolados.' },
    { q: 'Como resetar a senha de um lojista?', a: 'Em Tenants → clique no tenant → aba Usuários → selecione o usuário → "Resetar Senha". Um e-mail é enviado automaticamente.' },
    { q: 'O que é o ENCRYPTION_KEY e onde configurar?', a: 'É a chave Fernet usada para criptografar as chaves de API dos lojistas. Configure no arquivo .env: ENCRYPTION_KEY=<chave Fernet>. Gere uma com: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"' },
    { q: 'Como interpretar os alertas de churn?', a: 'O sistema detecta queda de >40% nas interações semana-a-semana por tenant. Um alerta aparece no Dashboard Global. Recomenda-se contato proativo com o lojista.' },
    { q: 'Qual é a frequência de atualização do Dashboard?', a: 'O dashboard atualiza automaticamente a cada 30 segundos. Clique em "Atualizar" para forçar refresh imediato.' },
    { q: 'Como funciona o isolamento entre tenants?', a: 'Todo dado é associado a um tenant_id. Queries do portal do lojista sempre filtram por tenant_id. O Master Admin é o único com acesso cross-tenant — protegido por role=owner sem tenant_id.' },
    { q: 'Onde ver os logs de auditoria completos?', a: 'Na aba "Logs & Auditoria" do Master Admin. Os logs registram todas as ações críticas com tenant_id, timestamp e tipo de evento.' },
];

function renderKB() {
    const container = document.getElementById('kbList');
    if (!container) return;
    container.innerHTML = KB_ARTICLES.map((a, i) => `
        <div class="kb-item">
            <div class="kb-question" onclick="toggleKB(${i})">
                <span>${a.q}</span>
                <span class="kb-chevron" id="chev-${i}">▼</span>
            </div>
            <div class="kb-answer" id="ans-${i}">${a.a}</div>
        </div>`).join('');
}

function toggleKB(i) {
    const ans = document.getElementById('ans-' + i);
    const chev = document.getElementById('chev-' + i);
    ans.classList.toggle('open');
    chev.classList.toggle('open');
}
// ── BUTLER AGENT ──────────────────────────────────────────────────
const SEV_BADGE = { critical: 'danger', high: 'danger', medium: 'warn', low: 'neutral' };
const SEV_ICON = { critical: '🔴', high: '🟠', medium: '🟡', low: '🟢' };

async function loadButlerStatus() {
    try {
        const r = await fetch(`${API}/master/butler/status`, { headers: authHeaders() });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const d = await r.json();
        const okC = (d.services || []).filter(s => s.status === 'ok').length;
        const badC = (d.services || []).filter(s => s.status !== 'ok').length;
        setText('bsOverall', (d.overall || '?').toUpperCase());
        setText('bsOkCount', okC);
        setText('bsBadCount', badC);
        const card = document.getElementById('bsSummary');
        if (card) card.className = `stat-card ${d.overall === 'ok' ? 'green' : d.overall === 'critical' ? 'red' : 'yellow'}`;
        const tbody = document.getElementById('bsServicesBody');
        if (tbody) tbody.innerHTML = (d.services || []).map(s =>
            `<tr><td style="font-weight:700">${s.name}</td>` +
            `<td><span class="badge ${s.status === 'ok' ? 'active' : 'danger'}">${s.status === 'ok' ? '✅ OK' : s.status === 'down' ? '🔴 DOWN' : '⚠️ DEG'}</span></td>` +
            `<td>${s.latency_ms != null ? s.latency_ms + 'ms' : '—'}</td>` +
            `<td class="text-sm" style="color:var(--text-muted)">${s.detail || ''}</td></tr>`
        ).join('') || '<tr><td colspan="4" style="text-align:center">Sem serviços</td></tr>';
    } catch (e) {
        console.error('loadButlerStatus error:', e);
        showAlert('Erro status: ' + e.message, 'error');
        const tbody = document.getElementById('bsServicesBody');
        if (tbody) tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;color:var(--red)">Erro ao carregar status: ${e.message}</td></tr>`;
    }
}

async function loadButlerLogs() {
    const sev = document.getElementById('blSeverityFilter')?.value || '';
    try {
        const r = await fetch(`${API}/master/butler/logs?limit=50${sev ? '&severity=' + sev : ''}`, { headers: authHeaders() });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const logs = await r.json();
        const tbody = document.getElementById('blBody');
        if (tbody) tbody.innerHTML = logs.map(l =>
            `<tr><td class="mono" style="color:var(--text-muted)">#${l.id}</td>` +
            `<td class="text-sm">${l.timestamp ? new Date(l.timestamp).toLocaleString('pt-BR') : '—'}</td>` +
            `<td class="mono text-sm">${l.action_type || '—'}</td>` +
            `<td><span class="badge ${SEV_BADGE[l.severity] || 'neutral'}">${SEV_ICON[l.severity] || ''} ${l.severity || ''}</span></td>` +
            `<td>${l.tenant_id != null ? '#' + l.tenant_id : '—'}</td>` +
            `<td><span class="badge ${l.result === 'ok' || l.result === 'sent' ? 'active' : l.result === 'pending_approval' ? 'warn' : 'neutral'}">${l.result || ''}</span></td>` +
            `<td class="text-sm" style="max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${l.description || ''}</td></tr>`
        ).join('') || '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text-muted)">Nenhum log</td></tr>';
    } catch (e) {
        console.error('loadButlerLogs error:', e);
        showAlert('Erro logs: ' + e.message, 'error');
        const tbody = document.getElementById('blBody');
        if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--red)">Erro ao carregar logs: ${e.message}</td></tr>`;
    }
}

async function loadButlerChurn() {
    try {
        const r = await fetch(`${API}/master/butler/churn`, { headers: authHeaders() });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const risks = await r.json();
        let crit = 0, high = 0, other = 0;
        risks.forEach(x => { if (x.risk_level === 'critical') crit++; else if (x.risk_level === 'high') high++; else other++; });
        setText('bChurnCritical', crit);
        setText('bChurnHigh', high);
        setText('bChurnMedLow', other);
        const tbody = document.getElementById('bChurnBody');
        if (tbody) tbody.innerHTML = risks.length ? risks.map(x =>
            `<tr><td style="font-weight:700">#${x.tenant_id}</td>` +
            `<td><span class="badge ${SEV_BADGE[x.risk_level] || 'neutral'}">${SEV_ICON[x.risk_level] || ''} ${x.risk_level}</span></td>` +
            `<td style="color:var(--red);font-weight:700">↓${x.drop_percent}%</td>` +
            `<td>${x.last_week}</td><td>${x.this_week}</td>` +
            `<td class="text-sm">${x.recommended_action}</td></tr>`
        ).join('') : '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--green)">✅ Nenhum risco</td></tr>';
    } catch (e) {
        console.error('loadButlerChurn error:', e);
        showAlert('Erro churn: ' + e.message, 'error');
        const tbody = document.getElementById('bChurnBody');
        if (tbody) tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--red)">Erro ao carregar churn: ${e.message}</td></tr>`;
    }
}

async function loadButlerBilling() {
    try {
        const r = await fetch(`${API}/master/butler/billing-report`, { headers: authHeaders() });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const d = await r.json();
        const s = d.summary || {};
        setText('bBillCritical', s.critical_alerts || 0);
        setText('bBillWarning', s.warning_alerts || 0);
        setText('bBillSuspended', s.suspended_tenants || 0);
        const alertBody = document.getElementById('bBillBody');
        if (alertBody) alertBody.innerHTML = (d.alerts || []).map(a =>
            `<tr><td style="font-weight:700">${a.tenant_name}</td>` +
            `<td><span class="badge ${a.level === 'critical' ? 'danger' : 'warn'}">${a.level}</span></td>` +
            `<td>${a.pct_daily}%</td><td>${a.pct_monthly}%</td>` +
            `<td><span class="badge neutral">${a.upgrade_to}</span></td>` +
            `<td class="text-sm">${a.action}</td></tr>`
        ).join('') || '<tr><td colspan="6" style="text-align:center;padding:1.5rem;color:var(--green)">✅ Sem alertas</td></tr>';
        const topBody = document.getElementById('bTopBody');
        if (topBody) topBody.innerHTML = (s.top_consumers || []).map(t =>
            `<tr><td>#${t.tenant_id}</td><td>${t.interactions}</td>` +
            `<td>${(t.tokens || 0).toLocaleString('pt-BR')}</td>` +
            `<td style="color:var(--yellow)">$${(t.cost_usd || 0).toFixed(4)}</td></tr>`
        ).join('') || '<tr><td colspan="4" style="text-align:center;padding:1rem;color:var(--text-muted)">Sem dados</td></tr>';
    } catch (e) { showAlert('Erro billing: ' + e.message, 'error'); }
}

async function loadSchedulerJobs() {
    try {
        const r = await fetch(`${API}/master/butler/scheduler/jobs`, { headers: authHeaders() });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const jobs = await r.json();
        const tbody = document.getElementById('bJobsBody');
        if (tbody) tbody.innerHTML = jobs.map(j =>
            `<tr><td class="mono text-sm">${j.id}</td>` +
            `<td style="font-weight:700">${j.name}</td>` +
            `<td class="text-sm" style="color:var(--text-muted)">${j.trigger}</td>` +
            `<td class="text-sm">${j.next_run ? new Date(j.next_run).toLocaleString('pt-BR') : '—'}</td>` +
            `<td><button class="btn btn-ghost btn-sm" onclick="triggerJob('${j.id}')">▶️ Executar</button></td></tr>`
        ).join('') || '<tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--text-muted)">Nenhum job</td></tr>';
    } catch (e) { showAlert('Erro jobs: ' + e.message, 'error'); }
}

async function triggerJob(jobId) {
    try {
        const r = await fetch(`${API}/master/butler/scheduler/jobs/${jobId}/run-now`, { method: 'POST', headers: authHeaders() });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        showAlert(`▶️ Job "${jobId}" disparado!`, 'success');
        setTimeout(loadSchedulerJobs, 1500);
    } catch (e) { showAlert('Erro: ' + e.message, 'error'); }
}

window.loadButlerStatus = loadButlerStatus;
window.loadButlerLogs = loadButlerLogs;
window.loadButlerChurn = loadButlerChurn;
window.loadButlerBilling = loadButlerBilling;
window.loadSchedulerJobs = loadSchedulerJobs;
window.triggerJob = triggerJob;

// ── AI CONFIG ────────────────────────────────────────────────────
function updateAIPreview() {
    const name = document.getElementById('aiAgentName')?.value || 'Max';
    const tone = document.getElementById('aiTone')?.value || 'professional';
    const persona = document.getElementById('aiPersona')?.value;
    const toneLabels = { professional: 'Profissional', friendly: 'Amigável', formal: 'Formal', casual: 'Casual', technical: 'Técnico' };
    setText('aiPreviewName', name);
    setText('aiPreviewTone', 'Tom: ' + (toneLabels[tone] || tone));
    setText('aiPreviewPersona', persona || 'Preencha os campos ao lado...');
}

async function loadInternalAIConfig() {
    try {
        const config = await apiFetch('/master/internal-ai/config');
        if (config) {
            const setV = (id, v) => { const el = document.getElementById(id); if (el) el.value = v || ''; };
            setV('aiAgentName', config.agent_name);
            setV('aiTone', config.tone);
            setV('aiPersona', config.persona);
            setV('aiBasePrompt', config.base_prompt);
            updateAIPreview();
        }
    } catch (e) {
        console.error('loadInternalAIConfig error:', e);
    }
}

async function saveInternalAI() {
    const body = {
        agent_name: document.getElementById('aiAgentName')?.value,
        tone: document.getElementById('aiTone')?.value,
        persona: document.getElementById('aiPersona')?.value,
        base_prompt: document.getElementById('aiBasePrompt')?.value,
    };
    try {
        const r = await apiFetch('/master/internal-ai/config', {
            method: 'POST',
            body: JSON.stringify(body)
        });
        if (r) {
            showAlert('✅ Configuração de IA interna salva com sucesso!', 'success');
        }
    } catch (e) {
        showAlert('Erro ao salvar configuração: ' + e.message, 'error');
    }
}

// ── LEADS / CRM ──────────────────────────────────────────────────
const STATUS_COL = {
    contact: 'colContact', briefing: 'colBriefing', proposal: 'colProposal',
    negotiation: 'colNego', closed_won: 'colWon', closed_lost: 'colLost'
};
const STATUS_CNT = {
    contact: 'cCont', briefing: 'cBrief', proposal: 'cProp',
    negotiation: 'cNego', closed_won: 'cWon', closed_lost: 'cLost'
};

async function loadLeads() {
    try {
        const leads = await apiFetch('/master/leads');
        if (!leads) return;
        renderKanban(leads);
        renderLeadsList(leads);
        setText('leadsCount', leads.length);
        // Sync Sidebar Badge
        const badge = document.querySelector('.nav-item[data-target="leads"] .nav-badge');
        if (badge) badge.textContent = leads.length;
    } catch (e) { showAlert('Erro ao carregar leads: ' + e.message, 'error'); }
    try {
        const m = await apiFetch('/master/leads/metrics/funnel');
        if (m) {
            setText('mContact', m.contact);
            setText('mBriefing', m.briefing);
            setText('mProposal', m.proposal);
            setText('mConversion', m.conversion_rate + '%');
            setText('mWon', m.closed_won);
            setText('mLost', m.closed_lost);
        }
    } catch (e) { }
}

function renderKanban(leads) {
    Object.values(STATUS_COL).forEach(id => { const el = document.getElementById(id); if (el) el.innerHTML = ''; });
    const counts = {};
    leads.forEach(l => {
        counts[l.status] = (counts[l.status] || 0) + 1;
        const col = document.getElementById(STATUS_COL[l.status]);
        if (!col) return;
        const card = document.createElement('div');
        card.className = 'kanban-card';
        card.innerHTML = `
        <div class="kanban-card-name">${l.name}</div>
        <div class="kanban-card-company">${l.company || '—'}</div>
        <div class="kanban-card-meta">
            <span>${l.source || ''}</span>
            <span style="color:var(--green)">R$${(l.estimated_mrr || 0).toFixed(0)}/mês</span>
        </div>`;
        card.onclick = () => openLeadModal(l);
        col.appendChild(card);
    });
    Object.entries(STATUS_CNT).forEach(([st, id]) => {
        setText(id, counts[st] || 0);
    });
}

function renderLeadsList(leads) {
    const tbody = document.getElementById('leadsListBody');
    if (!tbody) return;
    const statusLabel = {
        contact: '📞 Contato', briefing: '📝 Briefing', proposal: '📄 Proposta',
        negotiation: '🤝 Negociação', closed_won: '✅ Ganho', closed_lost: '❌ Perdido'
    };
    tbody.innerHTML = leads.map(l => `
    <tr>
        <td style="font-weight:700;color:var(--text-primary)">${l.name}</td>
        <td>${l.phone || '—'}</td>
        <td>${l.email || '—'}</td>
        <td>${l.company || '—'}</td>
        <td><span class="badge ${l.status === 'closed_won' ? 'active' : l.status === 'closed_lost' ? 'danger' : 'info'}">${statusLabel[l.status] || l.status}</span></td>
        <td style="color:var(--green)">R$${(l.estimated_mrr || 0).toFixed(0)}</td>
        <td>${l.assigned_to || '—'}</td>
        <td><button class="btn btn-ghost btn-sm" onclick='openLeadModal(${JSON.stringify(l).replace(/'/g, "&#39;")})'>✏️</button></td>
    </tr>`).join('');
}

function switchLeadView(view, btn) {
    document.querySelectorAll('.inner-tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const kanban = document.getElementById('leadsKanban'); if (kanban) kanban.style.display = view === 'kanban' ? 'flex' : 'none';
    const list = document.getElementById('leadsListView'); if (list) list.style.display = view === 'list' ? 'block' : 'none';
    const metrics = document.getElementById('leadsMetricsView'); if (metrics) metrics.style.display = view === 'metrics' ? 'block' : 'none';
}

function openLeadModal(lead = null) {
    const setV = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
    setV('leadEditId', lead ? lead.id : '');
    setText('leadModalTitle', lead ? '✏️ Editar Lead' : '+ Novo Lead');
    setV('leadName', lead ? lead.name : '');
    setV('leadCompany', lead ? (lead.company || '') : '');
    setV('leadPhone', lead ? (lead.phone || '') : '');
    setV('leadEmail', lead ? (lead.email || '') : '');
    setV('leadSource', lead ? (lead.source || '') : '');
    setV('leadStatus', lead ? lead.status : 'contact');
    setV('leadMRR', lead ? (lead.estimated_mrr || 0) : '');
    setV('leadCAC', lead ? (lead.cac_value || 0) : '');
    setV('leadAssigned', lead ? (lead.assigned_to || '') : '');
    setV('leadNotes', lead ? (lead.notes || '') : '');
    const modal = document.getElementById('leadModal'); if (modal) modal.classList.add('active');
}
function closeLeadModal() { const modal = document.getElementById('leadModal'); if (modal) modal.classList.remove('active'); }

async function saveLead() {
    const id = document.getElementById('leadEditId')?.value;
    const name = document.getElementById('leadName')?.value;
    const phone = document.getElementById('leadPhone')?.value;

    if (!name || name.trim() === '') {
        showAlert('O nome do lead é obrigatório', 'error');
        document.getElementById('leadName').focus();
        return;
    }

    const body = {
        name: name.trim(),
        company: document.getElementById('leadCompany')?.value,
        phone: phone,
        email: document.getElementById('leadEmail')?.value,
        source: document.getElementById('leadSource')?.value,
        status: document.getElementById('leadStatus')?.value,
        estimated_mrr: parseFloat(document.getElementById('leadMRR')?.value) || 0,
        cac_value: parseFloat(document.getElementById('leadCAC')?.value) || 0,
        assigned_to: document.getElementById('leadAssigned')?.value,
        notes: document.getElementById('leadNotes')?.value,
    };
    const path = id ? `/master/leads/${id}` : `/master/leads`;
    try {
        const r = await apiFetch(path, { method: id ? 'PUT' : 'POST', body: JSON.stringify(body) });
        if (r) {
            showAlert(id ? '✅ Lead atualizado!' : '✅ Lead criado!', 'success');
            closeLeadModal();
            loadLeads();
        }
    } catch (e) { showAlert('Erro ao salvar lead: ' + e.message, 'error'); }
}

// ── QUOTAS ───────────────────────────────────────────────────────
async function loadQuotas() {
    try {
        const quotas = await apiFetch('/master/quotas');
        if (quotas) renderQuotas(quotas);
    } catch (e) { showAlert('Erro ao carregar cotas', 'error'); }
}

function renderQuotas(quotas) {
    const tbody = document.getElementById('quotasBody');
    if (!tbody) return;
    tbody.innerHTML = quotas.map(q => {
        const bar = (cur, max) => {
            const p = Math.round(cur / Math.max(max, 1) * 100);
            const c = p >= 90 ? 'danger' : p >= 80 ? 'warn' : '';
            return `<div class="quota-bar"><div class="quota-fill ${c}" style="width:${Math.min(p, 100)}%"></div></div>
                <div class="quota-labels"><span>${cur}/${max}</span><span>${p}%</span></div>`;
        };
        const suspended = q.is_suspended ? '<span class="badge danger">🚫 Suspenso</span>' : '<span class="badge active">✅ Ativo</span>';
        return `<tr>
        <td style="font-weight:700;color:var(--text-primary)">${q.tenant_name}</td>
        <td><span class="badge neutral">${q.plan_tier || 'basic'}</span></td>
        <td><div class="quota-progress-wrap">${bar(q.current_whatsapp_instances, q.max_whatsapp_instances)}</div></td>
        <td><div class="quota-progress-wrap">${bar(q.current_messages_daily, q.max_messages_daily)}</div></td>
        <td><div class="quota-progress-wrap">${bar(q.current_messages_monthly, q.max_messages_monthly)}</div></td>
        <td>${suspended}</td>
        <td>
            <button class="btn btn-ghost btn-sm" onclick='openQuotaModal(${JSON.stringify(q)})'>✏️ Editar</button>
            ${q.is_suspended
                ? `<button class="btn btn-ghost btn-sm" style="color:var(--green)" onclick="unsuspendTenant(${q.tenant_id})">▶️ Liberar</button>`
                : `<button class="btn btn-danger btn-sm" onclick="suspendTenant(${q.tenant_id})">🚫 Suspender</button>`}
        </td>
    </tr>`;
    }).join('');
}

function openQuotaModal(q) {
    const setV = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
    setV('quotaEditTenantId', q.tenant_id);
    setText('quotaModalTitle', `📊 Editar Cota — ${q.tenant_name}`);
    setV('quotaPlan', q.plan_tier || 'basic');
    setV('quotaWA', q.max_whatsapp_instances);
    setV('quotaDaily', q.max_messages_daily);
    setV('quotaMonthly', q.max_messages_monthly);
    setV('quotaReason', '');
    const modal = document.getElementById('quotaModal'); if (modal) modal.classList.add('active');
}
function closeQuotaModal() { const modal = document.getElementById('quotaModal'); if (modal) modal.classList.remove('active'); }

async function saveQuota() {
    const tenantId = document.getElementById('quotaEditTenantId')?.value;
    const body = {
        plan_tier: document.getElementById('quotaPlan')?.value,
        max_whatsapp_instances: parseInt(document.getElementById('quotaWA')?.value) || 1,
        max_messages_daily: parseInt(document.getElementById('quotaDaily')?.value) || 1000,
        max_messages_monthly: parseInt(document.getElementById('quotaMonthly')?.value) || 20000,
        reason: document.getElementById('quotaReason')?.value,
    };
    try {
        const r = await apiFetch(`/master/quotas/${tenantId}`, { method: 'PUT', body: JSON.stringify(body) });
        if (r) {
            showAlert('✅ Cota atualizada! Altercação registrada no AuditLog.', 'success');
            closeQuotaModal(); loadQuotas();
        }
    } catch (e) { showAlert('Erro ao salvar cota: ' + e.message, 'error'); }
}

async function suspendTenant(tenantId) {
    const reason = prompt('Motivo da suspensão (obrigatório):');
    if (!reason) return;
    try {
        const r = await apiFetch(`/master/quotas/${tenantId}/suspend`, { method: 'POST', body: JSON.stringify({ reason }) });
        if (r) {
            showAlert('🚫 Tenant suspenso. AuditLog registrado.', 'success');
            loadQuotas(); loadAbuseAlerts();
        }
    } catch (e) { showAlert('Erro: ' + e.message, 'error'); }
}

async function unsuspendTenant(tenantId) {
    try {
        const r = await apiFetch(`/master/quotas/${tenantId}/unsuspend`, { method: 'POST' });
        if (r) {
            showAlert('✅ Suspensão removida.', 'success');
            loadQuotas(); loadAbuseAlerts();
        }
    } catch (e) { showAlert('Erro: ' + e.message, 'error'); }
}

// ── ABUSE ALERTS ─────────────────────────────────────────────────
async function loadAbuseAlerts() {
    try {
        const alerts = await apiFetch('/master/quotas/alerts/abuse');
        if (alerts) {
            renderAbuseAlerts(alerts);
            setText('abuseCount', alerts.length);
        }
    } catch (e) { showAlert('Erro ao carregar alertas de abuso', 'error'); }
}

function renderAbuseAlerts(alerts) {
    const grid = document.getElementById('abuseGrid');
    if (!grid) return;
    if (!alerts.length) {
        grid.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:3rem">
        <div style="font-size:2rem;margin-bottom:0.5rem">✅</div>
        <div style="color:var(--green);font-weight:700">Nenhum alerta no momento</div>
        <div class="text-muted text-sm">Todos os tenants dentro das cotas normais.</div></div>`;
        setText('abuseWarnCount', 0); setText('abuseCritCount', 0); setText('abuseSuspCount', 0);
        return;
    }
    let warns = 0, crits = 0, susps = 0;
    alerts.forEach(a => { if (a.level === 'warning') warns++; if (a.level === 'critical') crits++; if (a.is_suspended) susps++; });
    setText('abuseWarnCount', warns); setText('abuseCritCount', crits); setText('abuseSuspCount', susps);
    grid.innerHTML = alerts.map(a => `
    <div class="abuse-card ${a.level}">
        <div class="abuse-card-header">
            <div>
                <div class="abuse-tenant-name">${a.tenant_name}</div>
                <div class="abuse-tenant-id">Tenant #${a.tenant_id} · ${a.plan_tier || 'basic'}</div>
            </div>
            <span class="badge ${a.level === 'critical' ? 'danger' : 'warn'}">${a.level === 'critical' ? '🔴 CRÍTICO' : '⚠️ WARNING'}</span>
        </div>
        <div class="abuse-reasons">${a.reasons.map(r => `<span class="abuse-reason-tag">${r}</span>`).join('')}</div>
        <div class="quota-progress-wrap">
            <div class="quota-labels"><span>Msgs/Dia</span><span>${a.pct_daily}%</span></div>
            <div class="quota-bar"><div class="quota-fill ${a.pct_daily >= 90 ? 'danger' : 'warn'}" style="width:${Math.min(a.pct_daily, 100)}%"></div></div>
        </div>
        <div class="quota-progress-wrap" style="margin-top:0.5rem">
            <div class="quota-labels"><span>Msgs/Mês</span><span>${a.pct_monthly}%</span></div>
            <div class="quota-bar"><div class="quota-fill ${a.pct_monthly >= 90 ? 'danger' : 'warn'}" style="width:${Math.min(a.pct_monthly, 100)}%"></div></div>
        </div>
        <div class="abuse-actions">
            ${a.upgrade_suggested ? '<span class="badge warn">💡 Sugerir Upgrade</span>' : ''}
            ${a.is_suspended
            ? `<button class="btn btn-ghost btn-sm" style="color:var(--green)" onclick="unsuspendTenant(${a.tenant_id})">▶️ Liberar</button>`
            : `<button class="btn btn-danger btn-sm" onclick="suspendTenant(${a.tenant_id})">🚫 Suspender</button>`}
        </div>
    </div>`).join('');
}

// ── FINANCIAL ─────────────────────────────────────────────────────
async function loadFinancial() {
    try {
        const [f, txns] = await Promise.all([
            apiFetch('/master/financial').catch(() => null),
            apiFetch('/master/financial/transactions?limit=20').catch(() => []),
        ]);
        if (f) {
            setText('finTotalCost', '$' + (f.total_cost_usd_30d ?? 0).toFixed(2));
            setText('finInteractions', fmt(f.total_interactions_30d));
            setText('finTokens', fmt(f.total_tokens_30d));
            setText('finCAC', '$' + (f.estimated_cac_usd ?? 0).toFixed(4));
            const tbody = document.getElementById('finBreakdownBody');
            if (tbody) tbody.innerHTML = f.breakdown.map(b =>
                `<tr><td style="font-weight:700;color:var(--text-primary)">${b.tenant_name}</td>
            <td>${fmt(b.interactions_30d)}</td><td>${fmt(b.tokens_30d)}</td>
            <td style="color:var(--yellow)">$${(b.cost_usd_30d ?? 0).toFixed(4)}</td>
            <td>${b.pct_of_total}%</td></tr>`).join('') || '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:1rem">Sem dados</td></tr>';
        }
        if (txns) {
            const tbody = document.getElementById('finTransBody');
            if (tbody) tbody.innerHTML = txns.map(t =>
                `<tr><td>#${t.tenant_id}</td><td class="mono">${t.model_used || '—'}</td>
            <td>${fmt(t.total_tokens)}</td><td style="color:var(--yellow)">$${(t.cost_usd ?? 0).toFixed(4)}</td>
            <td class="text-sm">${t.timestamp ? new Date(t.timestamp).toLocaleString('pt-BR') : '—'}</td></tr>`
            ).join('') || '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:1rem">Sem dados</td></tr>';
        }
    } catch (e) { showAlert('Erro ao carregar financeiro', 'error'); }
}

window.updateAIPreview = updateAIPreview;
window.saveInternalAI = saveInternalAI;
window.loadLeads = loadLeads;
window.switchLeadView = switchLeadView;
window.openLeadModal = openLeadModal;
window.closeLeadModal = closeLeadModal;
window.saveLead = saveLead;
window.loadQuotas = loadQuotas;
window.openQuotaModal = openQuotaModal;
window.closeQuotaModal = closeQuotaModal;
window.saveQuota = saveQuota;
window.suspendTenant = suspendTenant;
window.unsuspendTenant = unsuspendTenant;
window.loadAbuseAlerts = loadAbuseAlerts;
window.loadFinancial = loadFinancial;
window.openTenantCreateModal = openTenantCreateModal;
window.closeTenantCreateModal = closeTenantCreateModal;
window.saveNewTenant = saveNewTenant;
window.deleteTenant = deleteTenant;
window.loadAccountConfig = loadAccountConfig;
window.saveAccountProfile = saveAccountProfile;
window.changeAccountPassword = changeAccountPassword;
window.loadWebhooks = loadWebhooks;
window.openWebhookModal = openWebhookModal;
window.closeWebhookModal = closeWebhookModal;
window.saveWebhook = saveWebhook;
window.deleteWebhook = deleteWebhook;
window.testWebhook = testWebhook;

// ── ACCOUNT SETTINGS ─────────────────────────────────────────────
async function loadAccountConfig() {
    try {
        const user = await apiFetch('/auth/me');
        if (!user) return;
        const setV = (id, v) => { const el = document.getElementById(id); if (el) el.value = v || ''; };
        setV('cfgName', user.name);
        setV('cfgEmail', user.email);
        setV('cfgPhone', user.phone);
        loadWebhooks();
    } catch (e) {
        console.error('loadAccountConfig', e);
        showAlert('Erro ao carregar configurações da conta', 'error');
    }
}

async function saveAccountProfile() {
    const name = document.getElementById('cfgName')?.value?.trim();
    const email = document.getElementById('cfgEmail')?.value?.trim();
    const phone = document.getElementById('cfgPhone')?.value?.trim();

    if (!name) { showAlert('O nome não pode estar vazio.', 'error'); return; }

    const payload = {};
    if (name) payload.name = name;
    if (email) payload.email = email;
    if (phone) payload.phone = phone;

    try {
        const res = await apiFetch('/auth/me', {
            method: 'PUT',
            body: JSON.stringify(payload)
        });
        if (!res) return;
        showAlert('✅ Perfil salvo com sucesso!', 'success');
        if (res.email_verification_sent) {
            showAlert('📧 Um link de confirmação foi enviado para o novo e-mail.', 'info');
        }
        // Refresh header display
        loadUser();
    } catch (e) {
        showAlert('Erro ao salvar perfil: ' + e.message, 'error');
    }
}

// ── WEBHOOKS & APIs ──────────────────────────────────────────────
async function loadWebhooks() {
    const tbody = document.getElementById('webhooksBody');
    if (!tbody) return;
    try {
        const webhooks = await apiFetch('/webhooks');
        if (!webhooks || webhooks.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-3">Nenhuma integração registrada.</td></tr>';
            return;
        }
        tbody.innerHTML = webhooks.map(w => `
            <tr>
                <td style="font-weight:700;color:var(--text-primary)">${w.name}</td>
                <td><span class="badge ${w.type === 'webhook' ? 'info' : 'warn'}">${w.type.toUpperCase()}</span></td>
                <td class="text-sm mono text-truncate" style="max-width:200px">${w.url}</td>
                <td>
                    <span class="badge ${w.is_active ? 'success' : 'danger'}">${w.is_active ? 'Ativa' : 'Inativa'}</span>
                    ${w.last_test_status ? `<br><small class="${w.last_test_status === 'ok' ? 'text-success' : 'text-danger'}">${w.last_test_status === 'ok' ? '✅ OK' : '❌ Falha'}</small>` : ''}
                </td>
                <td>
                    <div class="flex-row gap-2">
                        <button class="btn btn-ghost btn-sm" onclick="openWebhookModal(${w.id})" title="Editar">✏️</button>
                        <button class="btn btn-ghost btn-sm" onclick="testWebhook(${w.id})" title="Testar">⚡</button>
                        <button class="btn btn-ghost btn-danger btn-sm" onclick="deleteWebhook(${w.id})" title="Excluir">🗑️</button>
                    </div>
                </td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('loadWebhooks', e);
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-danger py-3">Erro ao carregar integrações.</td></tr>';
    }
}

function openWebhookModal(id = null) {
    const modal = document.getElementById('webhookModal');
    const backdrop = document.getElementById('webhookModalBackdrop');
    if (!modal || !backdrop) return;

    // Reset form
    document.getElementById('webhookId').value = id || '';
    document.getElementById('webhookName').value = '';
    document.getElementById('webhookType').value = 'webhook';
    document.getElementById('webhookUrl').value = '';
    document.getElementById('webhookMethod').value = 'POST';
    document.getElementById('webhookToken').value = '';
    document.getElementById('webhookHeaders').value = '';
    document.getElementById('webhookActive').checked = true;
    document.getElementById('webhookModalTitle').textContent = id ? 'Editar Integração' : 'Registrar Integração';

    if (id) {
        // Load existing data
        apiFetch(`/webhooks/${id}`).then(w => {
            if (!w) return;
            document.getElementById('webhookName').value = w.name;
            document.getElementById('webhookType').value = w.type;
            document.getElementById('webhookUrl').value = w.url;
            document.getElementById('webhookMethod').value = w.method;
            document.getElementById('webhookToken').value = w.token || '';
            document.getElementById('webhookHeaders').value = w.headers ? JSON.stringify(w.headers, null, 2) : '';
            document.getElementById('webhookActive').checked = w.is_active;
        });
    }

    modal.classList.add('active');
    backdrop.classList.add('active');
}

function closeWebhookModal() {
    document.getElementById('webhookModal')?.classList.remove('active');
    document.getElementById('webhookModalBackdrop')?.classList.remove('active');
}

async function saveWebhook() {
    const id = document.getElementById('webhookId').value;
    const name = document.getElementById('webhookName').value.trim();
    const url = document.getElementById('webhookUrl').value.trim();
    if (!name || !url) { showAlert('Nome e URL são obrigatórios', 'error'); return; }

    let headers = null;
    const headersStr = document.getElementById('webhookHeaders').value.trim();
    if (headersStr) {
        try { headers = JSON.parse(headersStr); }
        catch (e) { showAlert('Headers devem ser um JSON válido', 'error'); return; }
    }

    const payload = {
        name,
        url,
        type: document.getElementById('webhookType').value,
        method: document.getElementById('webhookMethod').value,
        token: document.getElementById('webhookToken').value || null,
        headers,
        is_active: document.getElementById('webhookActive').checked
    };

    try {
        const method = id ? 'PUT' : 'POST';
        const endpoint = id ? `/webhooks/${id}` : '/webhooks';
        const res = await apiFetch(endpoint, {
            method,
            body: JSON.stringify(payload)
        });
        if (res) {
            showAlert('✅ Integração salva com sucesso!', 'success');
            closeWebhookModal();
            loadWebhooks();
        }
    } catch (e) {
        showAlert('Erro ao salvar integração: ' + e.message, 'error');
    }
}

function removeIntegration(nodeId) {
    confirmAction('Tem certeza que deseja excluir esta integração?', async () => {
        try {
            await apiFetch(`/master/integrations/${nodeId}`, { method: 'DELETE' });
            showAlert('Integração removida', 'success');
            loadWebhooks(); // Refresh
        } catch (e) { showAlert('Erro: ' + e.message, 'error'); }
    });
}

async function deleteWebhook(id) {
    confirmAction('Tem certeza que deseja excluir esta integração?', async () => {
        try {
            await apiFetch(`/webhooks/${id}`, { method: 'DELETE' });
            showAlert('🗑️ Integração removida.', 'info');
            loadWebhooks();
        } catch (e) {
            showAlert('Erro ao excluir: ' + e.message, 'error');
        }
    });
}

async function testWebhook(id) {
    try {
        showAlert('⚡ Testando conexão...', 'info');
        const res = await apiFetch(`/webhooks/${id}/test`, { method: 'POST' });
        if (res && res.status === 'ok') {
            showAlert(`✅ Sucesso! HTTP ${res.http_status}`, 'success');
        } else {
            showAlert(`❌ Falha: ${res ? res.message : 'Erro desconhecido'}`, 'error');
        }
        loadWebhooks();
    } catch (e) {
        showAlert('Erro ao testar: ' + e.message, 'error');
    }
}

async function changeAccountPassword() {
    const oldPass = document.getElementById('cfgOldPass')?.value;
    const newPass = document.getElementById('cfgNewPass')?.value;
    const confirmPass = document.getElementById('cfgConfirmPass')?.value;

    if (!oldPass || !newPass || !confirmPass) {
        showAlert('Preencha todos os campos de senha.', 'error');
        return;
    }
    if (newPass !== confirmPass) {
        showAlert('A nova senha e a confirmação não coincidem.', 'error');
        return;
    }
    if (newPass.length < 6) {
        showAlert('A nova senha deve ter pelo menos 6 caracteres.', 'error');
        return;
    }

    try {
        const res = await apiFetch('/auth/me/password', {
            method: 'PUT',
            body: JSON.stringify({ current_password: oldPass, new_password: newPass })
        });
        if (!res) return;
        showAlert('🔑 Senha alterada com sucesso!', 'success');
        // Clear fields
        ['cfgOldPass', 'cfgNewPass', 'cfgConfirmPass'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
    } catch (e) {
        let msg = e.message || 'Erro desconhecido';
        if (msg.includes('401')) msg = 'Senha atual incorreta.';
        if (msg.includes('403') && msg.includes('MFA')) msg = 'MFA obrigatório. Configure via app autenticador.';
        showAlert('Erro: ' + msg, 'error');
    }
}

// ── WHATSAPP EVOLUTION ───────────────────────────────────────────
async function loadWhatsAppInstances() {
    try {
        const instances = await apiFetch('/master/whatsapp');
        const tbody = document.getElementById('whatsappInstancesBody');
        if (!tbody) return;
        if (!instances || !instances.length) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:2rem;">Nenhuma instância encontrada</td></tr>';
            return;
        }
        tbody.innerHTML = instances.map(i => {
            const safeName = encodeURIComponent(i.instance_name);
            return `
            <tr>
                <td>#${i.id}</td>
                <td><span class="bold">${i.tenant_name}</span> <span class="text-sm text-muted">(ID: ${i.tenant_id})</span></td>
                <td class="mono">
                    <div class="bold">${i.display_name}</div>
                    <div class="text-sm text-muted">${i.instance_name}</div>
                </td>
                <td>${i.phone_number || '<span class="text-muted text-sm">Não conectado</span>'}</td>
                <td style="max-width:200px">
                <div style="font-size:0.85rem;color:var(--text-muted)">${i.owner_email || 'Sem E-mail'}</div>
            </td>
                <td><span class="badge ${i.status === 'open' || i.status === 'connected' ? 'active' : i.status === 'pending' || i.status === 'connecting' ? 'warn' : 'danger'}">${i.status || 'desconhecido'}</span></td>
                <td>
                    ${i.status !== 'open' && i.status !== 'connected' ? `<button class="btn btn-ghost btn-sm wa-pairing-btn" data-name="${safeName}">🔗 Pareamento</button>` : ''}
                    <button class="btn btn-ghost btn-sm wa-edit-btn" data-name="${safeName}">✏️ Editar</button>
                    <button class="btn btn-ghost btn-danger btn-sm wa-delete-btn" data-name="${safeName}">🗑️ Excluir</button>
                </td>
            </tr>
        `}).join('');

        // Event delegation — evita problemas com nomes que têm espaços no onclick inline
        tbody.querySelectorAll('.wa-edit-btn').forEach(btn => {
            btn.addEventListener('click', () => openWhatsAppEditModal(decodeURIComponent(btn.dataset.name)));
        });
        tbody.querySelectorAll('.wa-delete-btn').forEach(btn => {
            btn.addEventListener('click', () => deleteWhatsAppInstance(decodeURIComponent(btn.dataset.name)));
        });
        tbody.querySelectorAll('.wa-pairing-btn').forEach(btn => {
            btn.addEventListener('click', () => getWhatsAppPairingCode(decodeURIComponent(btn.dataset.name)));
        });

        // Store globally for edit modal
        window._waInstances = instances;
    } catch (e) {
        showAlert('Erro ao carregar instâncias do WhatsApp: ' + e.message, 'error');
    }
}

window.openWhatsAppCreateModal = async function () {
    try {
        const tenants = await apiFetch('/master/tenants');
        const select = document.getElementById('waTenantSelect');
        if (select && tenants) {
            select.innerHTML = '<option value="">-- Selecione o Beneficiário --</option>' +
                '<option value="internal">--- INTERNO / MASTER AGENTE (MAX) ---</option>' +
                tenants.map(t => `<option value="${t.id}">${t.name}</option>`).join('');
        }
        document.getElementById('waInstanceName').value = '';
        document.getElementById('waDisplayName').value = '';
        document.getElementById('waInstanceToken').value = '';
        document.getElementById('whatsappCreateModal').classList.add('active');
    } catch (e) {
        showAlert('Erro ao carregar tenants: ' + e.message, 'error');
    }
};

window.closeWhatsAppCreateModal = function () {
    document.getElementById('whatsappCreateModal').classList.remove('active');
};

window.createWhatsAppInstance = async function () {
    const tenantId = document.getElementById('waTenantSelect').value;
    const instanceName = document.getElementById('waInstanceName').value.trim();
    const displayName = document.getElementById('waDisplayName').value.trim();
    const instanceToken = document.getElementById('waInstanceToken').value.trim();
    const evolUrl = document.getElementById('waEvolUrl').value.trim();
    const evolKey = document.getElementById('waEvolKey').value.trim();
    const ownerEmail = document.getElementById('waOwnerEmail').value.trim();

    if (!tenantId || !instanceName) {
        showAlert('Obrigatório: Selecione o tenant e defina o identificador da instância!', 'warn');
        return;
    }

    // UI Loading state
    const btn = document.querySelector('#whatsappCreateModal .btn-primary');
    const oldText = btn.textContent;
    btn.textContent = 'Criando...';
    btn.disabled = true;

    try {
        const res = await apiFetch('/master/whatsapp', {
            method: 'POST',
            body: JSON.stringify({
                tenant_id: tenantId === 'internal' ? null : parseInt(tenantId),
                instance_name: instanceName,
                display_name: displayName || instanceName,
                instance_token: instanceToken || null,
                evolution_api_url: evolUrl || null,
                evolution_api_key: evolKey || null,
                owner_email: ownerEmail || null
            })
        });
        if (res) {
            const hasWarning = res.warning && res.warning.startsWith('⚠️');
            showAlert(hasWarning ? res.warning : 'Instância criada com sucesso!', hasWarning ? 'warn' : 'success');
            closeWhatsAppCreateModal();
            loadWhatsAppInstances();

            // Show success alert
            setTimeout(() => {
                const statusHtml = hasWarning
                    ? `<div style="background:#422006;border:1px solid #92400e;padding:.75rem;border-radius:8px;margin-bottom:1rem;color:#fbbf24;">${res.warning}</div>`
                    : `<div style="background:#052e16;border:1px solid #166534;padding:.75rem;border-radius:8px;margin-bottom:1rem;color:#4ade80;">✅ Instância <strong>${instanceName}</strong> registrada e configurada automaticamente!</div>`;
                const instructions = `
                    <div style="text-align:left;">
                        ${statusHtml}
                        <p>O Webhook já foi injetado globalmente pela nossa infraestrutura Docker Compose.</p>
                        <p style="margin-top:1rem;color:#94a3b8;font-size:.85rem;">Você não precisa mais configurar nada na aba Webhook da Evolution API.</p>
                    </div>
                `;
                showGenericModal('Instância do WhatsApp', instructions);
            }, 500);
        }

    } catch (e) {
        console.error(e);
        showAlert('Erro ao criar instância: ' + e.message, 'error');
    } finally {
        btn.textContent = oldText;
        btn.disabled = false;
    }
};

window.openWhatsAppEditModal = function (instanceName) {
    if (!window._waInstances) return;
    const inst = window._waInstances.find(i => i.instance_name === instanceName);
    if (!inst) return;

    document.getElementById('waEditInstanceName').value = inst.instance_name;
    document.getElementById('waEditDisplayName').value = inst.display_name || '';
    document.getElementById('waEditInstanceToken').value = ''; // Don't show existing token for security
    document.getElementById('waEditEvolUrl').value = inst.evolution_api_url || '';
    document.getElementById('waEditEvolKey').value = inst.evolution_api_key || ''; // Will update if provided
    document.getElementById('waEditOwnerEmail').value = inst.owner_email || '';

    document.getElementById('whatsappEditModal').classList.add('active');
};

window.closeWhatsAppEditModal = function () {
    document.getElementById('whatsappEditModal').classList.remove('active');
};

window.editWhatsAppInstance = async function () {
    const instanceName = document.getElementById('waEditInstanceName').value;
    const displayName = document.getElementById('waEditDisplayName').value.trim();
    const instanceToken = document.getElementById('waEditInstanceToken').value.trim();
    const evolUrl = document.getElementById('waEditEvolUrl').value.trim();
    const evolKey = document.getElementById('waEditEvolKey').value.trim();
    const ownerEmail = document.getElementById('waEditOwnerEmail').value.trim();

    if (!instanceName) return;

    const btn = document.querySelector('#whatsappEditModal .btn-primary');
    const oldText = btn.textContent;
    btn.textContent = 'Salvando...';
    btn.disabled = true;

    try {
        const body = {};
        if (displayName) body.display_name = displayName;
        if (instanceToken) body.instance_token = instanceToken;
        if (evolUrl !== undefined) body.evolution_api_url = evolUrl || null;
        if (evolKey !== undefined && evolKey !== '') body.evolution_api_key = evolKey || null;
        if (ownerEmail !== undefined) body.owner_email = ownerEmail || null;

        const res = await apiFetch(`/master/whatsapp/${encodeURIComponent(instanceName)}`, {
            method: 'PUT',
            body: JSON.stringify(body)
        });

        if (res) {
            showAlert('Instância atualizada com sucesso!', 'success');
            closeWhatsAppEditModal();
            loadWhatsAppInstances();
        }
    } catch (e) {
        console.error(e);
        showAlert('Erro ao atualizar: ' + e.message, 'error');
    } finally {
        btn.textContent = oldText;
        btn.disabled = false;
    }
};

window.deleteWhatsAppInstance = function deleteWhatsAppInstance(instanceName) {
    confirmAction(`Tem certeza que deseja remover a instância "${instanceName}"? A conexão com o WhatsApp será desfeita.`, async () => {
        try {
            await apiFetch(`/master/whatsapp/${instanceName}`, { method: 'DELETE' });
            showAlert('Instância removida com sucesso.', 'info');
            loadWhatsAppInstances();
        } catch (e) {
            showAlert('Erro ao deletar: ' + e.message, 'error');
        }
    });
};

async function getWhatsAppPairingCode(instanceName) {
    const phone = prompt('Digite o número do WhatsApp (ex: 5511999999999):');
    if (!phone) return;

    try {
        showAlert('Gerando código de pareamento...', 'info');
        const res = await apiFetch(`/master/whatsapp/${instanceName}/pairing-code?phone=${phone}`);
        if (res && res.code) {
            const html = `
                <div style="text-align:center;">
                    <p>Use o código abaixo no seu WhatsApp (Configurações > Dispositivos Conectados > Conectar com número de telefone):</p>
                    <div style="font-size:3rem; font-weight:bold; letter-spacing:10px; margin:2rem 0; color:var(--primary); font-family:serif;">
                        ${res.code}
                    </div>
                    <button class="btn btn-ghost w-100" onclick="copyToClipboard('${res.code}')">Copiar Código</button>
                </div>
            `;
            showGenericModal('Código de Pareamento', html);
        } else {
            throw new Error(res?.error || 'Erro ao gerar código');
        }
    } catch (e) {
        showAlert('Erro: ' + e.message, 'error');
    }
}

// ── UTILS ────────────────────────────────────────────────────────
function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}
function fmt(n) { return Number(n || 0).toLocaleString('pt-BR'); }

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showAlert('Copiado para a área de transferência!', 'success');
    }).catch(err => {
        console.error('Erro ao copiar: ', err);
        showAlert('Falha ao copiar texto.', 'error');
    });
}

function showGenericModal(title, htmlBody) {
    document.getElementById('genericModalTitle').textContent = title;
    document.getElementById('genericModalBody').innerHTML = htmlBody;
    document.getElementById('genericModal').classList.add('active');
}

function closeGenericModal() {
    document.getElementById('genericModal').classList.remove('active');
}

// ── REGISTRATION VALIDATIONS ──────────────────────────────────────
async function loadRegistrations() {
    const body = document.getElementById('registrationsBody');
    if (!body) return;
    body.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:2rem;"><span class=\"skeleton\"></span></td></tr>';

    try {
        const regs = await apiFetch('/master/registrations');
        if (!regs || !regs.length) {
            body.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--text-muted);">Nenhum registro de validação encontrado.</td></tr>';
            return;
        }

        body.innerHTML = regs.map(r => {
            let badgeClass = 'badge';
            if (r.event_type.includes('success') || r.event_type.includes('identified') || r.event_type.includes('validated') || r.event_type.includes('registered')) {
                badgeClass += ' success';
            } else if (r.event_type.includes('failure')) {
                badgeClass += ' danger';
            }

            const date = new Date(r.created_at).toLocaleString('pt-BR');
            return `
                <tr>
                    <td class="text-sm">${date}</td>
                    <td><span class="${badgeClass}">${r.event_type}</span></td>
                    <td class="bold">${r.username || 'Sistema'}</td>
                    <td class="text-sm text-muted">${r.ip_address || '—'}</td>
                    <td class="text-sm">${r.details || '—'}</td>
                </tr>
            `;
        }).join('');
    } catch (e) {
        console.error('loadRegistrations', e);
        body.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--red);">Erro ao carregar registros: ${e.message}</td></tr>`;
    }
}

// ══════════════════════════════════════════════════════════════════
// WHATSAPP / EVOLUTION API MANAGEMENT
