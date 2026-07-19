const API_URL = '/api/creator';
let currentAppId = null;
let currentApps = [];

function copyText(text) {
    navigator.clipboard.writeText(text);
    showToast('Copied to clipboard!', 'success');
}

// Premium Toast Notification System
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    let icon = 'fa-info-circle';
    if (type === 'success') icon = 'fa-check-circle';
    if (type === 'error') icon = 'fa-exclamation-circle';

    toast.innerHTML = `<i class="fas ${icon}"></i> <span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

async function handleGoogleLogin(response) {
    try {
        const res = await fetch(`${API_URL}/google-login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: response.credential })
        });
        const data = await res.json();
        if (res.ok) {
            localStorage.setItem('token', data.token);
            localStorage.setItem('email', data.email);
            showToast('Google Login successful!', 'success');
            showDashboard();
        } else {
            showToast(data.detail || 'Google Login failed', 'error');
        }
    } catch (e) {
        showToast('Error communicating with server during Google login', 'error');
    }
}

function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('email');
    localStorage.removeItem('user_role');
    localStorage.removeItem('reseller_perms');
    document.getElementById('auth-container').style.display = 'block';
    document.getElementById('dashboard-container').style.display = 'none';
    showToast('Logged out successfully', 'info');
}

function openLogoutModal() {
    const modal = document.getElementById('logout-modal');
    const input = document.getElementById('logout-confirm-input');
    if (modal && input) {
        modal.style.display = 'flex';
        input.value = '';
        input.focus();

        input.onkeydown = function (e) {
            if (e.key === 'Enter') {
                submitLogout();
            }
        };
    }
}

function closeLogoutModal() {
    const modal = document.getElementById('logout-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

function submitLogout() {
    const input = document.getElementById('logout-confirm-input');
    if (input) {
        const text = input.value.trim().toLowerCase();
        if (text === 'logout') {
            closeLogoutModal();
            logout();
        } else {
            showToast('Invalid confirmation text. Type "logout" to confirm.', 'error');
            input.focus();
            input.select();
        }
    }
}

async function showDashboard() {
    document.getElementById('auth-container').style.display = 'none';
    document.getElementById('dashboard-container').style.display = 'flex';

    const role = localStorage.getItem('user_role') || 'creator';
    const token = localStorage.getItem('token');

    // Fetch and populate profile details
    if (token) {
        try {
            const profileRes = await fetch('/api/creator/profile', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (profileRes.ok) {
                const profileData = await profileRes.json();
                const emailSpan = document.getElementById('profile-email');
                if (emailSpan) emailSpan.innerText = profileData.email || 'Unknown';

                const nameInput = document.getElementById('profile-full-name');
                if (nameInput) nameInput.value = profileData.full_name || '';
            }
        } catch (e) {
            console.error('Failed to load profile details', e);
        }
    }

    loadSystemDefaults();

    const emailLabel = document.getElementById('profile-email-label');
    const resellerBadge = document.getElementById('profile-reseller-badge');
    const googleBadge = document.getElementById('profile-google-badge');
    const updateForm = document.getElementById('creator-update-details-form');

    if (role === 'reseller') {
        const navResellers = document.getElementById('nav-resellers');
        if (navResellers) navResellers.style.display = 'none';

        const createAppContainer = document.querySelector('.create-app-card');
        if (createAppContainer) createAppContainer.style.display = 'none';

        // Setup Reseller specific labels and badges
        if (emailLabel) emailLabel.innerText = 'Reseller Account:';
        if (resellerBadge) resellerBadge.style.display = 'block';
        if (googleBadge) googleBadge.style.display = 'none';
        if (updateForm) updateForm.style.display = 'none';

        // Hide Settings sub-tabs not accessible to resellers
        const defaultsTabBtn = document.getElementById('btn-settings-defaults');
        if (defaultsTabBtn) defaultsTabBtn.style.display = 'none';

        // Default Settings view for resellers
        switchSettingsSubTab('settings-profile');
    } else {
        const navResellers = document.getElementById('nav-resellers');
        if (navResellers) navResellers.style.display = 'block';

        const createAppContainer = document.querySelector('.create-app-card');
        if (createAppContainer) createAppContainer.style.display = 'block';

        // Setup Creator labels and badges
        if (emailLabel) emailLabel.innerText = 'Email Address:';
        if (resellerBadge) resellerBadge.style.display = 'none';
        if (googleBadge) googleBadge.style.display = 'block';
        if (updateForm) updateForm.style.display = 'block';

        // Show Settings sub-tabs for creators
        const defaultsTabBtn = document.getElementById('btn-settings-defaults');
        if (defaultsTabBtn) defaultsTabBtn.style.display = 'block';
    }

    loadApps();
}

function showTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
    const targetTab = document.getElementById(`${tabId}-tab`);
    if (targetTab) targetTab.style.display = 'block';

    // Update active class in sidebar links
    document.querySelectorAll('.sidebar-menu .menu-link').forEach(link => {
        link.classList.remove('active');
        if (link.getAttribute('onclick') && link.getAttribute('onclick').includes(`showTab('${tabId}')`)) {
            link.classList.add('active');
        }
    });

    if (tabId === 'resellers') {
        loadResellers();
        loadResellerAppCheckboxes();
    }
}

async function loadApps() {
    const token = localStorage.getItem('token');
    if (!token) return logout();

    // For google mock, just show empty
    if (token === 'google_mock_token') {
        document.getElementById('app-list').innerHTML = '<p style="color:var(--text-muted);">No apps (Google mock)</p>';
        return;
    }

    try {
        const res = await fetch(`${API_URL}/apps`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) throw new Error();
        const apps = await res.json();
        currentApps = apps;

        const list = document.getElementById('app-list');
        const selector = document.getElementById('app-selector');

        list.innerHTML = '';
        if (selector) selector.innerHTML = '<option value="">-- Select an App --</option>';

        // Update Dashboard Stats
        document.getElementById('stat-apps').innerText = apps.length;

        let totalUsers = 0;
        let totalLicenses = 0;

        // Fetch counts for stats (Async all apps)
        await Promise.all(apps.map(async app => {
            try {
                const uRes = await fetch(`${API_URL}/apps/${app.id}/users`, { headers: { 'Authorization': `Bearer ${token}` } });
                if (uRes.ok) { const u = await uRes.json(); totalUsers += u.length; }

                const lRes = await fetch(`${API_URL}/apps/${app.id}/licenses`, { headers: { 'Authorization': `Bearer ${token}` } });
                if (lRes.ok) { const l = await lRes.json(); totalLicenses += l.length; }
            } catch (e) { }
        }));

        document.getElementById('stat-users').innerText = totalUsers;
        document.getElementById('stat-licenses').innerText = totalLicenses;

        const isReseller = localStorage.getItem('user_role') === 'reseller';
        apps.forEach(app => {
            // App Tab Card
            const div = document.createElement('div');
            div.className = 'app-card';

            const deleteBtnHtml = isReseller ? '' : `<button onclick="deleteApp(event, ${app.id})" style="width:auto; padding:8px 12px; height:auto; background:rgba(239, 68, 68, 0.15); color:#ef4444; border:1px solid rgba(239,68,68,0.3); border-radius:8px; box-shadow:none;"><i class="fas fa-trash"></i></button>`;
            const copyOwnerHtml = app.owner_id === '********' ? '' : `<button class="copy-field-btn" onclick="copyText('${app.owner_id}')" title="Copy Owner ID"><i class="far fa-copy"></i></button>`;
            const copySecretHtml = app.secret === '********' ? '' : `<button class="copy-field-btn" onclick="copyText('${app.secret}')" title="Copy Secret"><i class="far fa-copy"></i></button>`;

            div.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h3 style="margin:0; display:flex; align-items:center; gap:8px;"><i class="fas fa-cube" style="color:var(--primary);"></i>${app.app_name}</h3>
                    ${deleteBtnHtml}
                </div>
                <div style="margin-top:20px; background:rgba(0,0,0,0.25); padding:15px; border-radius:12px; border: 1px solid rgba(255,255,255,0.03);">
                    <p style="margin:5px 0; font-family:monospace; display:flex; justify-content:space-between; align-items:center; word-break:break-all;">
                        <span><strong>Owner ID:</strong> <span style="color:white;">${app.owner_id}</span></span>
                        ${copyOwnerHtml}
                    </p>
                    <p style="margin:8px 0 5px 0; font-family:monospace; display:flex; justify-content:space-between; align-items:center; word-break:break-all;">
                        <span><strong>Secret:</strong> <span style="color:white;">${app.secret}</span></span>
                        ${copySecretHtml}
                    </p>
                </div>
            `;
            list.appendChild(div);

            // Workspace Dropdown Option
            if (selector) {
                const opt = document.createElement('option');
                opt.value = app.id;
                opt.text = app.app_name;
                selector.appendChild(opt);
            }
        });

        // Quick setup call removed.
    } catch (e) {
        logout();
    }
}

async function createApp() {
    const app_name = document.getElementById('new-app-name').value.trim();
    if (!app_name) return showToast('App name cannot be empty', 'error');

    const token = localStorage.getItem('token');
    try {
        const res = await fetch(`${API_URL}/apps/create`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ app_name })
        });
        if (res.ok) {
            const data = await res.json();
            document.getElementById('new-app-name').value = '';
            showToast('Application created successfully!', 'success');

            // Auto initialize with default settings
            const defaultStatus = localStorage.getItem('default_app_status') || 'active';
            const defaultVersion = localStorage.getItem('default_app_version') || '1.0';
            const defaultMotd = localStorage.getItem('default_app_motd') || 'Welcome to our application!';

            try {
                await fetch(`${API_URL}/apps/${data.app.id}/settings`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify({
                        status: defaultStatus,
                        version: defaultVersion,
                        dev_message: defaultMotd,
                        webhook_url: ''
                    })
                });
            } catch (settingsErr) {
                console.error('Failed to initialize defaults', settingsErr);
            }

            loadApps();
        } else {
            const data = await res.json();
            showToast(data.detail, 'error');
        }
    } catch (e) {
        showToast('Error creating app', 'error');
    }
}

async function deleteApp(event, appId) {
    event.stopPropagation();
    if (!confirm("Are you sure you want to delete this application? All users and licenses will be permanently lost.")) return;

    const token = localStorage.getItem('token');
    try {
        const res = await fetch(`${API_URL}/apps/${appId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (res.ok) {
            showToast('Application deleted.', 'info');
            if (currentAppId === appId) {
                const wsContent = document.getElementById('app-workspace-content');
                if (wsContent) wsContent.style.display = 'none';
                currentAppId = null;
            }
            loadApps();
        } else {
            const data = await res.json();
            showToast(data.detail, 'error');
        }
    } catch (e) {
        showToast('Error deleting app', 'error');
    }
}

async function switchWorkspaceApp(appId) {
    if (!appId) {
        document.getElementById('app-workspace-content').style.display = 'none';
        currentAppId = null;
        return;
    }

    currentAppId = appId;
    const app = currentApps.find(a => a.id == appId);
    if (app) {
        document.getElementById('settings-status').value = app.status || 'active';
        document.getElementById('settings-webhook').value = app.webhook_url || '';
        document.getElementById('settings-version').value = app.version || '1.0';
        document.getElementById('settings-dev-msg').value = app.dev_message || '';
    }

    document.getElementById('app-workspace-content').style.display = 'block';

    const isReseller = localStorage.getItem('user_role') === 'reseller';
    if (isReseller) {
        const perms = JSON.parse(localStorage.getItem('reseller_perms') || '{}');
        document.getElementById('btn-tab-users').style.display = perms.can_manage_users ? 'block' : 'none';
        document.getElementById('btn-tab-licenses').style.display = perms.can_manage_licenses ? 'block' : 'none';
        document.getElementById('btn-tab-logs').style.display = perms.can_view_logs ? 'block' : 'none';
        document.getElementById('btn-tab-settings').style.display = 'none';

        let targetTab = null;
        if (perms.can_manage_users) targetTab = 'users';
        else if (perms.can_manage_licenses) targetTab = 'licenses';
        else if (perms.can_view_logs) targetTab = 'logs';

        if (targetTab) {
            showAppTab(targetTab);
        } else {
            document.querySelectorAll('.app-sub-tab').forEach(el => el.style.display = 'none');
        }
    } else {
        document.getElementById('btn-tab-users').style.display = 'block';
        document.getElementById('btn-tab-licenses').style.display = 'block';
        document.getElementById('btn-tab-logs').style.display = 'block';
        document.getElementById('btn-tab-settings').style.display = 'block';
        showAppTab('users');
    }

    loadAppWorkspaceData();
}

function loadAppWorkspaceData() {
    loadUsers();
    loadLicenses();
    loadLogs();
}

function showAppTab(tab) {
    document.querySelectorAll('.app-sub-tab').forEach(el => {
        el.style.display = 'none';
        el.classList.remove('slide-in');
    });
    const selectedTab = document.getElementById(`app-${tab}-tab`);
    if (selectedTab) {
        selectedTab.style.display = 'block';
        // Trigger animation
        setTimeout(() => { selectedTab.classList.add('slide-in'); }, 10);
    }

    document.querySelectorAll('.sub-tabs-container .sub-tab-btn').forEach(btn => btn.classList.remove('active'));
    const btn = document.getElementById(`btn-tab-${tab}`);
    if (btn) btn.classList.add('active');
}

async function loadUsers() {
    const token = localStorage.getItem('token');
    const isReseller = localStorage.getItem('user_role') === 'reseller';
    const perms = isReseller ? JSON.parse(localStorage.getItem('reseller_perms') || '{}') : null;
    const canReset = !isReseller || (perms && perms.can_reset_hwid);

    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/users`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const users = await res.json();
        const list = document.getElementById('user-list');
        let html = '<table class="pro-table" id="user-table"><tr><th>User</th><th>Last IP</th><th>HWID</th><th>Status/Lock</th><th>Expires At</th><th>Actions</th></tr>';
        users.forEach(u => {
            let statusBadge = u.status === 'banned' ? '<span style="color:var(--danger);font-size:12px;border:1px solid var(--danger);padding:2px 4px;border-radius:4px;">BANNED</span>' : '';
            const resetBtnHtml = canReset ? `<button class="action-btn icon-btn" onclick="resetUserHWID(${u.id})" title="Reset HWID"><i class="fas fa-undo"></i></button>` : '';
            html += `<tr>
                <td>${u.username} <button onclick="copyToClipboard('${u.username}')" style="background:transparent;border:none;color:var(--text-muted);cursor:pointer;padding:0;width:auto;margin:0 5px;box-shadow:none;"><i class="fas fa-copy"></i></button></td>
                <td><span style="color:var(--primary); font-family:monospace;">${u.last_ip || 'Never'}</span></td>
                <td><span style="font-family:monospace; color:var(--text-muted);">${u.hwid ? u.hwid.substring(0, 8) + '...' : 'Not Set'}</span></td>
                <td>${statusBadge} ${u.hwid_lock ? '<span style="color:var(--success);"><i class="fas fa-lock"></i></span>' : '<span style="color:var(--danger);"><i class="fas fa-lock-open"></i></span>'}</td>
                <td>${u.expires_at}</td>
                <td>
                    <button class="action-btn icon-btn" onclick="toggleBanUser(${u.id})" title="Ban/Unban"><i class="fas fa-gavel"></i></button>
                    ${resetBtnHtml}
                    <button class="action-btn icon-btn danger-btn" onclick="deleteUser(${u.id})" title="Delete User"><i class="fas fa-trash"></i></button>
                </td>
            </tr>`;
        });
        html += '</table>';
        list.innerHTML = html;
        updateGrowthChart(users.length, null); // Basic chart update
    } catch (e) { }
}

async function loadLicenses() {
    const token = localStorage.getItem('token');
    const isReseller = localStorage.getItem('user_role') === 'reseller';
    const perms = isReseller ? JSON.parse(localStorage.getItem('reseller_perms') || '{}') : null;
    const canReset = !isReseller || (perms && perms.can_reset_hwid);

    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/licenses`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const licenses = await res.json();
        const list = document.getElementById('license-list');
        let html = '<table class="pro-table" id="license-table"><tr><th>Key</th><th>Last IP</th><th>Status/Lock</th><th>Duration</th><th>Expires</th><th>Actions</th></tr>';
        licenses.forEach(l => {
            let statusBadge = l.status === 'banned' ? '<span style="color:var(--danger);font-size:12px;border:1px solid var(--danger);padding:2px 4px;border-radius:4px;">BANNED</span>' : '';
            const resetBtnHtml = canReset ? `<button class="action-btn icon-btn" onclick="resetLicenseHWID(${l.id})" title="Reset HWID"><i class="fas fa-undo"></i></button>` : '';
            html += `<tr>
                <td><span style="font-family:monospace; color:var(--primary);">${l.license_key}</span> <button onclick="copyToClipboard('${l.license_key}')" style="background:transparent;border:none;color:var(--text-muted);cursor:pointer;padding:0;width:auto;margin:0 5px;box-shadow:none;"><i class="fas fa-copy"></i></button></td>
                <td><span style="font-family:monospace;">${l.last_ip || 'Never'}</span></td>
                <td>${statusBadge} ${l.hwid_lock ? '<span style="color:var(--success);"><i class="fas fa-lock"></i></span>' : '<span style="color:var(--danger);"><i class="fas fa-lock-open"></i></span>'}</td>
                <td>${l.duration_days} Days</td>
                <td>${l.expires_at}</td>
                <td>
                    <button class="action-btn icon-btn" onclick="toggleBanLicense(${l.id})" title="Ban/Unban"><i class="fas fa-gavel"></i></button>
                    ${resetBtnHtml}
                    <button class="action-btn icon-btn danger-btn" onclick="deleteLicense(${l.id})" title="Delete License"><i class="fas fa-trash"></i></button>
                </td>
            </tr>`;
        });
        html += '</table>';
        list.innerHTML = html;
        updateGrowthChart(null, licenses.length);
    } catch (e) { }
}

async function addUser() {
    const username = document.getElementById('new-user-name').value;
    const password = document.getElementById('new-user-pass').value;
    const expiry = document.getElementById('new-user-expiry').value;
    const hwidLock = document.getElementById('new-user-hwid').checked;
    const token = localStorage.getItem('token');

    if (!username || !password) return showToast('Username and Password required', 'error');

    const payload = { username, password, hwid_lock_enabled: hwidLock };
    if (expiry) {
        payload.expires_at = new Date(expiry).toISOString();
    }

    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/users`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            showToast('User created successfully!', 'success');
            document.getElementById('new-user-name').value = '';
            document.getElementById('new-user-pass').value = '';
            loadUsers();
            loadApps(); // Update dashboard stats
        } else {
            const data = await res.json();
            showToast(data.detail, 'error');
        }
    } catch (e) {
        showToast('Error adding user', 'error');
    }
}

async function generateLicenses() {
    const amount = parseInt(document.getElementById('new-lic-amount').value);
    const duration = parseInt(document.getElementById('new-lic-days').value);
    const hwidLock = document.getElementById('new-lic-hwid').checked;
    const token = localStorage.getItem('token');

    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/licenses`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                amount: amount,
                duration_days: duration,
                hwid_lock_enabled: hwidLock
            })
        });
        if (res.ok) {
            showToast(`${amount} License(s) generated successfully!`, 'success');
            loadLicenses();
            loadApps(); // Update dashboard stats
        } else {
            const data = await res.json();
            showToast(data.detail, 'error');
        }
    } catch (e) {
        showToast('Error generating licenses', 'error');
    }
}

async function resetUserHWID(id) {
    if (!confirm('Reset HWID for this user?')) return;
    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/users/${id}/reset-hwid`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        if (res.ok) { showToast('HWID Reset Successful', 'success'); loadUsers(); }
        else showToast('Error resetting HWID', 'error');
    } catch (e) { }
}

async function deleteUser(id) {
    if (!confirm('Delete this user?')) return;
    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/users/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        if (res.ok) { showToast('User Deleted', 'info'); loadUsers(); }
        else showToast('Error deleting user', 'error');
    } catch (e) { }
}

async function resetLicenseHWID(id) {
    if (!confirm('Reset HWID for this license?')) return;
    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/licenses/${id}/reset-hwid`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        if (res.ok) { showToast('HWID Reset Successful', 'success'); loadLicenses(); }
        else showToast('Error resetting HWID', 'error');
    } catch (e) { }
}

async function deleteLicense(id) {
    if (!confirm('Delete this license?')) return;
    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/licenses/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        if (res.ok) { showToast('License Deleted', 'info'); loadLicenses(); }
        else showToast('Error deleting license', 'error');
    } catch (e) { }
}

async function saveAppSettings() {
    const status = document.getElementById('settings-status').value;
    const webhook = document.getElementById('settings-webhook').value;
    const version = document.getElementById('settings-version').value;
    const devMsg = document.getElementById('settings-dev-msg').value;

    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/settings`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify({ status: status, webhook_url: webhook, version: version, dev_message: devMsg })
        });
        if (res.ok) {
            showToast('Settings saved successfully', 'success');
            loadApps(); // Reload apps to get updated global state
        } else {
            showToast('Error saving settings', 'error');
        }
    } catch (e) { }
}

async function toggleBanUser(id) {
    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/users/${id}/toggle-ban`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        if (res.ok) { showToast('User ban status toggled', 'success'); loadAppWorkspaceData(); }
        else showToast('Error toggling ban', 'error');
    } catch (e) { }
}

async function toggleBanLicense(id) {
    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/licenses/${id}/toggle-ban`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        if (res.ok) { showToast('License ban status toggled', 'success'); loadAppWorkspaceData(); }
        else showToast('Error toggling ban', 'error');
    } catch (e) { }
}

async function loadLogs() {
    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/logs`, {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        const logs = await res.json();
        const list = document.getElementById('log-list');
        if (logs.length === 0) {
            list.innerHTML = '<span style="color: var(--text-muted);">No activity logged yet...</span>';
            return;
        }
        let html = '';
        logs.forEach(l => {
            let color = 'var(--text-muted)';
            if (l.action.includes('SUCCESS') || l.action.includes('CREATED') || l.action.includes('GENERATED')) color = 'var(--success)';
            if (l.action.includes('FAILED') || l.action.includes('BAN') || l.action.includes('DELETE')) color = 'var(--danger)';

            html += `<div style="margin-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 5px;">
                <span style="color:#64748b;">[${new Date(l.created_at).toLocaleTimeString()}]</span> 
                <span style="color:${color}; font-weight:bold;">[${l.action}]</span> 
                <span style="color:#e2e8f0;">${l.description}</span>
            </div>`;
        });
        list.innerHTML = html;
    } catch (e) { }
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('Copied to clipboard!', 'info');
    });
}

function filterTable(tableContainerId, query) {
    const filter = query.toUpperCase();
    const table = document.getElementById(tableContainerId).querySelector('table');
    if (!table) return;
    const tr = table.getElementsByTagName("tr");
    for (let i = 1; i < tr.length; i++) {
        const textContent = tr[i].textContent || tr[i].innerText;
        if (textContent.toUpperCase().indexOf(filter) > -1) {
            tr[i].style.display = "";
        } else {
            tr[i].style.display = "none";
        }
    }
}

function exportCSV(type) {
    const tableContainerId = type === 'users' ? 'user-list' : 'license-list';
    const table = document.getElementById(tableContainerId).querySelector('table');
    if (!table) { showToast('No data to export', 'error'); return; }

    let csv = [];
    const rows = table.querySelectorAll("tr");

    for (let i = 0; i < rows.length; i++) {
        let row = [], cols = rows[i].querySelectorAll("td, th");
        // Skip Actions column
        for (let j = 0; j < cols.length - 1; j++) {
            row.push('"' + cols[j].innerText.replace(/"/g, '""') + '"');
        }
        csv.push(row.join(","));
    }

    const csvString = csv.join("\n");
    const a = document.createElement('a');
    a.href = 'data:attachment/csv,' + encodeURIComponent(csvString);
    a.target = '_blank';
    a.download = `LegitAuth_${type}_export.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

function setTheme(color) {
    document.documentElement.style.setProperty('--primary', color);
    showToast('Theme updated!', 'success');
}

let dashboardChart = null;
function updateGrowthChart(usersCount, licensesCount) {
    const ctx = document.getElementById('growthChart');
    if (!ctx) return;

    // We only update if we have both values, or we just randomly plot if incomplete for demo purposes
    if (dashboardChart) {
        if (usersCount !== null) dashboardChart.data.datasets[0].data = [Math.max(usersCount - 5, 0), usersCount - 2, usersCount];
        if (licensesCount !== null) dashboardChart.data.datasets[1].data = [Math.max(licensesCount - 10, 0), licensesCount - 5, licensesCount];
        dashboardChart.update();
        return;
    }

    dashboardChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['2 Days Ago', 'Yesterday', 'Today'],
            datasets: [{
                label: 'Users',
                data: [0, 0, usersCount || 0],
                borderColor: '#8b5cf6',
                backgroundColor: 'rgba(139, 92, 246, 0.2)',
                tension: 0.4,
                fill: true
            }, {
                label: 'Licenses',
                data: [0, 0, licensesCount || 0],
                borderColor: '#38bdf8',
                backgroundColor: 'rgba(56, 189, 248, 0.2)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { labels: { color: 'white' } } },
            scales: {
                y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8' } },
                x: { grid: { display: false }, ticks: { color: '#94a3b8' } }
            }
        }
    });
}

// Discord integration logic removed.   }


// --- Reseller System Frontend Logic ---

function switchLoginType(type) {
    const creatorBtn = document.getElementById('toggle-creator-btn');
    const resellerBtn = document.getElementById('toggle-reseller-btn');
    const creatorContainer = document.getElementById('creator-login-container');
    const resellerContainer = document.getElementById('reseller-login-container');

    if (type === 'creator') {
        creatorBtn.style.background = 'var(--primary)';
        creatorBtn.style.color = 'white';
        resellerBtn.style.background = 'transparent';
        resellerBtn.style.color = 'var(--text-muted)';
        creatorContainer.style.display = 'flex';
        resellerContainer.style.display = 'none';
    } else {
        resellerBtn.style.background = 'var(--primary)';
        resellerBtn.style.color = 'white';
        creatorBtn.style.background = 'transparent';
        creatorBtn.style.color = 'var(--text-muted)';
        creatorContainer.style.display = 'none';
        resellerContainer.style.display = 'flex';
    }
}

async function handleResellerLogin() {
    const usernameInput = document.getElementById('reseller-username');
    const passwordInput = document.getElementById('reseller-password');
    const username = usernameInput.value.trim();
    const password = passwordInput.value;

    if (!username || !password) {
        return showToast('Username and password are required', 'error');
    }

    try {
        const res = await fetch('/api/reseller/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (res.ok) {
            localStorage.setItem('token', data.access_token);
            localStorage.setItem('user_role', 'reseller');
            localStorage.setItem('reseller_perms', JSON.stringify(data.permissions));
            localStorage.setItem('email', username);
            showToast('Logged in as Reseller', 'success');

            usernameInput.value = '';
            passwordInput.value = '';

            showDashboard();
        } else {
            showToast(data.detail || 'Reseller Login failed', 'error');
        }
    } catch (e) {
        showToast('Error communicating with server during Reseller login', 'error');
    }
}

async function loadResellers() {
    const token = localStorage.getItem('token');
    try {
        const res = await fetch('/api/creator/resellers', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) throw new Error();
        const resellers = await res.json();

        const container = document.getElementById('resellers-list-container');
        if (!container) return;

        if (resellers.length === 0) {
            container.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 20px;">No reseller profiles created yet.</p>';
            return;
        }

        let html = `
            <table class="pro-table">
                <thead>
                    <tr>
                        <th>Username</th>
                        <th>Allowed Apps</th>
                        <th>Permissions</th>
                        <th>Created At</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
        `;

        resellers.forEach(r => {
            const appNames = r.allowed_apps.map(appId => {
                const app = currentApps.find(a => a.id === appId);
                return app ? app.app_name : `App ID ${appId}`;
            }).join(', ') || 'None';

            const perms = [];
            if (r.is_admin) perms.push('👑 Admin');
            if (r.can_view_secret) perms.push('View Secret');
            if (r.can_manage_users) perms.push('Manage Users');
            if (r.can_manage_licenses) perms.push('Manage Licenses');
            if (r.can_reset_hwid) perms.push('HWID Reset');
            if (r.can_view_logs) perms.push('View Logs');
            if (r.can_ban_users) perms.push('Ban Users');
            if (r.can_clean_banned) perms.push('Clean Banned');
            if (r.can_modify_app_settings) perms.push('Edit App Settings');
            const permText = perms.join(', ') || 'No Permissions';

            const dateStr = new Date(r.created_at).toLocaleDateString();

            html += `
                <tr>
                    <td><strong>${r.username}</strong></td>
                    <td style="max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${appNames}</td>
                    <td style="color: var(--primary); font-size: 13px;">${permText}</td>
                    <td>${dateStr}</td>
                    <td>
                        <button class="action-btn icon-btn" onclick="editReseller(${r.id}, '${r.username}', [${r.allowed_apps.join(',')}], ${r.is_admin}, ${r.can_view_secret}, ${r.can_manage_users}, ${r.can_manage_licenses}, ${r.can_reset_hwid}, ${r.can_view_logs}, ${r.can_ban_users}, ${r.can_clean_banned}, ${r.can_modify_app_settings})" title="Edit"><i class="fas fa-edit"></i></button>
                        <button class="action-btn icon-btn danger-btn" onclick="deleteReseller(${r.id})" title="Delete"><i class="fas fa-trash"></i></button>
                    </td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        container.innerHTML = html;
    } catch (e) {
        showToast('Error loading resellers list', 'error');
    }
}

async function loadResellerAppCheckboxes() {
    const container = document.getElementById('reseller-app-checkboxes');
    if (!container) return;

    container.innerHTML = '';
    if (currentApps.length === 0) {
        container.innerHTML = '<span style="color: var(--text-muted); font-size: 13px;">No applications available to select.</span>';
        return;
    }

    currentApps.forEach(app => {
        const label = document.createElement('label');
        label.style.display = 'flex';
        label.style.alignItems = 'center';
        label.style.gap = '8px';
        label.style.color = 'var(--text-muted)';
        label.style.cursor = 'pointer';
        label.innerHTML = `<input type="checkbox" name="reseller-apps" value="${app.id}" style="width: 16px; height: 16px; cursor: pointer;"> ${app.app_name}`;
        container.appendChild(label);
    });
}

async function saveReseller() {
    const editId = document.getElementById('edit-reseller-id').value;
    const username = document.getElementById('reseller-form-username').value.trim();
    const password = document.getElementById('reseller-form-password').value;

    if (!username) {
        return showToast('Reseller username cannot be empty', 'error');
    }
    if (!editId && !password) {
        return showToast('Password is required for new resellers', 'error');
    }

    const allowedApps = [];
    document.querySelectorAll('input[name="reseller-apps"]:checked').forEach(cb => {
        allowedApps.push(parseInt(cb.value));
    });

    const payload = {
        username: username,
        password: password || null,
        allowed_apps: allowedApps,
        is_admin: document.getElementById('perm-is-admin').checked,
        can_view_secret: document.getElementById('perm-view-secret').checked,
        can_manage_users: document.getElementById('perm-manage-users').checked,
        can_manage_licenses: document.getElementById('perm-manage-licenses').checked,
        can_reset_hwid: document.getElementById('perm-reset-hwid').checked,
        can_view_logs: document.getElementById('perm-view-logs').checked,
        can_ban_users: document.getElementById('perm-ban-users').checked,
        can_clean_banned: document.getElementById('perm-clean-banned').checked,
        can_modify_app_settings: document.getElementById('perm-modify-app-settings').checked
    };

    const token = localStorage.getItem('token');
    const method = editId ? 'PUT' : 'POST';
    const url = editId ? `/api/creator/resellers/${editId}` : '/api/creator/resellers';

    try {
        const res = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            showToast(editId ? 'Reseller profile updated!' : 'Reseller profile created!', 'success');
            clearResellerForm();
            loadResellers();
        } else {
            const data = await res.json();
            showToast(data.detail || 'Failed to save reseller profile', 'error');
        }
    } catch (e) {
        showToast('Error communicating with server', 'error');
    }
}

function editReseller(id, username, allowedApps, isAdmin, viewSecret, manageUsers, manageLicenses, resetHwid, viewLogs, banUsers, cleanBanned, modifyAppSettings) {
    document.getElementById('edit-reseller-id').value = id;

    const nameInput = document.getElementById('reseller-form-username');
    nameInput.value = username;
    nameInput.disabled = true;

    document.getElementById('reseller-form-password').placeholder = 'Enter new password to change';
    document.getElementById('reseller-form-pass-hint').style.display = 'inline';

    document.querySelectorAll('input[name="reseller-apps"]').forEach(cb => {
        cb.checked = allowedApps.includes(parseInt(cb.value));
    });

    const adminCb = document.getElementById('perm-is-admin');
    if (adminCb) {
        adminCb.checked = isAdmin;
        toggleResellerAdminState(isAdmin);
    }

    document.getElementById('perm-view-secret').checked = viewSecret;
    document.getElementById('perm-manage-users').checked = manageUsers;
    document.getElementById('perm-manage-licenses').checked = manageLicenses;
    document.getElementById('perm-reset-hwid').checked = resetHwid;
    document.getElementById('perm-view-logs').checked = viewLogs;
    document.getElementById('perm-ban-users').checked = banUsers;
    document.getElementById('perm-clean-banned').checked = cleanBanned;
    document.getElementById('perm-modify-app-settings').checked = modifyAppSettings;

    switchResellersSubTab('resellers-create-panel');

    document.getElementById('reseller-form-title').innerHTML = `<i class="fas fa-user-edit" style="color: var(--primary); margin-right: 8px;"></i>Edit Reseller Profile (${username})`;
    document.getElementById('btn-cancel-reseller-edit').style.display = 'inline-block';
}

async function deleteReseller(id) {
    if (!confirm('Are you sure you want to delete this reseller profile?')) return;

    const token = localStorage.getItem('token');
    try {
        const res = await fetch(`/api/creator/resellers/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (res.ok) {
            showToast('Reseller profile deleted', 'info');
            loadResellers();
        } else {
            const data = await res.json();
            showToast(data.detail || 'Failed to delete reseller', 'error');
        }
    } catch (e) {
        showToast('Error deleting reseller', 'error');
    }
}

function clearResellerForm() {
    document.getElementById('edit-reseller-id').value = '';

    const nameInput = document.getElementById('reseller-form-username');
    nameInput.value = '';
    nameInput.disabled = false;

    document.getElementById('reseller-form-password').value = '';
    document.getElementById('reseller-form-password').placeholder = 'e.g. password123';
    document.getElementById('reseller-form-pass-hint').style.display = 'none';

    document.querySelectorAll('input[name="reseller-apps"]').forEach(cb => cb.checked = false);

    const adminCb = document.getElementById('perm-is-admin');
    if (adminCb) {
        adminCb.checked = false;
        toggleResellerAdminState(false);
    }

    document.getElementById('perm-view-secret').checked = false;
    document.getElementById('perm-manage-users').checked = false;
    document.getElementById('perm-manage-licenses').checked = false;
    document.getElementById('perm-reset-hwid').checked = false;
    document.getElementById('perm-view-logs').checked = false;
    document.getElementById('perm-ban-users').checked = false;
    document.getElementById('perm-clean-banned').checked = false;
    document.getElementById('perm-modify-app-settings').checked = false;

    document.getElementById('reseller-form-title').innerHTML = '<i class="fas fa-user-plus" style="color: var(--primary); margin-right: 8px;"></i>Create New Reseller Profile';
    document.getElementById('btn-cancel-reseller-edit').style.display = 'none';
}

/* Sub-tabs logic for Settings & Resellers */
function switchSettingsSubTab(subTabId) {
    document.querySelectorAll('.settings-sub-content').forEach(el => el.style.display = 'none');
    document.querySelectorAll('#settings-tab .sub-tab-btn').forEach(btn => btn.classList.remove('active'));

    const target = document.getElementById(subTabId);
    if (target) target.style.display = 'block';

    const activeBtn = document.getElementById(`btn-${subTabId}`);
    if (activeBtn) activeBtn.classList.add('active');
}

function switchResellersSubTab(subTabId) {
    document.querySelectorAll('.reseller-sub-content').forEach(el => el.style.display = 'none');
    document.querySelectorAll('#resellers-tab .sub-tab-btn').forEach(btn => btn.classList.remove('active'));

    const target = document.getElementById(subTabId);
    if (target) target.style.display = 'block';

    const activeBtn = document.getElementById(`btn-${subTabId.replace('-panel', '')}`);
    if (activeBtn) activeBtn.classList.add('active');
}

function toggleResellerAdminState(checked) {
    const list = [
        'perm-view-secret',
        'perm-manage-users',
        'perm-manage-licenses',
        'perm-reset-hwid',
        'perm-view-logs',
        'perm-ban-users',
        'perm-clean-banned',
        'perm-modify-app-settings'
    ];
    list.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            if (checked) {
                el.checked = true;
                el.disabled = true;
            } else {
                el.disabled = false;
            }
        }
    });
}

async function saveCreatorProfile() {
    const fullName = document.getElementById('profile-full-name').value.trim();
    const newPassword = document.getElementById('profile-new-password').value;
    const token = localStorage.getItem('token');

    const payload = {};
    if (fullName) payload.full_name = fullName;
    if (newPassword) payload.password = newPassword;

    try {
        const res = await fetch('/api/creator/profile', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            showToast('Profile updated successfully!', 'success');
            document.getElementById('profile-new-password').value = '';
        } else {
            const data = await res.json();
            showToast(data.detail || 'Failed to update profile', 'error');
        }
    } catch (e) {
        showToast('Error communicating with server', 'error');
    }
}

function saveSystemDefaults() {
    const status = document.getElementById('default-app-status').value;
    const version = document.getElementById('default-app-version').value.trim();
    const motd = document.getElementById('default-app-motd').value.trim();
    const hwid = document.getElementById('default-app-hwid').value;

    localStorage.setItem('default_app_status', status);
    localStorage.setItem('default_app_version', version);
    localStorage.setItem('default_app_motd', motd);
    localStorage.setItem('default_app_hwid', hwid);

    showToast('Application defaults saved!', 'success');
}

function loadSystemDefaults() {
    const status = localStorage.getItem('default_app_status') || 'active';
    const version = localStorage.getItem('default_app_version') || '1.0';
    const motd = localStorage.getItem('default_app_motd') || 'Welcome to our application!';
    const hwid = localStorage.getItem('default_app_hwid') || 'true';

    const statusEl = document.getElementById('default-app-status');
    const versionEl = document.getElementById('default-app-version');
    const motdEl = document.getElementById('default-app-motd');
    const hwidEl = document.getElementById('default-app-hwid');

    if (statusEl) statusEl.value = status;
    if (versionEl) versionEl.value = version;
    if (motdEl) motdEl.value = motd;
    if (hwidEl) hwidEl.value = hwid;
}


