const API_BASE = '/api';
const AUTH_URL = '/login.html';

// Auth Check
function checkAuth() {
    const token = localStorage.getItem('token');
    if (!token) {
        window.location.href = AUTH_URL;
        return null;
    }
    return token;
}

// Authenticated Fetch Wrapper
async function authFetch(url, options = {}) {
    const token = checkAuth();
    if (!token) return; // Redirects inside checkAuth

    const headers = {
        ...options.headers,
        'Authorization': `Bearer ${token}`
    };

    const response = await fetch(url, { ...options, headers });

    if (response.status === 401) {
        console.warn('Sessão expirada ou inválida (401). Redirecionando para login...');
        localStorage.removeItem('token');
        window.location.href = AUTH_URL;
        return null;
    }

    return response;
}

// User Management
async function loadUser() {
    try {
        const response = await authFetch('/api/auth/me');
        if (!response) return;
        const user = await response.json();

        // Update sidebar info
        const nameDisplay = document.getElementById('userNameDisplay');
        const roleDisplay = document.getElementById('userRoleDisplay');
        const avatarDisplay = document.getElementById('userAvatar');

        if (nameDisplay) nameDisplay.textContent = user.name;
        if (roleDisplay) roleDisplay.textContent = user.role === 'admin' ? 'Administrador' : 'Colaborador';
        if (avatarDisplay) avatarDisplay.textContent = user.name.charAt(0).toUpperCase();

    } catch (error) {
        console.error('Erro ao carregar usuário:', error);
    }
}

function logout() {
    localStorage.removeItem('token');
    window.location.href = AUTH_URL;
}

let customersData = [];
let meetingsData = [];
let editingCustomerId = null;
let editingMeetingId = null;

// Navigation Logic (Sidebar)
document.addEventListener('DOMContentLoaded', () => {
    const navItems = document.querySelectorAll('.nav-item');
    const sections = document.querySelectorAll('.view-section');
    const pageTitle = document.getElementById('pageTitle');

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            // Remove active from all
            navItems.forEach(n => n.classList.remove('active'));
            sections.forEach(s => s.classList.remove('active'));

            // Add active to clicked
            item.classList.add('active');
            const targetId = item.dataset.target;
            const targetSection = document.getElementById(targetId);

            if (targetSection) {
                targetSection.classList.add('active');
                // Update Title
                pageTitle.textContent = item.textContent.trim();

                // Load specific data
                if (targetId === 'customers') loadCustomers();
                if (targetId === 'meetings') loadMeetings();
                if (targetId === 'tickets') loadTickets();
                if (targetId === 'conversations') loadConversations();
                if (targetId === 'analytics') loadAnalytics();
                if (targetId === 'settings') loadSettings();
                if (targetId === 'dashboard') loadStats();
            }
        });
    });

    // Initial Load
    loadUser();
    loadStats();
    loadCustomers(); // Pre-load
    // Refresh stats periodically
    setInterval(loadStats, 30000);
});

function showAlert(message, type = 'success') {
    const alert = document.createElement('div');
    alert.className = `alert ${type}`;
    alert.textContent = message;
    document.getElementById('alertContainer').appendChild(alert);
    setTimeout(() => alert.remove(), 5000);
}

async function loadStats() {
    try {
        const response = await authFetch(`${API_BASE}/stats?t=${Date.now()}`, { cache: 'no-store' });
        if (!response) return;
        const data = await response.json();

        // Update dashboard cards
        const ids = ['activeCustomers', 'openTickets', 'scheduledMeetings', 'todayConversations'];
        ids.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.textContent = data[id.replace(/[A-Z]/g, letter => `_${letter.toLowerCase()}`)] || 0;
        });

    } catch (error) {
        console.error('Erro ao carregar estatísticas:', error);
    }
}

// ... Copying existing Customer/Meeting logic ...

async function loadCustomers() {
    try {
        const response = await authFetch(`${API_BASE}/customers?t=${Date.now()}`, { cache: 'no-store' });
        if (!response) return;
        const customers = await response.json();
        customersData = customers;
        const tbody = document.getElementById('customersBody');

        if (customers.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: #9ca3af; padding: 1rem;">Nenhum cliente registrado</td></tr>';
            populateMeetingCustomers();
            return;
        }

        tbody.innerHTML = customers.map(c => {
            let statusBadge = '';
            switch (c.status) {
                case 'briefing': statusBadge = '<span class="badge pending">Briefing</span>'; break;
                case 'proposal': statusBadge = '<span class="badge" style="background:#8b5cf6">Proposta</span>'; break;
                case 'monthly': statusBadge = '<span class="badge completed">Mensal</span>'; break;
                case 'completed': statusBadge = '<span class="badge" style="background:#6b7280">Finalizado</span>'; break;
                default: statusBadge = '<span class="badge active">Em Processo</span>';
            }

            return `
            <tr>
                <td>#${c.id}</td>
                <td><strong>${c.name}</strong></td>
                <td>${c.company || '-'}</td>
                <td>${c.phone}</td>
                <td>${c.email || '-'}</td>
                <td>${statusBadge}</td>
                <td>
                    <button class="btn-secondary" style="padding: 5px 10px; font-size: 0.8rem;" onclick="editCustomer(${c.id})">Editar</button>
                </td>
            </tr>
        `}).join('');

        populateMeetingCustomers();
    } catch (error) {
        console.error('Erro ao carregar clientes:', error);
    }
}

async function loadTickets() {
    try {
        const response = await authFetch(`${API_BASE}/tickets?t=${Date.now()}`, { cache: 'no-store' });
        if (!response) return;
        const tickets = await response.json();
        const tbody = document.getElementById('ticketsBody');

        if (tickets.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #9ca3af; padding: 1rem;">Nenhum ticket aberto</td></tr>';
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
                <td>
                    <button class="btn-secondary" style="padding: 5px 10px; font-size: 0.8rem;" onclick="viewTicket(${t.id})">Ver</button>
                </td>
            </tr>
        `).join('');
    } catch (error) {
        console.error('Erro ao carregar tickets:', error);
    }
}

async function loadMeetings() {
    try {
        const response = await authFetch(`${API_BASE}/meetings?t=${Date.now()}`, { cache: 'no-store' });
        if (!response) return;
        const meetings = await response.json();
        meetingsData = meetings;
        const tbody = document.getElementById('meetingsBody');

        if (meetings.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: #9ca3af; padding: 1rem;">Nenhuma reunião agendada</td></tr>';
            return;
        }

        tbody.innerHTML = meetings.map(m => `
            <tr>
                <td>${m.customer_name}</td>
                <td>${m.type === 'briefing' ? '🎯 Briefing' : '💼 Proposta'}</td>
                <td>${new Date(m.date).toLocaleDateString('pt-BR')}</td>
                <td>${m.time}</td>
                <td><span class="badge completed">Agendada</span></td>
                <td>
                    <button class="btn-secondary" style="padding: 5px 10px; font-size: 0.8rem;" onclick="editMeeting(${m.id})">Editar</button>
                </td>
            </tr>
        `).join('');
    } catch (error) {
        console.error('Erro ao carregar reuniões:', error);
    }
}

// ... Existing Helpers ...
function populateMeetingCustomers() {
    const select = document.getElementById('meetingCustomer');
    if (customersData.length > 0) {
        select.innerHTML = '<option value="">Selecione um cliente...</option>' +
            customersData.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
    }
}

// ... Modal Functions (Customer & Meeting) ...
// Reuse existing modal logic (omitted for brevity in prompt but included in actual file)
// For this output, I will presume standard open/close/save functions are identical to before.
// I will just paste them to ensure functionality.

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
        console.error(error);
        showAlert('Erro ao excluir cliente', 'error');
    }
}

async function saveCustomer(e) {
    e.preventDefault();
    try {
        const method = editingCustomerId ? 'PUT' : 'POST';
        const url = editingCustomerId ? `${API_BASE}/customers/${editingCustomerId}` : `${API_BASE}/customers`;
        await authFetch(url, {
            method: method,
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
        console.error(error);
        showAlert('Erro ao salvar cliente', 'error');
    }
}

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

async function saveMeeting(e) {
    e.preventDefault();
    try {
        const method = editingMeetingId ? 'PUT' : 'POST';
        const url = editingMeetingId ? `${API_BASE}/meetings/${editingMeetingId}` : `${API_BASE}/meetings`;
        await authFetch(url, {
            method: method,
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
        console.error(error);
        showAlert('Erro ao salvar reunião', 'error');
    }
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
        console.error(error);
        showAlert('Erro ao excluir reunião', 'error');
    }
}

function viewTicket(id) {
    alert('Funcionalidade de ver ticket em breve.');
}

// ... Settings & Tests ...
async function testEvolutionAPI() {
    const status = document.getElementById('evolutionStatus');
    status.style.background = '#f59e0b';
    document.getElementById('evolutionStatusText').textContent = 'Testando...';
    try {
        await authFetch(`${API_BASE}/health/evolution`);
        status.style.background = '#10b981';
        document.getElementById('evolutionStatusText').textContent = 'Conectado';
        showAlert('Evolution API conectada com sucesso!', 'success');
    } catch {
        status.style.background = '#ef4444';
        document.getElementById('evolutionStatusText').textContent = 'Erro na conexão';
        showAlert('Erro ao conectar com Evolution API', 'error');
    }
}

async function testDatabase() {
    const status = document.getElementById('dbStatus');
    status.style.background = '#f59e0b';
    document.getElementById('dbStatusText').textContent = 'Testando...';
    try {
        await authFetch(`${API_BASE}/health/database`);
        status.style.background = '#10b981';
        document.getElementById('dbStatusText').textContent = 'Conectado';
        showAlert('Banco de dados conectado com sucesso!', 'success');
    } catch {
        status.style.background = '#ef4444';
        document.getElementById('dbStatusText').textContent = 'Erro na conexão';
        showAlert('Erro ao conectar com banco de dados', 'error');
    }
}

function copyNgrokUrl() {
    const url = document.getElementById('ngrokUrl').value;
    navigator.clipboard.writeText(url);
    showAlert('URL ngrok copiada!', 'success');
}

async function loadSettings() {
    try {
        const response = await authFetch(`${API_BASE}/config?t=${Date.now()}`, { cache: 'no-store' });
        if (!response) return;
        const configs = await response.json();

        const promptConfig = configs.find(c => c.key === 'system_prompt');
        if (promptConfig && document.getElementById('systemPrompt')) {
            document.getElementById('systemPrompt').value = promptConfig.value;
        }

        const openaiConfig = configs.find(c => c.key === 'openai_api_key');
        if (openaiConfig) {
            document.getElementById('openaiKey').value = openaiConfig.value;
        }
    } catch (error) {
        console.error('Error loading settings:', error);
    }
}

async function saveSettings() {
    const payload = {};
    const openAiKey = document.getElementById('openaiKey').value;
    if (openAiKey && openAiKey !== '********') {
        payload['openai_api_key'] = openAiKey;
    }
    const prompt = document.getElementById('systemPrompt')?.value;
    if (prompt) {
        payload['system_prompt'] = prompt;
    }

    try {
        await authFetch(`${API_BASE}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        showAlert('Configurações salvas com sucesso!', 'success');
    } catch (error) {
        showAlert('Erro ao salvar configurações', 'error');
    }
}

// --- NEW FEATURES: Conversations & Chat Test ---

async function loadConversations() {
    const container = document.getElementById('conversationsList');
    container.innerHTML = '<p style="text-align: center; color: #6b7280; padding: 2rem;">Carregando histórico...</p>';

    try {
        // Mock implementation for now, will implement backend route next
        const response = await authFetch(`${API_BASE}/conversations?t=${Date.now()}`);

        if (response && response.ok) {
            const conversations = await response.json();
            if (conversations.length === 0) {
                container.innerHTML = '<p style="text-align: center; color: #6b7280; padding: 2rem;">Nenhuma conversa encontrada.</p>';
                return;
            }
            // Render conversations list (simplified)
            container.innerHTML = conversations.map(c => `
                <div style="padding: 1rem; border-bottom: 1px solid #e5e7eb; cursor: pointer;" onclick="viewConversationDetail(${c.id})">
                    <div style="font-weight: bold;">${c.customer_name || c.phone}</div>
                    <div style="font-size: 0.8rem; color: #6b7280;">${new Date(c.last_message_at).toLocaleString()}</div>
                    <div style="margin-top: 0.5rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #4b5563;">
                        ${c.last_message_preview || '...'}
                    </div>
                </div>
            `).join('');
        } else {
            // Fallback if backend route not ready
            container.innerHTML = '<p style="text-align: center; color: #ef4444; padding: 2rem;">Erro ao carregar (API pendente)</p>';
        }
    } catch (error) {
        console.error('Error loading conversations:', error);
        container.innerHTML = '<p style="text-align: center; color: #ef4444; padding: 2rem;">Erro ao carregar conversas.</p>';
    }
}

async function sendTestMessage() {
    const input = document.getElementById('chatTestInput');
    const message = input.value.trim();
    if (!message) return;

    const messagesDiv = document.getElementById('chatTestMessages');

    // Add User Message
    const userDiv = document.createElement('div');
    userDiv.className = 'message user';
    userDiv.textContent = message;
    messagesDiv.appendChild(userDiv);

    input.value = '';
    messagesDiv.scrollTop = messagesDiv.scrollHeight;

    // Add Loading
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message agent';
    loadingDiv.textContent = 'Digitando...';
    messagesDiv.appendChild(loadingDiv);

    try {
        const response = await authFetch(`${API_BASE}/chat/test`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message })
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
        console.error(error);
    }

    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// --- Analytics ---
let channelsChart = null;
let funnelChart = null;

async function loadAnalytics() {
    try {
        const response = await authFetch(`${API_BASE}/analytics/dashboard`);
        if (!response) return;
        const data = await response.json();

        // 1. Update KPI Cards
        document.getElementById('stat-automation-rate').innerText = data.performance.automation_rate + '%';
        document.getElementById('stat-csat').innerText = data.performance.csat;
        document.getElementById('stat-leads').innerText = data.business.new_leads_30d;

        let totalTickets = 0;
        if (data.overview.tickets_today) {
            totalTickets = Object.values(data.overview.tickets_today).reduce((a, b) => a + b, 0);
        }
        document.getElementById('stat-tickets-today').innerText = totalTickets;

        // 2. Channels Chart
        const channelCtx = document.getElementById('channelsChart').getContext('2d');
        if (channelsChart) channelsChart.destroy();

        const channelLabels = Object.keys(data.overview.channels);
        const channelValues = Object.values(data.overview.channels);

        channelsChart = new Chart(channelCtx, {
            type: 'doughnut',
            data: {
                labels: channelLabels,
                datasets: [{
                    data: channelValues,
                    backgroundColor: ['#f56954', '#00a65a', '#f39c12', '#00c0ef', '#3c8dbc', '#d2d6de'],
                }]
            },
            options: { maintainAspectRatio: false, responsive: true }
        });

        // 3. Funnel Chart
        const funnelCtx = document.getElementById('funnelChart').getContext('2d');
        if (funnelChart) funnelChart.destroy();

        // Ensure strictly ordered pipeline for funnel
        const funnelOrder = ['em_processo', 'briefing', 'proposal', 'monthly', 'completed'];
        const funnelLabels = funnelOrder;
        const funnelValues = funnelOrder.map(status => data.business.funnel[status] || 0);

        funnelChart = new Chart(funnelCtx, {
            type: 'bar',
            data: {
                labels: funnelLabels.map(l => l.toUpperCase()),
                datasets: [{
                    label: 'Clientes por Fase',
                    data: funnelValues,
                    backgroundColor: '#3c8dbc'
                }]
            },
            options: {
                indexAxis: 'y',
                maintainAspectRatio: false,
                responsive: true
            }
        });

    } catch (error) {
        console.error("Error loading analytics:", error);
    }
}
