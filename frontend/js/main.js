const API_BASE = '/api/v1';
const AUTH_URL = '/login.html';

let _statsInterval = null;
let _isRefreshing = false;
let _refreshQueue = [];

// ── JWT Utils ────────────────────────────────────────────────────────────────
function b64DecodeUnicode(str) {
    try {
        return decodeURIComponent(atob(str).split('').map(c =>
            '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)
        ).join(''));
    } catch (e) {
        return atob(str);
    }
}

function getTokenPayload(token) {
    try {
        const base64Url = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
        return JSON.parse(b64DecodeUnicode(base64Url));
    } catch (_) {
        return null;
    }
}

// Retorna true se o token expira em menos de 60 segundos
function isTokenExpiredOrExpiring(token) {
    const payload = getTokenPayload(token);
    if (!payload || !payload.exp) return true;
    return payload.exp < (Date.now() / 1000) + 60;
}

// ── Refresh Token ─────────────────────────────────────────────────────────────
async function refreshAccessToken() {
    try {
        const res = await fetch(`${API_BASE}/auth/refresh`, {
            method: 'POST',
            credentials: 'include',  // envia o HttpOnly refresh cookie
            headers: { 'Content-Type': 'application/json' }
        });
        if (!res.ok) throw new Error('Refresh falhou');
        const data = await res.json();
        localStorage.setItem('token', data.access_token);
        return data.access_token;
    } catch (_) {
        return null;
    }
}

// ── Auth Guard ────────────────────────────────────────────────────────────────
function redirectToLogin() {
    // Para o interval antes de redirecionar
    if (_statsInterval) {
        clearInterval(_statsInterval);
        _statsInterval = null;
    }
    localStorage.removeItem('token');
    window.location.href = AUTH_URL;
}

async function checkAuth() {
    let token = localStorage.getItem('token');
    if (!token) {
        redirectToLogin();
        return null;
    }

    // Se o token está prestes a expirar, tenta renovar silenciosamente
    if (isTokenExpiredOrExpiring(token)) {
        token = await refreshAccessToken();
        if (!token) {
            redirectToLogin();
            return null;
        }
    }

    return token;
}

// ── Authenticated Fetch com retry após refresh ────────────────────────────────
async function authFetch(url, options = {}) {
    let token = await checkAuth();
    if (!token) return null;

    if (!options.cache) options.cache = 'no-store';

    const makeRequest = (t) => {
        const payload = getTokenPayload(t);
        const tenantId = payload?.tenant_id;
        return fetch(url, {
            ...options,
            headers: {
                ...options.headers,
                'Authorization': `Bearer ${t}`,
                ...(tenantId ? { 'X-Tenant-ID': String(tenantId) } : {})
            }
        });
    };

    let response = await makeRequest(token);

    // Se 401, tenta refresh uma vez antes de deslogar
    if (response.status === 401) {
        if (_isRefreshing) {
            // Aguarda o refresh em andamento
            return new Promise((resolve) => {
                _refreshQueue.push(async (newToken) => {
                    resolve(newToken ? await makeRequest(newToken) : null);
                });
            });
        }

        _isRefreshing = true;
        const newToken = await refreshAccessToken();
        _isRefreshing = false;

        if (newToken) {
            // Processa fila de requests que estavam esperando
            _refreshQueue.forEach(cb => cb(newToken));
            _refreshQueue = [];
            response = await makeRequest(newToken);
        } else {
            _refreshQueue.forEach(cb => cb(null));
            _refreshQueue = [];
            redirectToLogin();
            return null;
        }
    }

    return response;
}

// ── User ──────────────────────────────────────────────────────────────────────
async function loadUser() {
    try {
        const response = await authFetch('/api/v1/auth/me');
        if (!response) return;
        const user = await response.json();

        const nameDisplay = document.getElementById('userNameDisplay');
        const roleDisplay = document.getElementById('userRoleDisplay');
        const avatarDisplay = document.getElementById('userAvatar');

        if (nameDisplay) nameDisplay.textContent = user.name;
        if (roleDisplay) roleDisplay.textContent = user.company_role || (user.role === 'admin' ? 'Administrador' : 'Colaborador');

        if (avatarDisplay) {
            if (user.avatar_url) {
                avatarDisplay.innerHTML = `<img src="${user.avatar_url}" alt="Avatar" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`;
            } else {
                avatarDisplay.textContent = user.name.charAt(0).toUpperCase();
            }
        }

        const pName   = document.getElementById('myProfileName');
        const pRole   = document.getElementById('myProfileRole');
        const pAvatar = document.getElementById('myProfileAvatarUrl');
        const pBio    = document.getElementById('myProfileBio');

        if (pName)   pName.value   = user.name || '';
        if (pRole)   pRole.value   = user.company_role || '';
        if (pAvatar) pAvatar.value = user.avatar_url || '';
        if (pBio)    pBio.value    = user.bio || '';

    } catch (error) {
        console.error('Erro ao carregar usuário:', error);
    }
}

function logout() {
    redirectToLogin();
}

// ── Globals ───────────────────────────────────────────────────────────────────
let customersData = [];
let meetingsData = [];
let editingCustomerId = null;
let editingMeetingId = null;

// ── Navigation ────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const navItems = document.querySelectorAll('.nav-item');
    const sections = document.querySelectorAll('.view-section');
    const pageTitle = document.getElementById('pageTitle');

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            navItems.forEach(n => n.classList.remove('active'));
            sections.forEach(s => s.classList.remove('active'));
            item.classList.add('active');
            const targetId = item.dataset.target;
            const targetSection = document.getElementById(targetId);

            if (targetSection) {
                targetSection.classList.add('active');
                if (pageTitle) pageTitle.textContent = item.textContent.trim();

                if (targetId === 'customers')     loadCustomers();
                if (targetId === 'meetings')      loadMeetings();
                if (targetId === 'tickets')       loadTickets();
                if (targetId === 'conversations') loadConversations();
                if (targetId === 'analytics')     loadAnalytics();
                if (targetId === 'dashboard')     loadStats();
                if (targetId === 'profiles')      loadProfiles();
                if (targetId === 'webhooks')      loadWebhooks();
                if (targetId === 'automations')   loadAutomations();
                if (targetId === 'prompt-wizard') initWizard();
            }
        });
    });

    loadUser();
    loadStats();
    loadCustomers();

    // Interval guardado para poder cancelar em caso de 401
    _statsInterval = setInterval(loadStats, 30000);

    loadThemePreferences();

    const avatarFile = document.getElementById('myProfileAvatarFile');
    if (avatarFile) avatarFile.addEventListener('change', () => handleImageUpload('myProfileAvatarFile', 'myProfileAvatarUrl'));

    const logoFile = document.getElementById('panelLogoFile');
    if (logoFile) logoFile.addEventListener('change', () => handleImageUpload('panelLogoFile', 'panelLogoUrl'));
});

// ── Alerts ────────────────────────────────────────────────────────────────────
function showAlert(message, type = 'success') {
    const alert = document.createElement('div');
    alert.className = `alert ${type}`;
    alert.textContent = message;
    const container = document.getElementById('alertContainer');
    if (container) container.appendChild(alert);
    setTimeout(() => alert.remove(), 5000);
}

// ── Stats ─────────────────────────────────────────────────────────────────────
async function loadStats() {
    try {
        const response = await authFetch(`${API_BASE}/stats?t=${Date.now()}`, { cache: 'no-store' });
        if (!response) return;
        const data = await response.json();
        const ids = ['activeCustomers', 'openTickets', 'scheduledMeetings', 'todayConversations'];
        ids.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.textContent = data[id.replace(/[A-Z]/g, l => `_${l.toLowerCase()}`)] || 0;
        });
    } catch (error) {
        console.error('Erro ao carregar estatísticas:', error);
    }
}

// ── Customers ─────────────────────────────────────────────────────────────────
async function loadCustomers() {
    try {
        const response = await authFetch(`${API_BASE}/customers?t=${Date.now()}`, { cache: 'no-store' });
        if (!response) return;
        const customers = await response.json();
        customersData = customers;
        const tbody = document.getElementById('customersBody');
        if (!tbody) return;

        if (customers.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#9ca3af;padding:1rem;">Nenhum cliente registrado</td></tr>';
            populateMeetingCustomers();
            return;
        }

        tbody.innerHTML = customers.map(c => {
            let statusBadge = '';
            switch (c.status) {
                case 'briefing':  statusBadge = '<span class="badge pending">Briefing</span>'; break;
                case 'proposal':  statusBadge = '<span class="badge" style="background:#8b5cf6">Proposta</span>'; break;
                case 'monthly':   statusBadge = '<span class="badge completed">Mensal</span>'; break;
                case 'completed': statusBadge = '<span class="badge" style="background:#6b7280">Finalizado</span>'; break;
                default:          statusBadge = '<span class="badge active">Em Processo</span>';
            }
            return `
            <tr>
                <td>#${c.id}</td>
                <td><strong>${c.name}</strong></td>
                <td>${c.company || '-'}</td>
                <td>${c.phone}</td>
                <td>${c.email || '-'}</td>
                <td>${statusBadge}</td>
                <td><button class="btn-secondary" style="padding:5px 10px;font-size:0.8rem;" onclick="editCustomer(${c.id})">Editar</button></td>
            </tr>`;
        }).join('');

        populateMeetingCustomers();
    } catch (error) {
        console.error('Erro ao carregar clientes:', error);
    }
}

// ── Tickets ───────────────────────────────────────────────────────────────────
async function loadTickets() {
    try {
        const response = await authFetch(`${API_BASE}/tickets?t=${Date.now()}`, { cache: 'no-store' });
        if (!response) return;
        const tickets = await response.json();
        const tbody = document.getElementById('ticketsBody');
        if (!tbody) return;

        if (tickets.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#9ca3af;padding:1rem;">Nenhum ticket aberto</td></tr>';
            return;
        }

        tbody.innerHTML = tickets.map(t => `
            <tr>
                <td>#${t.id}</td>
                <td>${t.customer_name}</td>
                <td>${t.subject}</td>
                <td><span class="badge pending">Aberto</span></td>
                <td><span class="badge">${t.priority}</span></td>
                <td>${new Date(t.created_at).toLocaleDateString('pt-BR')}</td>
                <td><button class="btn-secondary" style="padding:5px 10px;font-size:0.8rem;" onclick="viewTicket(${t.id})">Ver</button></td>
            </tr>`).join('');
    } catch (error) {
        console.error('Erro ao carregar tickets:', error);
    }
}

// ── Meetings ──────────────────────────────────────────────────────────────────
async function loadMeetings() {
    try {
        const response = await authFetch(`${API_BASE}/meetings?t=${Date.now()}`, { cache: 'no-store' });
        if (!response) return;
        const meetings = await response.json();
        meetingsData = meetings;
        const tbody = document.getElementById('meetingsBody');
        if (!tbody) return;

        if (meetings.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#9ca3af;padding:1rem;">Nenhuma reunião agendada</td></tr>';
            return;
        }

        tbody.innerHTML = meetings.map(m => `
            <tr>
                <td>${m.customer_name}</td>
                <td>${m.type === 'briefing' ? '🎯 Briefing' : '💼 Proposta'}</td>
                <td>${new Date(m.date).toLocaleDateString('pt-BR')}</td>
                <td>${m.time}</td>
                <td><span class="badge completed">Agendada</span></td>
                <td><button class="btn-secondary" style="padding:5px 10px;font-size:0.8rem;" onclick="editMeeting(${m.id})">Editar</button></td>
            </tr>`).join('');
    } catch (error) {
        console.error('Erro ao carregar reuniões:', error);
    }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function populateMeetingCustomers() {
    const select = document.getElementById('meetingCustomer');
    if (select && customersData.length > 0) {
        select.innerHTML = '<option value="">Selecione um cliente...</option>' +
            customersData.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
    }
}

// ── Customer Modal ────────────────────────────────────────────────────────────
function openCustomerModal() {
    editingCustomerId = null;
    document.getElementById('customerModal').classList.add('active');
    document.getElementById('customerName').value = '';
    document.getElementById('customerPhone').value = '';
    document.getElementById('customerEmail').value = '';
    document.getElementById('customerCompany').value = '';
    document.getElementById('customerDemand').value = '';
    document.getElementById('customerStatus').value = 'em_processo';
    document.querySelector('#customerModal h2').textContent = 'Novo Cliente';
    document.getElementById('btnSaveCustomer').textContent = 'Criar Cliente';
    document.getElementById('btnDeleteCustomer').style.display = 'none';
}

function closeCustomerModal() {
    document.getElementById('customerModal').classList.remove('active');
}

function editCustomer(id) {
    const customer = customersData.find(c => c.id === id);
    if (!customer) return;
    editingCustomerId = id;
    document.getElementById('customerName').value = customer.name;
    document.getElementById('customerPhone').value = customer.phone;
    document.getElementById('customerEmail').value = customer.email || '';
    document.getElementById('customerCompany').value = customer.company || '';
    document.getElementById('customerDemand').value = customer.initial_demand || '';
    document.getElementById('customerStatus').value = customer.status || 'em_processo';
    document.querySelector('#customerModal h2').textContent = 'Editar Cliente';
    document.getElementById('btnSaveCustomer').textContent = 'Salvar Alterações';
    document.getElementById('btnDeleteCustomer').style.display = 'block';
    document.getElementById('customerModal').classList.add('active');
}

async function deleteCustomerFromModal() {
    if (!editingCustomerId) return;
    if (!confirm('Tem certeza que deseja excluir este cliente?')) return;
    try {
        await authFetch(`${API_BASE}/customers/${editingCustomerId}`, { method: 'DELETE' });
        showAlert('Cliente excluído com sucesso!', 'success');
        closeCustomerModal();
        loadCustomers();
        loadStats();
    } catch (error) {
        showAlert('Erro ao excluir cliente', 'error');
    }
}

async function saveCustomer(e) {
    e.preventDefault();
    try {
        const method = editingCustomerId ? 'PUT' : 'POST';
        const url = editingCustomerId ? `${API_BASE}/customers/${editingCustomerId}` : `${API_BASE}/customers`;
        await authFetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: document.getElementById('customerName').value,
                phone: document.getElementById('customerPhone').value,
                email: document.getElementById('customerEmail').value,
                company: document.getElementById('customerCompany').value,
                initial_demand: document.getElementById('customerDemand').value,
                status: document.getElementById('customerStatus').value
            })
        });
        showAlert(editingCustomerId ? 'Cliente atualizado!' : 'Cliente criado!', 'success');
        closeCustomerModal();
        loadCustomers();
        loadStats();
    } catch (error) {
        showAlert('Erro ao salvar cliente', 'error');
    }
}

// ── Meeting Modal ─────────────────────────────────────────────────────────────
function openMeetingModal() {
    editingMeetingId = null;
    document.getElementById('meetingModal').classList.add('active');
    document.getElementById('meetingCustomer').value = '';
    document.getElementById('meetingType').value = 'briefing';
    document.getElementById('meetingDate').value = '';
    document.getElementById('meetingTime').value = '';
    document.getElementById('meetingNotes').value = '';
    document.querySelector('#meetingModal h2').textContent = 'Agendar Reunião';
    document.getElementById('btnSaveMeeting').textContent = 'Agendar';
    document.getElementById('btnDeleteMeeting').style.display = 'none';
}

function closeMeetingModal() {
    document.getElementById('meetingModal').classList.remove('active');
}

function editMeeting(id) {
    const meeting = meetingsData.find(m => m.id === id);
    if (!meeting) return;
    editingMeetingId = id;
    document.getElementById('meetingCustomer').value = meeting.customer_id;
    document.getElementById('meetingType').value = meeting.type;
    document.getElementById('meetingDate').value = meeting.date;
    document.getElementById('meetingTime').value = meeting.time.substring(0, 5);
    document.getElementById('meetingNotes').value = meeting.notes || '';
    document.querySelector('#meetingModal h2').textContent = 'Editar Reunião';
    document.getElementById('btnSaveMeeting').textContent = 'Salvar Alterações';
    document.getElementById('btnDeleteMeeting').style.display = 'block';
    document.getElementById('meetingModal').classList.add('active');
}

async function saveMeeting(e) {
    e.preventDefault();
    try {
        const method = editingMeetingId ? 'PUT' : 'POST';
        const url = editingMeetingId ? `${API_BASE}/meetings/${editingMeetingId}` : `${API_BASE}/meetings`;
        await authFetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                customer_id: document.getElementById('meetingCustomer').value,
                type: document.getElementById('meetingType').value,
                date: document.getElementById('meetingDate').value,
                time: document.getElementById('meetingTime').value,
                notes: document.getElementById('meetingNotes').value
            })
        });
        showAlert(editingMeetingId ? 'Reunião atualizada!' : 'Reunião agendada!', 'success');
        closeMeetingModal();
        loadMeetings();
        loadStats();
    } catch (error) {
        showAlert('Erro ao salvar reunião', 'error');
    }
}

async function deleteMeetingFromModal() {
    if (!editingMeetingId) return;
    if (!confirm('Tem certeza que deseja excluir esta reunião?')) return;
    try {
        await authFetch(`${API_BASE}/meetings/${editingMeetingId}`, { method: 'DELETE' });
        showAlert('Reunião excluída com sucesso!', 'success');
        closeMeetingModal();
        loadMeetings();
        loadStats();
    } catch (error) {
        showAlert('Erro ao excluir reunião', 'error');
    }
}

function viewTicket(id) {
    alert('Funcionalidade de ver ticket em breve.');
}

// ── Conversations ─────────────────────────────────────────────────────────────
async function loadConversations() {
    const container = document.getElementById('conversationsList');
    if (!container) return;
    container.innerHTML = '<p style="text-align:center;color:#6b7280;padding:2rem;">Carregando histórico...</p>';

    try {
        const response = await authFetch(`${API_BASE}/conversations?t=${Date.now()}`);
        if (response && response.ok) {
            const conversations = await response.json();
            if (conversations.length === 0) {
                container.innerHTML = '<p style="text-align:center;color:#6b7280;padding:2rem;">Nenhuma conversa encontrada.</p>';
                return;
            }
            container.innerHTML = conversations.map(c => `
                <div style="padding:1rem;border-bottom:1px solid #e5e7eb;cursor:pointer;" onclick="viewConversationDetail(${c.id})">
                    <div style="font-weight:bold;">${c.customer_name || c.phone}</div>
                    <div style="font-size:0.8rem;color:#6b7280;">${new Date(c.last_message_at).toLocaleString()}</div>
                    <div style="margin-top:0.5rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#4b5563;">${c.last_message_preview || '...'}</div>
                </div>`).join('');
        } else {
            container.innerHTML = '<p style="text-align:center;color:#ef4444;padding:2rem;">Erro ao carregar (API pendente)</p>';
        }
    } catch (error) {
        container.innerHTML = '<p style="text-align:center;color:#ef4444;padding:2rem;">Erro ao carregar conversas.</p>';
    }
}

// ── Chat Test ─────────────────────────────────────────────────────────────────
async function sendTestMessage() {
    const input = document.getElementById('chatTestInput');
    const message = input.value.trim();
    if (!message) return;

    const messagesDiv = document.getElementById('chatTestMessages');
    const userDiv = document.createElement('div');
    userDiv.className = 'message user';
    userDiv.textContent = message;
    messagesDiv.appendChild(userDiv);
    input.value = '';
    messagesDiv.scrollTop = messagesDiv.scrollHeight;

    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message agent';
    loadingDiv.textContent = 'Digitando...';
    messagesDiv.appendChild(loadingDiv);

    try {
        const response = await authFetch(`${API_BASE}/chat/test`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });
        loadingDiv.remove();
        if (response && response.ok) {
            const data = await response.json();
            const agentDiv = document.createElement('div');
            agentDiv.className = 'message agent';
            agentDiv.textContent = data.reply;
            messagesDiv.appendChild(agentDiv);
        } else {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'message agent';
            errorDiv.style.color = 'red';
            errorDiv.textContent = 'Erro ao processar mensagem.';
            messagesDiv.appendChild(errorDiv);
        }
    } catch (error) {
        loadingDiv.remove();
    }
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// ── Analytics ─────────────────────────────────────────────────────────────────
let channelsChart = null;
let funnelChart = null;

async function loadAnalytics() {
    try {
        const response = await authFetch(`${API_BASE}/analytics/dashboard`);
        if (!response) return;
        const data = await response.json();

        document.getElementById('stat-automation-rate').innerText = data.performance.automation_rate + '%';
        document.getElementById('stat-csat').innerText = data.performance.csat;
        document.getElementById('stat-leads').innerText = data.business.new_leads_30d;

        let totalTickets = 0;
        if (data.overview.tickets_today) {
            totalTickets = Object.values(data.overview.tickets_today).reduce((a, b) => a + b, 0);
        }
        document.getElementById('stat-tickets-today').innerText = totalTickets;

        const channelCtx = document.getElementById('channelsChart').getContext('2d');
        if (channelsChart) channelsChart.destroy();
        channelsChart = new Chart(channelCtx, {
            type: 'doughnut',
            data: {
                labels: Object.keys(data.overview.channels),
                datasets: [{ data: Object.values(data.overview.channels), backgroundColor: ['#f56954','#00a65a','#f39c12','#00c0ef','#3c8dbc','#d2d6de'] }]
            },
            options: { maintainAspectRatio: false, responsive: true }
        });

        const funnelCtx = document.getElementById('funnelChart').getContext('2d');
        if (funnelChart) funnelChart.destroy();
        const funnelOrder = ['em_processo', 'briefing', 'proposal', 'monthly', 'completed'];
        funnelChart = new Chart(funnelCtx, {
            type: 'bar',
            data: {
                labels: funnelOrder.map(l => l.toUpperCase()),
                datasets: [{ label: 'Clientes por Fase', data: funnelOrder.map(s => data.business.funnel[s] || 0), backgroundColor: '#3c8dbc' }]
            },
            options: { indexAxis: 'y', maintainAspectRatio: false, responsive: true }
        });
    } catch (error) {
        console.error('Error loading analytics:', error);
    }
}

// ── Tema / Branding ───────────────────────────────────────────────────────────
const PRESET_COLORS = [
    { color: '#6366f1', label: 'Índigo (padrão)' },
    { color: '#8b5cf6', label: 'Violeta' },
    { color: '#ec4899', label: 'Rosa' },
    { color: '#f59e0b', label: 'Âmbar' },
    { color: '#10b981', label: 'Esmeralda' },
    { color: '#0ea5e9', label: 'Céu' },
    { color: '#ef4444', label: 'Vermelho' },
    { color: '#0f172a', label: 'Slate Dark' },
];

function renderColorSwatches() {
    const container = document.getElementById('colorSwatches');
    if (!container) return;
    const current = localStorage.getItem('accentColor') || '#6366f1';
    container.innerHTML = PRESET_COLORS.map(p => `
        <div class="color-swatch${p.color === current ? ' selected' : ''}"
             style="background:${p.color};"
             title="${p.label}"
             onclick="applyAccentColor('${p.color}', this)">
        </div>`).join('');
}

function applyAccentColor(color, swatchEl = null) {
    document.documentElement.style.setProperty('--accent', color);
    document.documentElement.style.setProperty('--accent-glow', color + '40');
    document.documentElement.style.setProperty('--accent-subtle', color + '14');
    const picker = document.getElementById('customAccent');
    if (picker) picker.value = color;
    document.querySelectorAll('.color-swatch').forEach(s => s.classList.remove('selected'));
    if (swatchEl) swatchEl.classList.add('selected');
    localStorage.setItem('accentColor', color);
}

async function saveThemePreferences() {
    const prefs = {
        accentColor:  document.documentElement.style.getPropertyValue('--accent') || '#6366f1',
        panelName:    document.getElementById('panelName')?.value || 'Auto Tech Lith',
        panelEmoji:   document.getElementById('panelEmoji')?.value || '🤖',
        panelLogoUrl: document.getElementById('panelLogoUrl')?.value || ''
    };
    try {
        const configs = Object.keys(prefs).map(k => ({ key: k, value: prefs[k] }));
        await authFetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ configs })
        });
        showAlert('🎨 Marca global salva com sucesso!', 'success');
    } catch (e) {
        showAlert('Erro ao salvar personalização', 'error');
    }
}

async function loadThemePreferences() {
    try {
        const response = await fetch('/api/config');
        if (response && response.ok) {
            const prefs = await response.json();
            if (prefs.accentColor) applyAccentColor(prefs.accentColor);
            if (prefs.panelName) {
                const sidebarName = document.getElementById('sidebarName');
                const panelNameInput = document.getElementById('panelName');
                if (sidebarName) sidebarName.textContent = prefs.panelName;
                if (panelNameInput) panelNameInput.value = prefs.panelName;
            }
            if (prefs.panelEmoji) {
                const sidebarEmoji = document.getElementById('sidebarEmoji');
                const panelEmojiInput = document.getElementById('panelEmoji');
                if (sidebarEmoji) sidebarEmoji.textContent = prefs.panelEmoji;
                if (panelEmojiInput) panelEmojiInput.value = prefs.panelEmoji;
            }
            if (prefs.panelLogoUrl) {
                const panelLogoUrlInput = document.getElementById('panelLogoUrl');
                if (panelLogoUrlInput) panelLogoUrlInput.value = prefs.panelLogoUrl;
                updateSidebarLogo();
            }
        }
    } catch (e) {
        console.warn('Erro ao carregar configurações globais:', e);
    }
    renderColorSwatches();
}

async function resetTheme() {
    if (!confirm('Tem certeza que deseja apagar a personalização global?')) return;
    document.getElementById('panelName').value = 'Auto Tech Lith';
    document.getElementById('panelEmoji').value = '🤖';
    document.getElementById('panelLogoUrl').value = '';
    applyAccentColor('#6366f1');
    renderColorSwatches();
    await saveThemePreferences();
    showAlert('↩ Tema restaurado ao padrão e salvo.', 'success');
}

function switchSettingsTab(tabName) {
    document.querySelectorAll('.inner-tab').forEach(t => t.classList.remove('active'));
    ['settingsProfilePanel','settingsBrandingPanel','settingsWebhooksPanel','settingsPromptPanel'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
    const map = {
        profile:  ['tabMyProfile',         'settingsProfilePanel'],
        branding: ['tabBranding',          'settingsBrandingPanel'],
        webhooks: ['tabSettingsWebhooks',  'settingsWebhooksPanel'],
        prompt:   ['tabSettingsPrompt',    'settingsPromptPanel'],
    };
    if (map[tabName]) {
        const [tabId, panelId] = map[tabName];
        document.getElementById(tabId)?.classList.add('active');
        const panel = document.getElementById(panelId);
        if (panel) panel.style.display = 'block';
    }
}

function updateSidebarLogo() {
    const url = document.getElementById('panelLogoUrl')?.value;
    const header = document.querySelector('.sidebar-header h2');
    if (!header) return;
    if (url) {
        header.innerHTML = `<img src="${url}" alt="Logo" style="max-height:28px;width:auto;vertical-align:middle;margin-right:8px;"> <span id="sidebarName">${document.getElementById('panelName')?.value || 'Auto Tech Lith'}</span><span id="sidebarEmoji" style="display:none;"></span>`;
    } else {
        const emoji = document.getElementById('panelEmoji')?.value || '🤖';
        const name  = document.getElementById('panelName')?.value  || 'Auto Tech Lith';
        header.innerHTML = `<span id="sidebarEmoji">${emoji}</span> <span id="sidebarName">${name}</span>`;
    }
}

async function saveMyProfile(e) {
    e.preventDefault();
    const data = {
        name:         document.getElementById('myProfileName').value,
        company_role: document.getElementById('myProfileRole').value,
        avatar_url:   document.getElementById('myProfileAvatarUrl').value,
        bio:          document.getElementById('myProfileBio').value
    };
    try {
        const response = await authFetch('/api/v1/auth/me', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (response && response.ok) {
            showAlert('👤 Perfil atualizado com sucesso!', 'success');
            loadUser();
        }
    } catch (error) {
        showAlert('Erro ao salvar perfil', 'error');
    }
}

// ── Automações ────────────────────────────────────────────────────────────────
async function loadAutomations() {
    try {
        const response = await authFetch(`${API_BASE}/automations`);
        if (!response) return;
        const automations = await response.json();
        const tbody = document.getElementById('automationsBody');
        if (!tbody) return;

        if (automations.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#9ca3af;padding:1rem;">Nenhuma regra configurada</td></tr>';
            return;
        }
        tbody.innerHTML = automations.map(a => `
            <tr>
                <td>${a.is_active ? '✅' : '❌'}</td>
                <td><strong>${a.name}</strong></td>
                <td><span class="badge" style="background:#6366f1;color:white">${a.trigger_event}</span></td>
                <td><span class="badge" style="background:#10b981;color:white">${a.action_type}</span></td>
                <td><button class="btn-danger btn-sm" onclick="deleteAutomation(${a.id})">Remover</button></td>
            </tr>`).join('');
    } catch (e) {
        console.error('Erro ao carregar automações:', e);
    }
}

function openAutomationModal() { document.getElementById('automationModal').classList.add('active'); }
function closeAutomationModal() { document.getElementById('automationModal').classList.remove('active'); }

async function saveAutomation(e) {
    e.preventDefault();
    let payload = {};
    try { payload = JSON.parse(document.getElementById('autoPayload').value || '{}'); }
    catch (_) { showAlert('JSON de payload inválido', 'error'); return; }

    const data = {
        name:           document.getElementById('autoName').value,
        trigger_event:  document.getElementById('autoTrigger').value,
        action_type:    document.getElementById('autoAction').value,
        action_payload: payload,
        is_active:      document.getElementById('autoActive').checked
    };
    try {
        const res = await authFetch(`${API_BASE}/automations`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (res && res.ok) {
            showAlert('⚡ Regra de automação salva!', 'success');
            closeAutomationModal();
            loadAutomations();
        }
    } catch (err) {
        showAlert('Erro ao salvar automação', 'error');
    }
}

async function deleteAutomation(id) {
    if (!confirm('Excluir esta regra?')) return;
    try {
        await authFetch(`${API_BASE}/automations/${id}`, { method: 'DELETE' });
        loadAutomations();
    } catch (e) {
        showAlert('Erro ao remover automação', 'error');
    }
}

async function exportCustomersCSV() {
    try {
        const response = await authFetch(`${API_BASE}/reports/customers/csv`);
        if (!response) return;
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `clientes_export_${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        showAlert('📥 Relatório CSV gerado com sucesso!', 'success');
    } catch (e) {
        showAlert('Erro ao exportar CSV', 'error');
    }
}

async function handleImageUpload(fileInputId, urlInputId) {
    const fileInput = document.getElementById(fileInputId);
    const urlInput  = document.getElementById(urlInputId);
    if (!fileInput.files || fileInput.files.length === 0) return;

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    try {
        const token = localStorage.getItem('token');
        const payload = getTokenPayload(token);
        const tenantId = payload?.tenant_id;
        const response = await fetch(`${API_BASE}/upload`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                ...(tenantId ? { 'X-Tenant-ID': String(tenantId) } : {})
            },
            body: formData
        });
        const result = await response.json();
        if (response.ok && result.status === 'success') {
            urlInput.value = result.url;
            showAlert('Arquivo enviado com sucesso! Clique em Salvar para aplicar.', 'success');
            urlInput.dispatchEvent(new Event('input', { bubbles: true }));
        } else {
            showAlert('Erro: ' + (result.detail || 'Falha ao enviar arquivo'), 'error');
        }
    } catch (err) {
        showAlert('Erro de conexão ao enviar arquivo', 'error');
    }
}
