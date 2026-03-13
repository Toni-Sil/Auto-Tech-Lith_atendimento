/**
 * system_config.js — Master Admin System Configuration Panel
 * Handles GET/PUT /api/v1/master/system-config and SMTP test.
 */

const API_SYSCONFIG = '/api/v1/master/system-config';

// ── Load ──────────────────────────────────────────────────────────────────
async function loadSystemConfig() {
  const token = localStorage.getItem('token');
  try {
    const res = await fetch(API_SYSCONFIG, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!res.ok) throw new Error(await res.text());
    const d = await res.json();

    // General
    _val('scProjectName', d.project_name);
    _val('scEnv', d.env);
    _checked('scDebug', d.app_debug);
    _val('scPublicUrl', d.public_url || '');
    _val('scVerifyToken', d.verify_token || '');

    // AI
    _val('scOpenAIModel', d.openai_model);
    _val('scOpenAIKey', '');
    document.getElementById('scOpenAIKeyMask').textContent = d.openai_api_key_masked;

    // Evolution
    _val('scEvoUrl', d.evolution_api_url);
    _val('scEvoKey', '');
    document.getElementById('scEvoKeyMask').textContent = d.evolution_api_key_masked;

    // Tokens
    _val('scAccessExp', d.access_token_expire_minutes);
    _val('scRefreshExp', d.refresh_token_expire_minutes);
    _updateSliderLabel('scAccessExp', 'scAccessExpLabel', ' min');
    _updateSliderLabel('scRefreshExp', 'scRefreshExpLabel', ' min');

    // SMTP
    _val('scSmtpServer', d.smtp_server || '');
    _val('scSmtpPort', d.smtp_port);
    _val('scSmtpUser', d.smtp_user || '');
    _val('scSmtpPass', '');
    document.getElementById('scSmtpPassMask').textContent = d.smtp_password_masked;

    // CORS
    _val('scCorsOrigins', (d.backend_cors_origins || []).join('\n'));

    // Telegram
    _val('scTelegramToken', '');
    document.getElementById('scTelegramTokenMask').textContent = d.telegram_bot_token_masked;
    _val('scTelegramChat', d.telegram_chat_id || '');

    showAlert('Configurações carregadas.', 'success');
  } catch (e) {
    showAlert('Erro ao carregar configurações: ' + e.message, 'error');
  }
}

// ── Save ──────────────────────────────────────────────────────────────────
async function saveSystemConfig() {
  const token = localStorage.getItem('token');

  const corsRaw = document.getElementById('scCorsOrigins').value;
  const corsOrigins = corsRaw
    .split('\n')
    .map(s => s.trim())
    .filter(Boolean);

  const body = {};
  _maybeSet(body, 'project_name', 'scProjectName');
  _maybeSet(body, 'env', 'scEnv');
  body.app_debug = document.getElementById('scDebug').checked;
  _maybeSet(body, 'public_url', 'scPublicUrl');
  _maybeSet(body, 'verify_token', 'scVerifyToken');
  _maybeSet(body, 'openai_model', 'scOpenAIModel');
  _maybeSet(body, 'openai_api_key', 'scOpenAIKey'); // only if filled
  _maybeSet(body, 'evolution_api_url', 'scEvoUrl');
  _maybeSet(body, 'evolution_api_key', 'scEvoKey');
  body.access_token_expire_minutes = parseInt(document.getElementById('scAccessExp').value);
  body.refresh_token_expire_minutes = parseInt(document.getElementById('scRefreshExp').value);
  _maybeSet(body, 'smtp_server', 'scSmtpServer');
  body.smtp_port = parseInt(document.getElementById('scSmtpPort').value);
  _maybeSet(body, 'smtp_user', 'scSmtpUser');
  _maybeSet(body, 'smtp_password', 'scSmtpPass');
  if (corsOrigins.length) body.backend_cors_origins = corsOrigins;
  _maybeSet(body, 'telegram_bot_token', 'scTelegramToken');
  _maybeSet(body, 'telegram_chat_id', 'scTelegramChat');

  try {
    const res = await fetch(API_SYSCONFIG, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
    showAlert(`✅ ${data.message}`, 'success');
    loadSystemConfig(); // reload masks
  } catch (e) {
    showAlert('Erro ao salvar: ' + e.message, 'error');
  }
}

// ── SMTP Test ─────────────────────────────────────────────────────────────
async function testSmtp() {
  const token = localStorage.getItem('token');
  const to = document.getElementById('scSmtpTestEmail').value.trim();
  if (!to) { showAlert('Informe um e-mail de destino para o teste.', 'warning'); return; }

  try {
    const res = await fetch(`${API_SYSCONFIG}/test-smtp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ to_email: to })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
    showAlert('📧 ' + data.message, 'success');
  } catch (e) {
    showAlert('Falha no teste SMTP: ' + e.message, 'error');
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────
function _val(id, v) {
  const el = document.getElementById(id);
  if (el) el.value = v ?? '';
}
function _checked(id, v) {
  const el = document.getElementById(id);
  if (el) el.checked = !!v;
}
function _maybeSet(obj, key, id) {
  const el = document.getElementById(id);
  if (el && el.value.trim()) obj[key] = el.value.trim();
}
function _updateSliderLabel(sliderId, labelId, suffix) {
  const slider = document.getElementById(sliderId);
  const label = document.getElementById(labelId);
  if (slider && label) {
    label.textContent = slider.value + suffix;
    slider.addEventListener('input', () => { label.textContent = slider.value + suffix; });
  }
}

// Auto-load when tab is shown
document.addEventListener('DOMContentLoaded', () => {
  // Switch tab hook (master.js calls switchView)
  const observer = new MutationObserver(() => {
    const sec = document.getElementById('sys-config');
    if (sec && sec.classList.contains('active')) loadSystemConfig();
  });
  const sc = document.getElementById('sys-config');
  if (sc) observer.observe(sc, { attributes: true, attributeFilter: ['class'] });
});
