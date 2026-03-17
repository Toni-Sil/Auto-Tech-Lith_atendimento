/**
 * api.js — Centralized API client
 * All fetch calls go through here for consistent error handling,
 * auth headers and token refresh.
 */

(function () {
  window.ATL = window.ATL || {};

  const BASE = '/api/v1';

  function getToken() {
    return localStorage.getItem('access_token');
  }

  function setToken(token) {
    localStorage.setItem('access_token', token);
  }

  function clearSession() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    window.location.href = '/login';
  }

  async function request(method, path, body = null, options = {}) {
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const config = {
      method,
      headers,
      ...(body ? { body: JSON.stringify(body) } : {}),
    };

    let res = await fetch(`${BASE}${path}`, config);

    // Auto-refresh on 401
    if (res.status === 401 && !options._retry) {
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        const refreshRes = await fetch(`${BASE}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (refreshRes.ok) {
          const data = await refreshRes.json();
          setToken(data.access_token);
          return request(method, path, body, { ...options, _retry: true });
        } else {
          clearSession();
          return;
        }
      } else {
        clearSession();
        return;
      }
    }

    if (!res.ok) {
      let errMsg = `HTTP ${res.status}`;
      try {
        const errData = await res.json();
        errMsg = errData.detail || errData.message || errMsg;
      } catch (_) {}
      throw new Error(errMsg);
    }

    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      return res.json();
    }
    return res.text();
  }

  window.ATL.api = {
    get:    (path, opts)         => request('GET',    path, null, opts),
    post:   (path, body, opts)   => request('POST',   path, body, opts),
    put:    (path, body, opts)   => request('PUT',    path, body, opts),
    patch:  (path, body, opts)   => request('PATCH',  path, body, opts),
    delete: (path, opts)         => request('DELETE', path, null, opts),
    setToken,
    getToken,
    clearSession,
  };
})();
