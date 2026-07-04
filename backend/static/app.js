const API_URL = '/api/creator';
let currentAppId = null;
let currentApps = [];

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
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({token: response.credential})
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
    document.getElementById('auth-container').style.display = 'block';
    document.getElementById('dashboard-container').style.display = 'none';
    showToast('Logged out successfully', 'info');
}

function showDashboard() {
    document.getElementById('auth-container').style.display = 'none';
    document.getElementById('dashboard-container').style.display = 'flex';
    
    // Update Settings Profile Email & Token dynamically
    const email = localStorage.getItem('email') || 'Unknown';
    const emailSpan = document.getElementById('profile-email');
    if (emailSpan) {
        emailSpan.innerText = email;
    }
    const tokenInput = document.getElementById('profile-api-token');
    if (tokenInput) {
        tokenInput.value = localStorage.getItem('token') || '';
    }
    
    loadApps();
    checkDiscordLink();
}

function showTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
    document.getElementById(`${tabId}-tab`).style.display = 'block';
    if (tabId === 'discord') {
        checkDiscordLink();
    }
}

async function loadApps() {
    const token = localStorage.getItem('token');
    if (!token) return logout();
    
    // For google mock, just show empty
    if(token === 'google_mock_token') {
        document.getElementById('app-list').innerHTML = '<p style="color:var(--text-muted);">No apps (Google mock)</p>';
        return;
    }

    try {
        const res = await fetch(`${API_URL}/apps`, {
            headers: {'Authorization': `Bearer ${token}`}
        });
        if (!res.ok) throw new Error();
        const apps = await res.json();
        currentApps = apps;
        
        const list = document.getElementById('app-list');
        const selector = document.getElementById('app-selector');
        const discordSelector = document.getElementById('discord-app-selector');
        
        list.innerHTML = '';
        if (selector) selector.innerHTML = '<option value="">-- Select an App --</option>';
        if (discordSelector) discordSelector.innerHTML = '<option value="">-- Select an App to Integrate --</option>';
        
        // Update Dashboard Stats
        document.getElementById('stat-apps').innerText = apps.length;
        
        let totalUsers = 0;
        let totalLicenses = 0;

        // Fetch counts for stats (Async all apps)
        await Promise.all(apps.map(async app => {
            try {
                const uRes = await fetch(`${API_URL}/apps/${app.id}/users`, { headers: {'Authorization': `Bearer ${token}`} });
                if(uRes.ok) { const u = await uRes.json(); totalUsers += u.length; }
                
                const lRes = await fetch(`${API_URL}/apps/${app.id}/licenses`, { headers: {'Authorization': `Bearer ${token}`} });
                if(lRes.ok) { const l = await lRes.json(); totalLicenses += l.length; }
            } catch(e){}
        }));
        
        document.getElementById('stat-users').innerText = totalUsers;
        document.getElementById('stat-licenses').innerText = totalLicenses;

        apps.forEach(app => {
            // App Tab Card
            const div = document.createElement('div');
            div.className = 'app-card';
            div.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h3 style="margin:0;"><i class="fas fa-cube" style="color:var(--primary); margin-right:8px;"></i>${app.app_name}</h3>
                    <button onclick="deleteApp(event, ${app.id})" style="width:auto; padding:8px 15px; background:rgba(239, 68, 68, 0.2); color:#ef4444; border:1px solid #ef4444; box-shadow:none;"><i class="fas fa-trash"></i></button>
                </div>
                <div style="margin-top:15px; background:rgba(0,0,0,0.2); padding:10px; border-radius:8px;">
                    <p style="margin:5px 0;"><strong>Owner ID:</strong> <span style="color:white;">${app.owner_id}</span></p>
                    <p style="margin:5px 0;"><strong>Secret:</strong> <span style="color:white;">${app.secret}</span></p>
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

            // Discord Dropdown Option
            if (discordSelector) {
                const opt = document.createElement('option');
                opt.value = app.id;
                opt.text = app.app_name;
                discordSelector.appendChild(opt);
            }
        });
        
        // Update Quick Setup after loading apps!
        updateQuickSetup();
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
            body: JSON.stringify({app_name})
        });
        if (res.ok) {
            document.getElementById('new-app-name').value = '';
            showToast('Application created successfully!', 'success');
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
            headers: {'Authorization': `Bearer ${token}`}
        });
        if (res.ok) {
            showToast('Application deleted.', 'info');
            if (currentAppId === appId) {
                const wsContent = document.getElementById('app-workspace-content');
                if(wsContent) wsContent.style.display = 'none';
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
    if(app) {
        document.getElementById('settings-status').value = app.status || 'active';
        document.getElementById('settings-webhook').value = app.webhook_url || '';
        document.getElementById('settings-version').value = app.version || '1.0';
        document.getElementById('settings-dev-msg').value = app.dev_message || '';
    }

    document.getElementById('app-workspace-content').style.display = 'block';
    showAppTab('users');
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
    selectedTab.style.display = 'block';
    
    // Trigger animation
    setTimeout(() => { selectedTab.classList.add('slide-in'); }, 10);
    
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active-tab-btn'));
    const btn = document.getElementById(`btn-tab-${tab}`);
    if(btn) btn.classList.add('active-tab-btn');
}

async function loadUsers() {
    const token = localStorage.getItem('token');
    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/users`, {
            headers: {'Authorization': `Bearer ${token}`}
        });
        const users = await res.json();
        const list = document.getElementById('user-list');
        let html = '<table class="pro-table" id="user-table"><tr><th>User</th><th>Last IP</th><th>HWID</th><th>Status/Lock</th><th>Expires At</th><th>Actions</th></tr>';
        users.forEach(u => {
            let statusBadge = u.status === 'banned' ? '<span style="color:var(--danger);font-size:12px;border:1px solid var(--danger);padding:2px 4px;border-radius:4px;">BANNED</span>' : '';
            html += `<tr>
                <td>${u.username} <button onclick="copyToClipboard('${u.username}')" style="background:transparent;border:none;color:var(--text-muted);cursor:pointer;padding:0;width:auto;margin:0 5px;box-shadow:none;"><i class="fas fa-copy"></i></button></td>
                <td><span style="color:var(--primary); font-family:monospace;">${u.last_ip || 'Never'}</span></td>
                <td><span style="font-family:monospace; color:var(--text-muted);">${u.hwid ? u.hwid.substring(0,8)+'...' : 'Not Set'}</span></td>
                <td>${statusBadge} ${u.hwid_lock ? '<span style="color:var(--success);"><i class="fas fa-lock"></i></span>' : '<span style="color:var(--danger);"><i class="fas fa-lock-open"></i></span>'}</td>
                <td>${u.expires_at}</td>
                <td>
                    <button class="action-btn icon-btn" onclick="toggleBanUser(${u.id})" title="Ban/Unban"><i class="fas fa-gavel"></i></button>
                    <button class="action-btn icon-btn" onclick="resetUserHWID(${u.id})" title="Reset HWID"><i class="fas fa-undo"></i></button>
                    <button class="action-btn icon-btn danger-btn" onclick="deleteUser(${u.id})" title="Delete User"><i class="fas fa-trash"></i></button>
                </td>
            </tr>`;
        });
        html += '</table>';
        list.innerHTML = html;
        updateGrowthChart(users.length, null); // Basic chart update
    } catch(e) {}
}

async function loadLicenses() {
    const token = localStorage.getItem('token');
    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/licenses`, {
            headers: {'Authorization': `Bearer ${token}`}
        });
        const licenses = await res.json();
        const list = document.getElementById('license-list');
        let html = '<table class="pro-table" id="license-table"><tr><th>Key</th><th>Last IP</th><th>Status/Lock</th><th>Duration</th><th>Expires</th><th>Actions</th></tr>';
        licenses.forEach(l => {
            let statusBadge = l.status === 'banned' ? '<span style="color:var(--danger);font-size:12px;border:1px solid var(--danger);padding:2px 4px;border-radius:4px;">BANNED</span>' : '';
            html += `<tr>
                <td><span style="font-family:monospace; color:var(--primary);">${l.license_key}</span> <button onclick="copyToClipboard('${l.license_key}')" style="background:transparent;border:none;color:var(--text-muted);cursor:pointer;padding:0;width:auto;margin:0 5px;box-shadow:none;"><i class="fas fa-copy"></i></button></td>
                <td><span style="font-family:monospace;">${l.last_ip || 'Never'}</span></td>
                <td>${statusBadge} ${l.hwid_lock ? '<span style="color:var(--success);"><i class="fas fa-lock"></i></span>' : '<span style="color:var(--danger);"><i class="fas fa-lock-open"></i></span>'}</td>
                <td>${l.duration_days} Days</td>
                <td>${l.expires_at}</td>
                <td>
                    <button class="action-btn icon-btn" onclick="toggleBanLicense(${l.id})" title="Ban/Unban"><i class="fas fa-gavel"></i></button>
                    <button class="action-btn icon-btn" onclick="resetLicenseHWID(${l.id})" title="Reset HWID"><i class="fas fa-undo"></i></button>
                    <button class="action-btn icon-btn danger-btn" onclick="deleteLicense(${l.id})" title="Delete License"><i class="fas fa-trash"></i></button>
                </td>
            </tr>`;
        });
        html += '</table>';
        list.innerHTML = html;
        updateGrowthChart(null, licenses.length);
    } catch(e) {}
}

async function addUser() {
    const username = document.getElementById('new-user-name').value;
    const password = document.getElementById('new-user-pass').value;
    const expiry = document.getElementById('new-user-expiry').value;
    const hwidLock = document.getElementById('new-user-hwid').checked;
    const token = localStorage.getItem('token');
    
    if(!username || !password) return showToast('Username and Password required', 'error');

    const payload = {username, password, hwid_lock_enabled: hwidLock};
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
    if(!confirm('Reset HWID for this user?')) return;
    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/users/${id}/reset-hwid`, {
            method: 'POST',
            headers: {'Authorization': `Bearer ${localStorage.getItem('token')}`}
        });
        if(res.ok) { showToast('HWID Reset Successful', 'success'); loadUsers(); }
        else showToast('Error resetting HWID', 'error');
    } catch(e) {}
}

async function deleteUser(id) {
    if(!confirm('Delete this user?')) return;
    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/users/${id}`, {
            method: 'DELETE',
            headers: {'Authorization': `Bearer ${localStorage.getItem('token')}`}
        });
        if(res.ok) { showToast('User Deleted', 'info'); loadUsers(); }
        else showToast('Error deleting user', 'error');
    } catch(e) {}
}

async function resetLicenseHWID(id) {
    if(!confirm('Reset HWID for this license?')) return;
    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/licenses/${id}/reset-hwid`, {
            method: 'POST',
            headers: {'Authorization': `Bearer ${localStorage.getItem('token')}`}
        });
        if(res.ok) { showToast('HWID Reset Successful', 'success'); loadLicenses(); }
        else showToast('Error resetting HWID', 'error');
    } catch(e) {}
}

async function deleteLicense(id) {
    if(!confirm('Delete this license?')) return;
    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/licenses/${id}`, {
            method: 'DELETE',
            headers: {'Authorization': `Bearer ${localStorage.getItem('token')}`}
        });
        if(res.ok) { showToast('License Deleted', 'info'); loadLicenses(); }
        else showToast('Error deleting license', 'error');
    } catch(e) {}
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
            body: JSON.stringify({status: status, webhook_url: webhook, version: version, dev_message: devMsg})
        });
        if(res.ok) {
            showToast('Settings saved successfully', 'success');
            loadApps(); // Reload apps to get updated global state
        } else {
            showToast('Error saving settings', 'error');
        }
    } catch(e) {}
}

async function toggleBanUser(id) {
    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/users/${id}/toggle-ban`, {
            method: 'POST',
            headers: {'Authorization': `Bearer ${localStorage.getItem('token')}`}
        });
        if(res.ok) { showToast('User ban status toggled', 'success'); loadAppWorkspaceData(); }
        else showToast('Error toggling ban', 'error');
    } catch(e) {}
}

async function toggleBanLicense(id) {
    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/licenses/${id}/toggle-ban`, {
            method: 'POST',
            headers: {'Authorization': `Bearer ${localStorage.getItem('token')}`}
        });
        if(res.ok) { showToast('License ban status toggled', 'success'); loadAppWorkspaceData(); }
        else showToast('Error toggling ban', 'error');
    } catch(e) {}
}

async function loadLogs() {
    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/logs`, {
            headers: {'Authorization': `Bearer ${localStorage.getItem('token')}`}
        });
        const logs = await res.json();
        const list = document.getElementById('log-list');
        if(logs.length === 0) {
            list.innerHTML = '<span style="color: var(--text-muted);">No activity logged yet...</span>';
            return;
        }
        let html = '';
        logs.forEach(l => {
            let color = 'var(--text-muted)';
            if(l.action.includes('SUCCESS') || l.action.includes('CREATED') || l.action.includes('GENERATED')) color = 'var(--success)';
            if(l.action.includes('FAILED') || l.action.includes('BAN') || l.action.includes('DELETE')) color = 'var(--danger)';
            
            html += `<div style="margin-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 5px;">
                <span style="color:#64748b;">[${new Date(l.created_at).toLocaleTimeString()}]</span> 
                <span style="color:${color}; font-weight:bold;">[${l.action}]</span> 
                <span style="color:#e2e8f0;">${l.description}</span>
            </div>`;
        });
        list.innerHTML = html;
    } catch(e) {}
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('Copied to clipboard!', 'info');
    });
}

function filterTable(tableContainerId, query) {
    const filter = query.toUpperCase();
    const table = document.getElementById(tableContainerId).querySelector('table');
    if(!table) return;
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
    if(!table) { showToast('No data to export', 'error'); return; }
    
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
    if(!ctx) return;
    
    // We only update if we have both values, or we just randomly plot if incomplete for demo purposes
    if(dashboardChart) {
        if(usersCount !== null) dashboardChart.data.datasets[0].data = [Math.max(usersCount-5, 0), usersCount-2, usersCount];
        if(licensesCount !== null) dashboardChart.data.datasets[1].data = [Math.max(licensesCount-10, 0), licensesCount-5, licensesCount];
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

let resolvedGuildId = null;
let resolvedGuildName = null;
let currentDiscordGuilds = [];

function updateQuickSetup() {
    // Step 1 check
    const step1Status = document.getElementById('step1-status');
    const btnStep1 = document.getElementById('btn-step1');
    const step2Status = document.getElementById('step2-status');
    const btnStep2 = document.getElementById('btn-step2');
    const step3Status = document.getElementById('step3-status');
    const btnStep3 = document.getElementById('btn-step3');
    
    // Check if discord linked first
    const token = localStorage.getItem('token');
    fetch(`${API_URL}/discord/me`, {headers: {'Authorization': `Bearer ${token}`}})
        .then(async res => {
            if (res.ok) {
                // Step 1 complete!
                step1Status.innerText = 'Complete';
                step1Status.style.background = 'rgba(16, 185, 129, 0.2)';
                step1Status.style.color = '#10b981';
                step1Status.style.borderColor = '#10b981';
                btnStep1.disabled = true;
                btnStep1.style.opacity = 0.5;
                
                // Now step 2 unlocked!
                step2Status.innerText = 'Pending';
                step2Status.style.background = 'rgba(239, 68, 68, 0.2)';
                step2Status.style.color = '#ef4444';
                step2Status.style.borderColor = '#ef4444';
                btnStep2.style.opacity = 1;
                btnStep2.style.pointerEvents = 'auto';
                
                // Get invite URL
                const inviteRes = await fetch(`${API_URL}/discord/invite-url`, {headers: {'Authorization': `Bearer ${token}`}});
                if (inviteRes.ok) {
                    const inviteData = await inviteRes.json();
                    btnStep2.href = inviteData.invite_url;
                }
                
                // Mark step 3 as pending
                step3Status.innerText = 'Pending';
                step3Status.style.background = 'rgba(239, 68, 68, 0.2)';
                step3Status.style.color = '#ef4444';
                step3Status.style.borderColor = '#ef4444';
                
                // Check if there are any apps with discord linked to mark step3 complete
                if (currentApps.some(app => app.discord_guild_id && app.discord_channel_id)) {
                    step3Status.innerText = 'Complete!';
                    step3Status.style.background = 'rgba(16, 185, 129, 0.2)';
                    step3Status.style.color = '#10b981';
                    step3Status.style.borderColor = '#10b981';
                    btnStep3.style.opacity = 1;
                    btnStep3.style.pointerEvents = 'auto';
                    step2Status.innerText = 'Complete';
                    step2Status.style.background = 'rgba(16, 185, 129, 0.2)';
                    step2Status.style.color = '#10b981';
                    step2Status.style.borderColor = '#10b981';
                }
            }
        });
}

async function checkDiscordLink() {
    const token = localStorage.getItem('token');
    try {
        const res = await fetch(`${API_URL}/discord/me`, {headers: {'Authorization': `Bearer ${token}`}});
        if (res.ok) {
            const userData = await res.json();
            document.getElementById('discord-link-status').style.display = 'none';
            document.getElementById('discord-linked-status').style.display = 'block';
            document.getElementById('discord-user-tag').innerText = userData.username + '#' + (userData.discriminator || '0');
            await loadDiscordGuilds();
            updateQuickSetup();
        }
    } catch(e) {
        // Discord not linked
        document.getElementById('discord-link-status').style.display = 'block';
        document.getElementById('discord-linked-status').style.display = 'none';
    }
}

async function linkDiscordAccount() {
    const token = localStorage.getItem('token');
    try {
        const res = await fetch(`${API_URL}/discord/login`, {headers: {'Authorization': `Bearer ${token}`}});
        if (res.ok) {
            const data = await res.json();
            window.location.href = data.auth_url;
        }
    } catch(e) {
        showToast('Error initiating Discord link', 'error');
    }
}

async function loadDiscordGuilds() {
    const token = localStorage.getItem('token');
    try {
        const res = await fetch(`${API_URL}/discord/guilds`, {headers: {'Authorization': `Bearer ${token}`}});
        if (res.ok) {
            const guilds = await res.json();
            currentDiscordGuilds = guilds;
            const guildSelector = document.getElementById('discord-guild-selector');
            guildSelector.innerHTML = '<option value="">-- Select Server --</option>';
            guilds.forEach(g => {
                const opt = document.createElement('option');
                opt.value = g.id;
                opt.text = g.name;
                guildSelector.appendChild(opt);
            });
            showToast(`Loaded ${guilds.length} servers!`, 'info');
        } else {
            throw new Error();
        }
    } catch(e) {
        showToast('Could not load Discord servers', 'error');
    }
}

async function onDiscordGuildSelect(guildId) {
    if (!guildId) {
        document.getElementById('discord-channel-selector').innerHTML = '<option value="">-- Choose Channel --</option>';
        document.getElementById('discord-invite-link').href = '#';
        return;
    }
    
    resolvedGuildId = guildId;
    const guild = currentDiscordGuilds.find(g => g.id == guildId);
    if (guild) resolvedGuildName = guild.name;
    
    // Update invite link
    const token = localStorage.getItem('token');
    try {
        const resInvite = await fetch(`${API_URL}/discord/invite-url?guild_id=${guildId}`, {headers: {'Authorization': `Bearer ${token}`}});
        if (resInvite.ok) {
            const data = await resInvite.json();
            document.getElementById('discord-invite-link').href = data.invite_url;
        }
    } catch(e) {}
    
    // Load channels
    await loadDiscordGuildChannels(guildId);
}

async function loadDiscordGuildChannels(guildId, selectedChannelId = null) {
    const token = localStorage.getItem('token');
    const selector = document.getElementById('discord-channel-selector');
    selector.innerHTML = '<option value="">-- Loading Channels --</option>';
    
    try {
        const res = await fetch(`${API_URL}/discord/guilds/${guildId}/channels`, {
            headers: {'Authorization': `Bearer ${token}`}
        });
        if (res.ok) {
            const channels = await res.json();
            selector.innerHTML = '<option value="">-- Choose Channel --</option>';
            channels.forEach(ch => {
                const opt = document.createElement('option');
                opt.value = ch.id;
                opt.text = `#${ch.name}`;
                if (selectedChannelId && ch.id == selectedChannelId) {
                    opt.selected = true;
                }
                selector.appendChild(opt);
            });
        } else {
            const data = await res.json();
            selector.innerHTML = '<option value="">-- Invite bot first, then refresh --</option>';
            showToast(data.detail || 'Make sure the Bot is in your server!', 'warning');
        }
    } catch(e) {
        selector.innerHTML = '<option value="">-- Error loading channels --</option>';
    }
}

async function switchDiscordApp(appId) {
    if (!appId) {
        document.getElementById('discord-integration-details').style.display = 'none';
        return;
    }
    
    document.getElementById('discord-integration-details').style.display = 'block';
    
    const app = currentApps.find(a => a.id == appId);
    if (!app) return;
    
    const statusText = document.getElementById('discord-status-text');
    const statusBadge = document.getElementById('discord-status-badge');
    const unlinkBtn = document.getElementById('discord-unlink-btn');
    
    if (app.discord_guild_id && app.discord_channel_id) {
        statusText.innerText = `Linked to server "${app.discord_guild_name}" in channel #${app.discord_channel_name}`;
        statusBadge.innerText = 'Active';
        statusBadge.style.background = 'rgba(16, 185, 129, 0.2)';
        statusBadge.style.color = '#10b981';
        statusBadge.style.borderColor = '#10b981';
        unlinkBtn.style.display = 'inline-block';
        
        // Populate the guild selector
        resolvedGuildId = app.discord_guild_id;
        resolvedGuildName = app.discord_guild_name;
        const guildSelector = document.getElementById('discord-guild-selector');
        const existingOption = Array.from(guildSelector.options).find(o => o.value == resolvedGuildId);
        if (!existingOption) {
            const opt = document.createElement('option');
            opt.value = resolvedGuildId;
            opt.text = resolvedGuildName;
            guildSelector.appendChild(opt);
        }
        guildSelector.value = resolvedGuildId;
        
        // Set invite url
        const token = localStorage.getItem('token');
        try {
            const resInvite = await fetch(`${API_URL}/discord/invite-url?guild_id=${resolvedGuildId}`, {headers: {'Authorization': `Bearer ${token}`}});
            if (resInvite.ok) {
                const data = await resInvite.json();
                document.getElementById('discord-invite-link').href = data.invite_url;
            }
        } catch(e) {}
        
        // Load channels
        await loadDiscordGuildChannels(resolvedGuildId, app.discord_channel_id);
    } else {
        statusText.innerText = 'Not Configured';
        statusBadge.innerText = 'Inactive';
        statusBadge.style.background = 'rgba(239, 68, 68, 0.2)';
        statusBadge.style.color = '#ef4444';
        statusBadge.style.borderColor = '#ef4444';
        unlinkBtn.style.display = 'none';
    }
}

async function resolveDiscordInvite() {
    const invite = document.getElementById('discord-invite-input').value.trim();
    if (!invite) return showToast('Please enter an invite link or code', 'error');
    
    const token = localStorage.getItem('token');
    try {
        const res = await fetch(`${API_URL}/discord/resolve-invite?invite=${encodeURIComponent(invite)}`, {
            headers: {'Authorization': `Bearer ${token}`}
        });
        const data = await res.json();
        if (res.ok) {
            resolvedGuildId = data.guild_id;
            resolvedGuildName = data.guild_name;
            
            // Load into selector
            const guildSelector = document.getElementById('discord-guild-selector');
            const existingOption = Array.from(guildSelector.options).find(o => o.value == resolvedGuildId);
            if (!existingOption) {
                const opt = document.createElement('option');
                opt.value = resolvedGuildId;
                opt.text = resolvedGuildName;
                guildSelector.appendChild(opt);
            }
            guildSelector.value = resolvedGuildId;
            
            // Set invite URL
            const resInvite = await fetch(`${API_URL}/discord/invite-url?guild_id=${resolvedGuildId}`, {headers: {'Authorization': `Bearer ${token}`}});
            if (resInvite.ok) {
                const inviteData = await resInvite.json();
                document.getElementById('discord-invite-link').href = inviteData.invite_url;
            }
            
            showToast('Discord server found!', 'success');
            
            // Fetch channels
            await loadDiscordGuildChannels(resolvedGuildId);
        } else {
            showToast(data.detail || 'Could not resolve invite link', 'error');
        }
    } catch(e) {
        showToast('Error resolving invite', 'error');
    }
}

async function loadDiscordChannels(guildId, selectedChannelId = null) {
    await loadDiscordGuildChannels(guildId, selectedChannelId);
}

async function saveDiscordConfig() {
    const appId = document.getElementById('discord-app-selector').value;
    const channelId = document.getElementById('discord-channel-selector').value;
    const channelSelector = document.getElementById('discord-channel-selector');
    const channelName = channelSelector.options[channelSelector.selectedIndex]?.text.replace('#', '') || '';
    
    if (!channelId) return showToast('Please select an operating channel', 'error');
    
    const token = localStorage.getItem('token');
    try {
        const res = await fetch(`${API_URL}/apps/${appId}/discord`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                discord_guild_id: resolvedGuildId,
                discord_channel_id: channelId,
                discord_guild_name: resolvedGuildName,
                discord_channel_name: channelName
            })
        });
        if (res.ok) {
            showToast('Discord configuration saved successfully!', 'success');
            await loadApps();
            // Re-select to update the status card view
            document.getElementById('discord-app-selector').value = appId;
            await switchDiscordApp(appId);
        } else {
            const data = await res.json();
            showToast(data.detail || 'Failed to save configuration', 'error');
        }
    } catch(e) {
        showToast('Error saving Discord config', 'error');
    }
}

async function unlinkDiscordConfig() {
    if (!confirm('Are you sure you want to unlink Discord from this application?')) return;
    
    const appId = document.getElementById('discord-app-selector').value;
    const token = localStorage.getItem('token');
    try {
        const res = await fetch(`${API_URL}/apps/${appId}/discord`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                discord_guild_id: null,
                discord_channel_id: null,
                discord_guild_name: null,
                discord_channel_name: null
            })
        });
        if (res.ok) {
            showToast('Discord integration removed.', 'info');
            await loadApps();
            // Re-select to update UI
            document.getElementById('discord-app-selector').value = appId;
            await switchDiscordApp(appId);
        } else {
            const data = await res.json();
            showToast(data.detail || 'Failed to unlink', 'error');
        }
    } catch(e) {
        showToast('Error unlinking Discord integration', 'error');
    }
}

// Check auth on load
if (localStorage.getItem('token')) {
    showDashboard();
}
