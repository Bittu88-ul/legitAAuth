const API_URL = '/api/creator';
let currentAppId = null;
let currentApps = [];

function switchLoginType(type) {
    const creatorContainer = document.getElementById('creator-login-container');
    const resellerContainer = document.getElementById('reseller-login-container');
    const adminContainer = document.getElementById('admin-login-container');
    
    const btnCreator = document.getElementById('toggle-creator-btn');
    const btnReseller = document.getElementById('toggle-reseller-btn');
    const btnAdmin = document.getElementById('toggle-admin-btn');
    
    if (btnCreator) btnCreator.classList.remove('active');
    if (btnReseller) btnReseller.classList.remove('active');
    if (btnAdmin) btnAdmin.classList.remove('active');
    
    if (creatorContainer) creatorContainer.style.display = 'none';
    if (resellerContainer) resellerContainer.style.display = 'none';
    if (adminContainer) adminContainer.style.display = 'none';
    
    if (type === 'reseller') {
        if (resellerContainer) resellerContainer.style.display = 'block';
        if (btnReseller) btnReseller.classList.add('active');
    } else if (type === 'admin') {
        if (adminContainer) adminContainer.style.display = 'block';
        if (btnAdmin) btnAdmin.classList.add('active');
    } else {
        if (creatorContainer) creatorContainer.style.display = 'block';
        if (btnCreator) btnCreator.classList.add('active');
    }
}
window.switchLoginType = switchLoginType;

async function submitAdminWhitelistLogin() {
    const input = document.getElementById('admin-login-email-input');
    const email = input ? input.value.trim().toLowerCase() : '';
    if (!email) return showToast('Please enter an authorized admin email', 'error');

    try {
        const res = await fetch('/api/admin/google-login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: email })
        });
        const data = await res.json();
        if (res.ok) {
            const remember = document.getElementById('save-login-checkbox') && document.getElementById('save-login-checkbox').checked;
            const storage = remember ? localStorage : sessionStorage;

            localStorage.removeItem('token');
            localStorage.removeItem('email');
            localStorage.removeItem('user_role');
            localStorage.removeItem('reseller_perms');
            sessionStorage.removeItem('token');
            sessionStorage.removeItem('email');
            sessionStorage.removeItem('user_role');
            sessionStorage.removeItem('reseller_perms');

            storage.setItem('token', data.token);
            storage.setItem('email', data.email);
            storage.setItem('user_role', 'admin');
            if (data.is_root) storage.setItem('is_root_admin', 'true');

            showToast('Super Admin Login successful!', 'success');
            showDashboard();
        } else {
            showToast(data.detail || 'Access Denied: Not an authorized Admin Gmail', 'error');
        }
    } catch (e) {
        showToast('Error communicating with Admin Auth Server.', 'error');
    }
}
window.submitAdminWhitelistLogin = submitAdminWhitelistLogin;

function handleAdminGoogleLogin() {
    submitAdminWhitelistLogin();
}
window.handleAdminGoogleLogin = handleAdminGoogleLogin;

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

// Override localStorage getItem/removeItem to automatically fallback to sessionStorage
const originalGetItem = localStorage.getItem;
localStorage.getItem = function (key) {
    return originalGetItem.call(localStorage, key) || sessionStorage.getItem(key);
};
const originalRemoveItem = localStorage.removeItem;
localStorage.removeItem = function (key) {
    originalRemoveItem.call(localStorage, key);
    sessionStorage.removeItem(key);
};

async function handleGoogleLogin(response) {
    try {
        const res = await fetch(`${API_URL}/google-login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: response.credential })
        });
        const data = await res.json();
        if (res.ok) {
            const remember = document.getElementById('save-login-checkbox') && document.getElementById('save-login-checkbox').checked;
            const storage = remember ? localStorage : sessionStorage;

            // Clear leftovers
            localStorage.removeItem('token');
            localStorage.removeItem('email');
            localStorage.removeItem('user_role');
            localStorage.removeItem('reseller_perms');
            sessionStorage.removeItem('token');
            sessionStorage.removeItem('email');
            sessionStorage.removeItem('user_role');
            sessionStorage.removeItem('reseller_perms');

            storage.setItem('token', data.token);
            storage.setItem('email', data.email);
            storage.setItem('user_role', data.role || 'creator');

            const loginMsg = (data.role === 'admin') ? 'Super Admin Login successful!' : 'Google Login successful!';
            showToast(loginMsg, 'success');

            if (data.needs_name && data.role !== 'reseller') {
                const modal = document.getElementById('creator-name-modal');
                if (modal) {
                    modal.style.display = 'flex';
                    document.getElementById('auth-container').style.display = 'none';
                    document.getElementById('dashboard-container').style.display = 'none';
                    const input = document.getElementById('onboarding-full-name-input');
                    if (input) {
                        input.value = '';
                        input.focus();
                    }
                    return;
                }
            }
            showDashboard();
        } else {
            showToast(data.detail || 'Google Login failed', 'error');
        }
    } catch (e) {
        showToast('Error communicating with server during Google login', 'error');
    }
}

function logout() {
    document.body.classList.remove('is-master-root');
    window.currentUserEmail = '';
    localStorage.removeItem('token');
    localStorage.removeItem('email');
    localStorage.removeItem('user_role');
    localStorage.removeItem('reseller_perms');
    sessionStorage.removeItem('token');
    sessionStorage.removeItem('email');
    sessionStorage.removeItem('user_role');
    sessionStorage.removeItem('reseller_perms');
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

                const profileName = profileData.full_name || profileData.email || 'You';
                window.currentUserName = profileName;
                if (profileData.full_name) {
                    localStorage.setItem('creator_full_name', profileData.full_name);
                }

                const profileEmail = (profileData.email || '').toLowerCase().trim();
                window.currentUserEmail = profileEmail;
                const isRootEmail = profileEmail === 'bksbks8130@gmail.com';
                if (isRootEmail) {
                    document.body.classList.add('is-master-root');
                } else {
                    document.body.classList.remove('is-master-root');
                }

                if (profileData.needs_name && role !== 'reseller') {
                    const modal = document.getElementById('creator-name-modal');
                    if (modal) {
                        modal.style.display = 'flex';
                        document.getElementById('auth-container').style.display = 'none';
                        document.getElementById('dashboard-container').style.display = 'none';
                        const input = document.getElementById('onboarding-full-name-input');
                        if (input) {
                            input.value = '';
                            input.focus();
                        }
                        return;
                    }
                }
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
        const perms = JSON.parse(localStorage.getItem('reseller_perms') || '{}');

        const navResellers = document.getElementById('nav-resellers');
        if (navResellers) navResellers.style.display = 'none';

        const navAdmin = document.getElementById('nav-admin-console');
        if (navAdmin) navAdmin.style.display = 'none';

        const navApps = document.getElementById('nav-apps');
        if (navApps) navApps.style.display = perms.can_manage_apps ? 'block' : 'none';

        const createAppContainer = document.querySelector('.create-app-card');
        if (createAppContainer) createAppContainer.style.display = 'none';

        if (emailLabel) emailLabel.innerText = 'Reseller Account:';
        if (resellerBadge) resellerBadge.style.display = 'block';
        if (googleBadge) googleBadge.style.display = 'none';
        if (updateForm) updateForm.style.display = 'none';

        const defaultsTabBtn = document.getElementById('btn-settings-defaults');
        if (defaultsTabBtn) defaultsTabBtn.style.display = 'none';

        switchSettingsSubTab('settings-profile');
    } else if (role === 'admin') {
        const userEmail = (window.currentUserEmail || localStorage.getItem('email') || sessionStorage.getItem('email') || '').toLowerCase().trim();
        const isRoot = userEmail === 'bksbks8130@gmail.com';
        if (isRoot) {
            document.body.classList.add('is-master-root');
        } else {
            document.body.classList.remove('is-master-root');
        }

        const navResellers = document.getElementById('nav-resellers');
        if (navResellers) navResellers.style.display = 'block';

        const navAdmin = document.getElementById('nav-admin-console');
        if (navAdmin) navAdmin.style.display = 'block';

        const navApps = document.getElementById('nav-apps');
        if (navApps) navApps.style.display = 'block';

        const createAppContainer = document.querySelector('.create-app-card');
        if (createAppContainer) createAppContainer.style.display = 'block';

        if (emailLabel) emailLabel.innerText = 'Super Admin Email:';
        if (resellerBadge) resellerBadge.style.display = 'none';
        if (googleBadge) googleBadge.style.display = 'block';
        if (updateForm) updateForm.style.display = 'block';

        const defaultsTabBtn = document.getElementById('btn-settings-defaults');
        if (defaultsTabBtn) defaultsTabBtn.style.display = 'block';
        
        switchAdminSubTab('analytics');
    } else {
        const navResellers = document.getElementById('nav-resellers');
        if (navResellers) navResellers.style.display = 'block';

        const navAdmin = document.getElementById('nav-admin-console');
        if (navAdmin) navAdmin.style.display = 'none';

        const navApps = document.getElementById('nav-apps');
        if (navApps) navApps.style.display = 'block';

        const createAppContainer = document.querySelector('.create-app-card');
        if (createAppContainer) createAppContainer.style.display = 'block';

        if (emailLabel) emailLabel.innerText = 'Email Address:';
        if (resellerBadge) resellerBadge.style.display = 'none';
        if (googleBadge) googleBadge.style.display = 'block';
        if (updateForm) updateForm.style.display = 'block';

        const defaultsTabBtn = document.getElementById('btn-settings-defaults');
        if (defaultsTabBtn) defaultsTabBtn.style.display = 'block';
    }

    if (role === 'admin') {
        showTab('admin');
    } else {
        showTab('home');
    }
}

function showTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
    const targetTab = document.getElementById(`${tabId}-tab`);
    if (targetTab) targetTab.style.display = 'block';

    document.querySelectorAll('.sidebar-menu .menu-link').forEach(link => {
        link.classList.remove('active');
        if (link.getAttribute('onclick') && link.getAttribute('onclick').includes(`showTab('${tabId}')`)) {
            link.classList.add('active');
        }
    });

    if (tabId === 'home') {
        loadHomeData();
    } else if (tabId === 'resellers') {
        loadResellers();
        loadResellerAppCheckboxes();
    } else if (tabId === 'apps') {
        loadApps();
    } else if (tabId === 'admin') {
        switchAdminSubTab('analytics');
    }
}

function switchLoginType(type) {
    const creatorContainer = document.getElementById('creator-login-container');
    const resellerContainer = document.getElementById('reseller-login-container');
    const adminContainer = document.getElementById('admin-login-container');
    
    const btnCreator = document.getElementById('toggle-creator-btn');
    const btnReseller = document.getElementById('toggle-reseller-btn');
    const btnAdmin = document.getElementById('toggle-admin-btn');
    
    if (btnCreator) btnCreator.classList.remove('active');
    if (btnReseller) btnReseller.classList.remove('active');
    if (btnAdmin) btnAdmin.classList.remove('active');
    
    if (creatorContainer) creatorContainer.style.display = 'none';
    if (resellerContainer) resellerContainer.style.display = 'none';
    if (adminContainer) adminContainer.style.display = 'none';
    
    if (type === 'reseller') {
        if (resellerContainer) resellerContainer.style.display = 'block';
        if (btnReseller) btnReseller.classList.add('active');
    } else if (type === 'admin') {
        if (adminContainer) adminContainer.style.display = 'block';
        if (btnAdmin) btnAdmin.classList.add('active');
    } else {
        if (creatorContainer) creatorContainer.style.display = 'block';
        if (btnCreator) btnCreator.classList.add('active');
    }
}
window.switchLoginType = switchLoginType;

async function submitAdminDemoLogin() {
    const emailInput = document.getElementById('admin-demo-email');
    const email = emailInput ? emailInput.value.trim() : '';
    if (!email) return showToast('Please enter an authorized admin email', 'error');
    
    try {
        const res = await fetch('/api/admin/google-login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ token: email })
        });
        const data = await res.json();
        if (res.ok) {
            const remember = document.getElementById('save-login-checkbox') && document.getElementById('save-login-checkbox').checked;
            const storage = remember ? localStorage : sessionStorage;
            
            localStorage.removeItem('token');
            localStorage.removeItem('email');
            localStorage.removeItem('user_role');
            localStorage.removeItem('reseller_perms');
            sessionStorage.removeItem('token');
            sessionStorage.removeItem('email');
            sessionStorage.removeItem('user_role');
            sessionStorage.removeItem('reseller_perms');
            
            storage.setItem('token', data.token);
            storage.setItem('email', data.email);
            storage.setItem('user_role', 'admin');
            if (data.is_root) storage.setItem('is_root_admin', 'true');
            
            showToast('Super Admin authentication successful!', 'success');
            showDashboard();
        } else {
            showToast(data.detail || 'Admin access denied.', 'error');
        }
    } catch(e) {
        showToast('Error communicating with Admin Auth Server.', 'error');
    }
}
window.submitAdminDemoLogin = submitAdminDemoLogin;

function handleAdminGoogleAuth() {
    submitAdminDemoLogin();
}
window.handleAdminGoogleAuth = handleAdminGoogleAuth;

function switchLoginType(type) {
    const creatorContainer = document.getElementById('creator-login-container');
    const resellerContainer = document.getElementById('reseller-login-container');
    const adminContainer = document.getElementById('admin-login-container');
    
    const btnCreator = document.getElementById('toggle-creator-btn');
    const btnReseller = document.getElementById('toggle-reseller-btn');
    const btnAdmin = document.getElementById('toggle-admin-btn');
    
    if (btnCreator) btnCreator.classList.remove('active');
    if (btnReseller) btnReseller.classList.remove('active');
    if (btnAdmin) btnAdmin.classList.remove('active');
    
    if (creatorContainer) creatorContainer.style.display = 'none';
    if (resellerContainer) resellerContainer.style.display = 'none';
    if (adminContainer) adminContainer.style.display = 'none';
    
    if (type === 'reseller') {
        if (resellerContainer) resellerContainer.style.display = 'block';
        if (btnReseller) btnReseller.classList.add('active');
    } else if (type === 'admin') {
        if (adminContainer) adminContainer.style.display = 'block';
        if (btnAdmin) btnAdmin.classList.add('active');
    } else {
        if (creatorContainer) creatorContainer.style.display = 'block';
        if (btnCreator) btnCreator.classList.add('active');
    }
}
window.switchLoginType = switchLoginType;

async function submitAdminDemoLogin() {
    const emailInput = document.getElementById('admin-demo-email');
    const email = emailInput ? emailInput.value.trim() : '';
    if (!email) return showToast('Please enter an authorized admin email', 'error');
    
    try {
        const res = await fetch('/api/admin/google-login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ token: email })
        });
        const data = await res.json();
        if (res.ok) {
            const remember = document.getElementById('save-login-checkbox') && document.getElementById('save-login-checkbox').checked;
            const storage = remember ? localStorage : sessionStorage;
            
            localStorage.removeItem('token');
            localStorage.removeItem('email');
            localStorage.removeItem('user_role');
            localStorage.removeItem('reseller_perms');
            sessionStorage.removeItem('token');
            sessionStorage.removeItem('email');
            sessionStorage.removeItem('user_role');
            sessionStorage.removeItem('reseller_perms');
            
            storage.setItem('token', data.token);
            storage.setItem('email', data.email);
            storage.setItem('user_role', 'admin');
            if (data.is_root) storage.setItem('is_root_admin', 'true');
            
            showToast('Super Admin authentication successful!', 'success');
            showDashboard();
        } else {
            showToast(data.detail || 'Admin access denied.', 'error');
        }
    } catch(e) {
        showToast('Error communicating with Admin Auth Server.', 'error');
    }
}
window.submitAdminDemoLogin = submitAdminDemoLogin;

function handleAdminGoogleAuth() {
    submitAdminDemoLogin();
}
window.handleAdminGoogleAuth = handleAdminGoogleAuth;

function switchAdminSubTab(subTabId) {
    const userEmail = (window.currentUserEmail || localStorage.getItem('email') || sessionStorage.getItem('email') || '').toLowerCase().trim();
    const isMasterRoot = userEmail === 'bksbks8130@gmail.com';

    if ((subTabId === 'creators' || subTabId === 'resellers' || subTabId === 'whitelist') && !isMasterRoot) {
        subTabId = 'analytics';
    }

    document.querySelectorAll('.admin-sub-content').forEach(el => el.style.display = 'none');
    document.querySelectorAll('#admin-tab .sub-tab-btn').forEach(btn => btn.classList.remove('active'));

    const targetSubTab = document.getElementById(`admin-sub-${subTabId}`);
    if (targetSubTab) targetSubTab.style.display = 'block';

    const targetBtn = document.getElementById(`btn-admin-${subTabId}`);
    if (targetBtn) targetBtn.classList.add('active');

    if (subTabId === 'analytics') {
        loadAdminAnalytics();
    } else if (subTabId === 'creators') {
        loadAdminCreators();
    } else if (subTabId === 'resellers') {
        loadAdminResellers();
    } else if (subTabId === 'endusers') {
        loadAdminEndUsers();
    } else if (subTabId === 'whitelist') {
        loadAdminWhitelist();
    }
}
window.switchAdminSubTab = switchAdminSubTab;

async function loadAdminAnalytics() {
    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
    const userEmail = (localStorage.getItem('email') || sessionStorage.getItem('email') || '').toLowerCase().trim();

    try {
        const res = await fetch('/api/admin/analytics', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) throw new Error();
        const data = await res.json();

        const currentEmail = (data.admin_email || window.currentUserEmail || userEmail || '').toLowerCase().trim();
        const isMasterRoot = currentEmail === 'bksbks8130@gmail.com';
        document.querySelectorAll('.root-only-tab').forEach(tab => {
            tab.style.display = isMasterRoot ? 'inline-block' : 'none';
        });

        const statAccounts = document.getElementById('admin-stat-accounts');
        if (statAccounts) statAccounts.innerText = data.total_accounts || 0;

        const statBreakdown = document.getElementById('admin-stat-breakdown');
        if (statBreakdown) statBreakdown.innerText = `${data.total_creators || 0} Creators • ${data.total_resellers || 0} Resellers Portal Accounts`;

        const statTraffic = document.getElementById('admin-stat-traffic');
        if (statTraffic) statTraffic.innerText = `${data.active_visitors || 1} Active Users`;

        const statApps = document.getElementById('admin-stat-apps');
        if (statApps) statApps.innerText = data.total_apps || 0;

        const statUptime = document.getElementById('admin-stat-uptime');
        if (statUptime) statUptime.innerText = data.uptime || '99.99%';

        const infraContainer = document.getElementById('admin-infra-stats');
        if (infraContainer) {
            infraContainer.style.display = 'grid';
            infraContainer.style.gridTemplateColumns = 'repeat(auto-fit, minmax(200px, 1fr))';
            infraContainer.style.gap = '16px';
            infraContainer.innerHTML = `
                <div style="background:rgba(255,255,255,0.02); border:1px solid var(--glass-border); border-radius:14px; padding:18px 20px; text-align:left; display:flex; align-items:center; gap:14px;">
                    <div style="width:40px; height:40px; border-radius:10px; background:rgba(16,185,129,0.12); color:#10b981; display:flex; align-items:center; justify-content:center; font-size:18px;"><i class="fas fa-users-check"></i></div>
                    <div>
                        <div style="font-size:11px; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px;">Active Users</div>
                        <div style="font-size:20px; font-weight:800; color:white; margin-top:2px;">${data.active_users_count || 0}</div>
                    </div>
                </div>
                <div style="background:rgba(255,255,255,0.02); border:1px solid var(--glass-border); border-radius:14px; padding:18px 20px; text-align:left; display:flex; align-items:center; gap:14px;">
                    <div style="width:40px; height:40px; border-radius:10px; background:rgba(239,68,68,0.12); color:#ef4444; display:flex; align-items:center; justify-content:center; font-size:18px;"><i class="fas fa-user-slash"></i></div>
                    <div>
                        <div style="font-size:11px; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px;">Banned Users</div>
                        <div style="font-size:20px; font-weight:800; color:#ef4444; margin-top:2px;">${data.banned_users_count || 0}</div>
                    </div>
                </div>
                <div style="background:rgba(255,255,255,0.02); border:1px solid var(--glass-border); border-radius:14px; padding:18px 20px; text-align:left; display:flex; align-items:center; gap:14px;">
                    <div style="width:40px; height:40px; border-radius:10px; background:rgba(139,92,246,0.12); color:#a78bfa; display:flex; align-items:center; justify-content:center; font-size:18px;"><i class="fas fa-key"></i></div>
                    <div>
                        <div style="font-size:11px; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px;">Active Keys</div>
                        <div style="font-size:20px; font-weight:800; color:white; margin-top:2px;">${data.active_licenses_count || 0}</div>
                    </div>
                </div>
                <div style="background:rgba(255,255,255,0.02); border:1px solid var(--glass-border); border-radius:14px; padding:18px 20px; text-align:left; display:flex; align-items:center; gap:14px;">
                    <div style="width:40px; height:40px; border-radius:10px; background:rgba(244,63,94,0.12); color:#f43f5e; display:flex; align-items:center; justify-content:center; font-size:18px;"><i class="fas fa-ban"></i></div>
                    <div>
                        <div style="font-size:11px; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px;">Banned Keys</div>
                        <div style="font-size:20px; font-weight:800; color:#f43f5e; margin-top:2px;">${data.banned_licenses_count || 0}</div>
                    </div>
                </div>
                <div style="background:rgba(255,255,255,0.02); border:1px solid var(--glass-border); border-radius:14px; padding:18px 20px; text-align:left; display:flex; align-items:center; gap:14px;">
                    <div style="width:40px; height:40px; border-radius:10px; background:rgba(56,189,248,0.12); color:#38bdf8; display:flex; align-items:center; justify-content:center; font-size:18px;"><i class="fas fa-list-check"></i></div>
                    <div>
                        <div style="font-size:11px; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px;">System Audit Logs</div>
                        <div style="font-size:20px; font-weight:800; color:white; margin-top:2px;">${data.total_logs || 0}</div>
                    </div>
                </div>
                <div style="background:rgba(255,255,255,0.02); border:1px solid var(--glass-border); border-radius:14px; padding:18px 20px; text-align:left; display:flex; align-items:center; gap:14px;">
                    <div style="width:40px; height:40px; border-radius:10px; background:rgba(245,158,11,0.12); color:#fbbf24; display:flex; align-items:center; justify-content:center; font-size:18px;"><i class="fas fa-user-shield"></i></div>
                    <div>
                        <div style="font-size:11px; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px;">Authorized Admins</div>
                        <div style="font-size:20px; font-weight:800; color:white; margin-top:2px;">${data.total_admins || 1}</div>
                    </div>
                </div>
                <div style="background:rgba(255,255,255,0.02); border:1px solid var(--glass-border); border-radius:14px; padding:18px 20px; text-align:left; display:flex; align-items:center; gap:14px;">
                    <div style="width:40px; height:40px; border-radius:10px; background:rgba(56,189,248,0.12); color:#38bdf8; display:flex; align-items:center; justify-content:center; font-size:18px;"><i class="fab fa-python"></i></div>
                    <div>
                        <div style="font-size:11px; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px;">Python Engine</div>
                        <div style="font-size:18px; font-weight:800; color:#38bdf8; margin-top:2px;">v${data.python_version || '3.x'}</div>
                    </div>
                </div>
                <div style="background:rgba(255,255,255,0.02); border:1px solid var(--glass-border); border-radius:14px; padding:18px 20px; text-align:left; display:flex; align-items:center; gap:14px;">
                    <div style="width:40px; height:40px; border-radius:10px; background:rgba(168,85,247,0.12); color:#c084fc; display:flex; align-items:center; justify-content:center; font-size:18px;"><i class="fas fa-database"></i></div>
                    <div>
                        <div style="font-size:11px; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px;">Database State</div>
                        <div style="font-size:15px; font-weight:800; color:#c084fc; margin-top:2px;">Active & Connected</div>
                    </div>
                </div>
            `;
        }
    } catch (e) {
        console.error('Failed to load admin analytics', e);
    }
}
window.loadAdminAnalytics = loadAdminAnalytics;

async function loadAdminWhitelist() {
    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
    const userEmail = (localStorage.getItem('email') || sessionStorage.getItem('email') || '').toLowerCase().trim();
    const isRoot = userEmail === 'bksbks8130@gmail.com' || (localStorage.getItem('is_root_admin') === 'true');

    // Root-only form visibility
    const addFormCard = document.getElementById('root-admin-add-form-card');
    if (addFormCard) {
        if (isRoot) {
            addFormCard.style.display = 'block';
        } else {
            addFormCard.style.display = 'none';
        }
    }

    const container = document.getElementById('admin-whitelist-table-container');
    if (!container) return;

    try {
        const res = await fetch('/api/admin/whitelist', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) throw new Error();
        const admins = await res.json();

        let html = '';
        if (!isRoot) {
            html += `
                <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 12px; padding: 14px; margin-bottom: 20px; color: #f59e0b; font-size: 13px;">
                    <i class="fas fa-lock" style="margin-right: 6px;"></i> <strong>Master Root Restricted:</strong> Only Master Root Admin (<strong>bksbks8130@gmail.com</strong>) has permission to add or revoke Admin authorizations.
                </div>
            `;
        }

        html += `
            <table class="pro-table">
                <thead>
                    <tr>
                        <th>Admin Email</th>
                        <th>Authorized By</th>
                        <th>Role Badge</th>
                        <th>Date Added</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
        `;

        admins.forEach(a => {
            const badge = a.is_root
                ? '<span class="status-badge lock-enabled" style="color:#f59e0b;"><i class="fas fa-crown"></i> ROOT MASTER</span>'
                : '<span class="status-badge status-active"><i class="fas fa-user-shield"></i> SUPER ADMIN</span>';

            let deleteBtn = '<span style="color:var(--text-muted); font-size:12px;">Protected</span>';
            if (isRoot && !a.is_root) {
                deleteBtn = `<button onclick="deleteAdminEmail(${a.id})" class="row-action-btn btn-delete" title="Revoke Admin Access"><i class="fas fa-trash"></i></button>`;
            }

            html += `
                <tr>
                    <td><strong style="color:white; font-family:monospace;">${a.email}</strong></td>
                    <td><span style="color:var(--text-muted);">${a.added_by}</span></td>
                    <td>${badge}</td>
                    <td><span style="font-size:12px; color:var(--text-muted);">${a.created_at.substring(0, 10)}</span></td>
                    <td>${deleteBtn}</td>
                </tr>
            `;
        });
        html += '</tbody></table>';
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<p style="color:var(--danger); padding:15px;">Failed to load Admin Whitelist directory.</p>';
    }
}
window.loadAdminWhitelist = loadAdminWhitelist;

async function addAdminEmail() {
    const input = document.getElementById('new-admin-email-input');
    const email = input ? input.value.trim().toLowerCase() : '';
    if (!email) return showToast('Please enter a valid Gmail address', 'error');

    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
    try {
        const res = await fetch('/api/admin/whitelist', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ email })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message || 'Admin authorized successfully!', 'success');
            if (input) input.value = '';
            loadAdminWhitelist();
        } else {
            showToast(data.detail || 'Failed to authorize admin.', 'error');
        }
    } catch (e) {
        showToast('Error authorizing new admin email.', 'error');
    }
}
window.addAdminEmail = addAdminEmail;

async function deleteAdminEmail(adminId) {
    if (!confirm("Are you sure you want to revoke Admin authorization for this email?")) return;
    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
    try {
        const res = await fetch(`/api/admin/whitelist/${adminId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await res.json();
        if (res.ok) {
            showToast('Admin authorization revoked.', 'info');
            loadAdminWhitelist();
        } else {
            showToast(data.detail || 'Failed to revoke authorization.', 'error');
        }
    } catch (e) {
        showToast('Error revoking admin authorization.', 'error');
    }
}
window.deleteAdminEmail = deleteAdminEmail;

async function submitCreatorNameOnboarding() {
    const input = document.getElementById('onboarding-full-name-input');
    const name = input ? input.value.trim() : '';
    if (!name) return showToast('Please enter your Name / Alias', 'error');

    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
    if (!token) return logout();

    try {
        const res = await fetch('/api/creator/profile', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ full_name: name })
        });

        if (res.ok) {
            window.currentUserName = name;
            localStorage.setItem('creator_full_name', name);
            showToast('Account setup complete!', 'success');
            const modal = document.getElementById('creator-name-modal');
            if (modal) modal.style.display = 'none';
            showDashboard();
        } else {
            const data = await res.json();
            showToast(data.detail || 'Failed to save name', 'error');
        }
    } catch (e) {
        showToast('Error saving creator name', 'error');
    }
}
window.submitCreatorNameOnboarding = submitCreatorNameOnboarding;

async function loadAdminCreators() {
    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
    const container = document.getElementById('admin-creators-table-container');
    if (!container) return;

    try {
        const res = await fetch('/api/admin/creators-dir', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) throw new Error();
        const creators = await res.json();

        let html = `
            <table class="pro-table">
                <thead>
                    <tr>
                        <th>Creator Email</th>
                        <th>Name</th>
                        <th>Active Apps</th>
                        <th>Status</th>
                        <th>Registered Date</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
        `;

        creators.forEach(c => {
            const isBanned = c.status === 'banned';
            const statusBadge = isBanned 
                ? '<span class="status-badge status-banned" style="background:rgba(244,63,94,0.15); color:#f43f5e; border:1px solid rgba(244,63,94,0.3);"><i class="fas fa-ban"></i> Banned</span>' 
                : '<span class="status-badge status-active" style="background:rgba(16,185,129,0.15); color:#10b981; border:1px solid rgba(16,185,129,0.3);"><i class="fas fa-check-circle"></i> Active</span>';

            const actions = `
                <div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
                    <button onclick="viewCreatorHostedApps(${c.id}, '${c.email}')" class="glow-btn btn-secondary btn-small" style="padding:6px 12px; font-size:12px; background:rgba(56,189,248,0.15); border:1px solid rgba(56,189,248,0.4); color:#38bdf8;" title="Check Hosted Applications & Keys">
                        <i class="fas fa-cubes"></i> Check Hosted Apps (${c.app_count})
                    </button>
                    <button onclick="adminToggleCreatorBan(${c.id})" class="glow-btn ${isBanned ? 'btn-success' : 'btn-danger'} btn-small" style="padding:6px 10px; font-size:12px;" title="${isBanned ? 'Unban Email' : 'Ban Email'}">
                        <i class="fas ${isBanned ? 'fa-user-check' : 'fa-user-slash'}"></i> ${isBanned ? 'Unban' : 'Ban'}
                    </button>
                    <button onclick="adminDeleteCreator(${c.id})" class="glow-btn btn-danger btn-small" style="padding:6px 10px; font-size:12px;" title="Delete Gmail & All Data">
                        <i class="fas fa-trash-can"></i> Delete
                    </button>
                </div>
            `;

            html += `
                <tr>
                    <td><span style="color:var(--primary); font-family:monospace; font-weight:600;">${c.email}</span></td>
                    <td><strong style="color:white;">${c.full_name || 'Creator Account'}</strong></td>
                    <td><span class="status-badge" style="background:rgba(255,255,255,0.06); color:white; border:1px solid var(--glass-border);">${c.app_count} Apps</span></td>
                    <td>${statusBadge}</td>
                    <td><span style="font-size:12px; color:var(--text-muted);">${c.created_at.substring(0, 10)}</span></td>
                    <td>${actions}</td>
                </tr>
            `;
        });
        html += '</tbody></table>';
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<p style="color:var(--danger); padding:15px;">Failed to load Creators Directory.</p>';
    }
}
window.loadAdminCreators = loadAdminCreators;

let currentHostedCreatorData = null;

async function viewCreatorHostedApps(creatorId, creatorEmail) {
    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
    const modal = document.getElementById('creator-hosted-apps-modal');
    const content = document.getElementById('creator-hosted-apps-content');
    const emailLabel = document.getElementById('hosted-apps-creator-email-label');

    if (!modal || !content) return;

    if (emailLabel) emailLabel.innerText = `Creator Email: ${creatorEmail}`;
    content.innerHTML = '<div style="text-align:center; padding:40px;"><i class="fas fa-circle-notch fa-spin" style="font-size:32px; color:var(--primary);"></i><p style="margin-top:12px; color:var(--text-muted);">Fetching hosted applications...</p></div>';
    modal.style.display = 'flex';

    try {
        const res = await fetch(`/api/admin/creators/${creatorId}/hosted-apps`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) throw new Error();
        currentHostedCreatorData = await res.json();

        if (!currentHostedCreatorData.apps || currentHostedCreatorData.apps.length === 0) {
            document.getElementById('breadcrumb-links').innerHTML = '<span style="color:white;"><i class="fas fa-cubes"></i> Apps</span>';
            content.innerHTML = `<div style="text-align:center; padding:40px; color:var(--text-muted);"><i class="fas fa-box-open" style="font-size:36px; margin-bottom:10px;"></i><p>This creator has not hosted any applications yet.</p></div>`;
            return;
        }

        renderHostedAppsLevel1();
    } catch (e) {
        content.innerHTML = '<p style="color:var(--danger); padding:20px;">Failed to load creator hosted applications.</p>';
    }
}
window.viewCreatorHostedApps = viewCreatorHostedApps;

// LEVEL 1: Apps Overview Grid
function renderHostedAppsLevel1() {
    if (!currentHostedCreatorData || !currentHostedCreatorData.apps) return;

    const breadcrumb = document.getElementById('breadcrumb-links');
    if (breadcrumb) {
        breadcrumb.innerHTML = `
            <span style="color:#38bdf8; font-weight:700; cursor:pointer;" onclick="renderHostedAppsLevel1()"><i class="fas fa-cubes"></i> Applications (${currentHostedCreatorData.apps.length})</span>
        `;
    }

    const content = document.getElementById('creator-hosted-apps-content');
    if (!content) return;

    let html = `
        <p class="text-muted" style="font-size:13px; margin-bottom:18px;">Click on any application below to inspect its User Accounts or License Keys:</p>
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:16px;">
    `;

    currentHostedCreatorData.apps.forEach(app => {
        const userCount = app.users ? app.users.length : 0;
        const licenseCount = app.licenses ? app.licenses.length : 0;

        html += `
            <div class="glass-panel" style="background:rgba(255,255,255,0.03); border:1px solid var(--glass-border); border-radius:16px; padding:22px; transition:all 0.2s ease;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                    <h3 style="margin:0; font-size:18px; color:white; font-family:'Outfit', sans-serif;"><i class="fas fa-cube" style="color:var(--primary); margin-right:8px;"></i> ${app.app_name}</h3>
                    <span class="status-badge ${app.status === 'active' ? 'status-active' : 'status-banned'}">${app.status.toUpperCase()}</span>
                </div>

                <div style="background:rgba(0,0,0,0.3); padding:10px; border-radius:8px; font-size:11.5px; font-family:monospace; margin-bottom:15px;">
                    <div style="margin-bottom:4px;"><strong style="color:var(--text-muted);">Owner ID:</strong> <span style="color:#38bdf8;">${app.owner_id}</span></div>
                    <div><strong style="color:var(--text-muted);">Version:</strong> <span style="color:white;">v${app.version}</span></div>
                </div>

                <div style="display:flex; gap:10px; margin-bottom:16px;">
                    <div style="flex:1; background:rgba(56,189,248,0.1); border:1px solid rgba(56,189,248,0.2); border-radius:8px; padding:8px; text-align:center;">
                        <span style="font-size:11px; color:#38bdf8; display:block;"><i class="fas fa-users"></i> Users</span>
                        <strong style="font-size:15px; color:white;">${userCount}</strong>
                    </div>
                    <div style="flex:1; background:rgba(16,185,129,0.1); border:1px solid rgba(16,185,129,0.2); border-radius:8px; padding:8px; text-align:center;">
                        <span style="font-size:11px; color:#10b981; display:block;"><i class="fas fa-key"></i> Licenses</span>
                        <strong style="font-size:15px; color:white;">${licenseCount}</strong>
                    </div>
                </div>

                <button onclick="renderHostedAppsLevel2(${app.id})" class="glow-btn btn-primary btn-small" style="width:100%; padding:10px; font-weight:700; font-size:13px;">
                    <i class="fas fa-arrow-right-to-bracket"></i> Select Application (${app.app_name})
                </button>
            </div>
        `;
    });

    html += '</div>';
    content.innerHTML = html;
}
window.renderHostedAppsLevel1 = renderHostedAppsLevel1;

// LEVEL 2: Application Option Selection (Users vs Licenses)
function renderHostedAppsLevel2(appId) {
    if (!currentHostedCreatorData || !currentHostedCreatorData.apps) return;
    const app = currentHostedCreatorData.apps.find(a => a.id === appId);
    if (!app) return;

    const breadcrumb = document.getElementById('breadcrumb-links');
    if (breadcrumb) {
        breadcrumb.innerHTML = `
            <span style="color:var(--text-muted); cursor:pointer;" onclick="renderHostedAppsLevel1()"><i class="fas fa-cubes"></i> Apps</span>
            <span style="color:var(--text-muted);">&gt;</span>
            <span style="color:#38bdf8; font-weight:700; cursor:pointer;" onclick="renderHostedAppsLevel2(${app.id})"><i class="fas fa-cube"></i> ${app.app_name}</span>
        `;
    }

    const content = document.getElementById('creator-hosted-apps-content');
    if (!content) return;

    const userCount = app.users ? app.users.length : 0;
    const licenseCount = app.licenses ? app.licenses.length : 0;

    let html = `
        <div style="background:rgba(255,255,255,0.02); border:1px solid var(--glass-border); border-radius:16px; padding:20px; margin-bottom:20px;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:12px;">
                <h3 style="margin:0; font-size:20px; color:white; font-family:'Outfit', sans-serif;"><i class="fas fa-cube" style="color:var(--primary); margin-right:8px;"></i> ${app.app_name}</h3>
                <div style="display:flex; gap:8px;">
                    <span class="status-badge ${app.status === 'active' ? 'status-active' : 'status-banned'}">${app.status.toUpperCase()}</span>
                    <span class="status-badge" style="background:rgba(255,255,255,0.08); color:white;">v${app.version}</span>
                </div>
            </div>
            <div style="background:rgba(0,0,0,0.3); padding:12px; border-radius:8px; font-size:12px; font-family:monospace; display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap:10px;">
                <div><strong style="color:var(--text-muted);">Owner ID:</strong> <span style="color:#38bdf8;">${app.owner_id}</span></div>
                <div><strong style="color:var(--text-muted);">Secret Key:</strong> <span style="color:#f43f5e;">${app.secret}</span></div>
            </div>
        </div>

        <p class="text-muted" style="font-size:13.5px; margin-bottom:15px;">Choose what data you would like to inspect for <strong>${app.app_name}</strong>:</p>

        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:20px;">
            <!-- Option 1: Users -->
            <div class="glass-panel text-center" style="background:rgba(56,189,248,0.04); border:1px solid rgba(56,189,248,0.3); border-radius:18px; padding:30px;">
                <div style="width:60px; height:60px; border-radius:50%; background:rgba(56,189,248,0.15); color:#38bdf8; display:flex; align-items:center; justify-content:center; font-size:26px; margin:0 auto 15px auto;">
                    <i class="fas fa-users-line"></i>
                </div>
                <h3 style="color:white; font-size:20px; font-family:'Outfit', sans-serif; margin-bottom:6px;">User Accounts</h3>
                <p class="text-muted" style="font-size:13px; margin-bottom:15px;">Registered software client user credentials and HWID lock status.</p>
                <span class="status-badge" style="background:rgba(56,189,248,0.2); color:#38bdf8; font-size:13px; padding:6px 14px; display:inline-block; margin-bottom:20px;">
                    <i class="fas fa-users"></i> ${userCount} Users Registered
                </span>
                <br>
                <button onclick="renderHostedAppsLevel3(${app.id}, 'users')" class="glow-btn btn-primary" style="width:100%; padding:12px; font-size:14px; font-weight:700;">
                    <i class="fas fa-eye"></i> View Registered Users
                </button>
            </div>

            <!-- Option 2: Licenses -->
            <div class="glass-panel text-center" style="background:rgba(16,185,129,0.04); border:1px solid rgba(16,185,129,0.3); border-radius:18px; padding:30px;">
                <div style="width:60px; height:60px; border-radius:50%; background:rgba(16,185,129,0.15); color:#10b981; display:flex; align-items:center; justify-content:center; font-size:26px; margin:0 auto 15px auto;">
                    <i class="fas fa-key"></i>
                </div>
                <h3 style="color:white; font-size:20px; font-family:'Outfit', sans-serif; margin-bottom:6px;">License Keys</h3>
                <p class="text-muted" style="font-size:13px; margin-bottom:15px;">Issued single-use or multi-use license activation keys.</p>
                <span class="status-badge" style="background:rgba(16,185,129,0.2); color:#10b981; font-size:13px; padding:6px 14px; display:inline-block; margin-bottom:20px;">
                    <i class="fas fa-key"></i> ${licenseCount} Licenses Generated
                </span>
                <br>
                <button onclick="renderHostedAppsLevel3(${app.id}, 'licenses')" class="glow-btn btn-success" style="width:100%; padding:12px; font-size:14px; font-weight:700;">
                    <i class="fas fa-eye"></i> View Issued Licenses
                </button>
            </div>
        </div>
    `;

    content.innerHTML = html;
}
window.renderHostedAppsLevel2 = renderHostedAppsLevel2;

// LEVEL 3: Tables View (User Accounts or License Keys)
function renderHostedAppsLevel3(appId, type) {
    if (!currentHostedCreatorData || !currentHostedCreatorData.apps) return;
    const app = currentHostedCreatorData.apps.find(a => a.id === appId);
    if (!app) return;

    const isUsers = type === 'users';
    const breadcrumb = document.getElementById('breadcrumb-links');
    if (breadcrumb) {
        breadcrumb.innerHTML = `
            <span style="color:var(--text-muted); cursor:pointer;" onclick="renderHostedAppsLevel1()"><i class="fas fa-cubes"></i> Apps</span>
            <span style="color:var(--text-muted);">&gt;</span>
            <span style="color:var(--text-muted); cursor:pointer;" onclick="renderHostedAppsLevel2(${app.id})"><i class="fas fa-cube"></i> ${app.app_name}</span>
            <span style="color:var(--text-muted);">&gt;</span>
            <span style="color:${isUsers ? '#38bdf8' : '#10b981'}; font-weight:700;"><i class="fas ${isUsers ? 'fa-users-line' : 'fa-key'}"></i> ${isUsers ? 'User Accounts' : 'License Keys'}</span>
        `;
    }

    const content = document.getElementById('creator-hosted-apps-content');
    if (!content) return;

    let tableHtml = '';
    if (isUsers) {
        if (app.users && app.users.length > 0) {
            tableHtml = `
                <table class="pro-table" style="font-size:12.5px;">
                    <thead>
                        <tr>
                            <th>Username</th>
                            <th>HWID Lock</th>
                            <th>Last IP</th>
                            <th>Status</th>
                            <th>Expires At</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${app.users.map(u => `
                            <tr>
                                <td><strong style="color:white;">${u.username}</strong></td>
                                <td><span style="font-family:monospace; color:${u.hwid ? '#a78bfa' : 'var(--text-muted)'};">${u.hwid || 'None'}</span></td>
                                <td><span style="font-family:monospace;">${u.last_ip || 'N/A'}</span></td>
                                <td><span class="status-badge ${u.status === 'banned' ? 'status-banned' : 'status-active'}">${u.status}</span></td>
                                <td><span>${u.expires_at ? u.expires_at.substring(0,10) : 'Lifetime'}</span></td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        } else {
            tableHtml = `<div style="text-align:center; padding:35px; color:var(--text-muted);"><i class="fas fa-users-slash" style="font-size:32px; margin-bottom:10px;"></i><p>No registered User Accounts in this application.</p></div>`;
        }
    } else {
        if (app.licenses && app.licenses.length > 0) {
            tableHtml = `
                <table class="pro-table" style="font-size:12.5px;">
                    <thead>
                        <tr>
                            <th>License Key</th>
                            <th>HWID Lock</th>
                            <th>Last IP</th>
                            <th>Status</th>
                            <th>Duration / Expiry</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${app.licenses.map(l => `
                            <tr>
                                <td><strong style="color:#10b981; font-family:monospace;">${l.license_key}</strong></td>
                                <td><span style="font-family:monospace; color:${l.hwid ? '#a78bfa' : 'var(--text-muted)'};">${l.hwid || 'None'}</span></td>
                                <td><span style="font-family:monospace;">${l.last_ip || 'N/A'}</span></td>
                                <td><span class="status-badge ${l.status === 'banned' ? 'status-banned' : 'status-active'}">${l.status}</span></td>
                                <td><span>${l.duration_days > 0 ? l.duration_days + ' Days' : (l.expires_at ? l.expires_at.substring(0,10) : 'Lifetime')}</span></td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        } else {
            tableHtml = `<div style="text-align:center; padding:35px; color:var(--text-muted);"><i class="fas fa-key" style="font-size:32px; margin-bottom:10px;"></i><p>No License Keys generated in this application.</p></div>`;
        }
    }

    let html = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px; flex-wrap:wrap; gap:10px;">
            <button onclick="renderHostedAppsLevel2(${app.id})" class="glow-btn btn-cancel btn-small" style="padding:7px 14px; font-size:12px;">
                <i class="fas fa-arrow-left"></i> Back to ${app.app_name}
            </button>
            <span style="font-size:13px; color:white; font-weight:600;">
                App: <strong style="color:#38bdf8;">${app.app_name}</strong>
            </span>
        </div>
        ${tableHtml}
    `;

    content.innerHTML = html;
}
window.renderHostedAppsLevel3 = renderHostedAppsLevel3;

function closeCreatorHostedAppsModal() {
    const modal = document.getElementById('creator-hosted-apps-modal');
    if (modal) modal.style.display = 'none';
}
window.closeCreatorHostedAppsModal = closeCreatorHostedAppsModal;

async function adminToggleCreatorBan(creatorId) {
    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
    try {
        const res = await fetch(`/api/admin/creators/${creatorId}/toggle-ban`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message || 'Creator status updated!', 'success');
            loadAdminCreators();
        } else {
            showToast(data.detail || 'Failed to toggle ban status', 'error');
        }
    } catch (e) {
        showToast('Error toggling creator ban status', 'error');
    }
}
window.adminToggleCreatorBan = adminToggleCreatorBan;

async function adminDeleteCreator(creatorId) {
    if (!confirm('Are you sure you want to permanently delete this Creator account and all its settings?')) return;
    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
    try {
        const res = await fetch(`/api/admin/creators/${creatorId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await res.json();
        if (res.ok) {
            showToast('Creator deleted successfully!', 'info');
            loadAdminCreators();
        } else {
            showToast(data.detail || 'Failed to delete creator', 'error');
        }
    } catch (e) {
        showToast('Error deleting creator account', 'error');
    }
}
window.adminDeleteCreator = adminDeleteCreator;

async function loadAdminResellers() {
    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
    const container = document.getElementById('admin-resellers-table-container');
    if (!container) return;

    try {
        const res = await fetch('/api/admin/resellers-dir', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) throw new Error();
        const resellers = await res.json();

        let html = `
            <table class="pro-table">
                <thead>
                    <tr>
                        <th>Reseller Username</th>
                        <th>Belongs to Creator</th>
                        <th>Created Date</th>
                    </tr>
                </thead>
                <tbody>
        `;

        resellers.forEach(r => {
            html += `
                <tr>
                    <td><strong style="color:white; font-family:monospace;">${r.username}</strong></td>
                    <td><span style="color:var(--primary);">${r.creator_email}</span></td>
                    <td><span style="font-size:12px; color:var(--text-muted);">${r.created_at ? r.created_at.substring(0, 10) : 'N/A'}</span></td>
                </tr>
            `;
        });
        html += '</tbody></table>';
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<p style="color:var(--danger); padding:15px;">Failed to load Resellers Directory.</p>';
    }
}
window.loadAdminResellers = loadAdminResellers;

async function loadAdminEndUsers() {
    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
    const container = document.getElementById('admin-endusers-table-container');
    if (!container) return;

    try {
        const res = await fetch('/api/admin/end-users-dir', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) throw new Error();
        const users = await res.json();

        if (users.length === 0) {
            container.innerHTML = '<p class="text-muted" style="padding:15px;">No End-Users currently registered in database.</p>';
            return;
        }

        let html = `
            <table class="pro-table">
                <thead>
                    <tr>
                        <th>Application</th>
                        <th>Username</th>
                        <th>HWID Status</th>
                        <th>Last IP</th>
                        <th>Status</th>
                        <th>Expires At</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
        `;

        users.forEach(u => {
            const hwidBadge = u.hwid ? `<span class="status-badge status-active" title="${u.hwid}"><i class="fas fa-lock"></i> Locked</span>` : '<span class="status-badge lock-disabled"><i class="fas fa-unlock"></i> None</span>';
            const statusBadge = u.status === 'banned' ? '<span class="status-badge status-banned"><i class="fas fa-ban"></i> Banned</span>' : '<span class="status-badge status-active"><i class="fas fa-check-circle"></i> Active</span>';
            
            html += `
                <tr>
                    <td><span class="status-badge" style="background:rgba(139,92,246,0.15); color:#a78bfa; font-weight:600;"><i class="fas fa-cube" style="margin-right:4px;"></i>${u.app_name}</span></td>
                    <td><strong style="color:white;">${u.username}</strong></td>
                    <td>${hwidBadge}</td>
                    <td><span style="font-family:monospace; font-size:12px; color:var(--text-muted);">${u.last_ip || 'N/A'}</span></td>
                    <td>${statusBadge}</td>
                    <td><span style="font-size:12px; color:var(--text-muted);">${u.expires_at ? u.expires_at.substring(0, 10) : 'Lifetime'}</span></td>
                    <td>
                        <div style="display:flex; gap:6px;">
                            <button onclick="adminResetEndUserHWID(${u.id})" class="glow-btn btn-secondary btn-small" title="Reset HWID"><i class="fas fa-arrows-rotate"></i></button>
                            <button onclick="adminToggleEndUserBan(${u.id})" class="glow-btn ${u.status === 'banned' ? 'btn-success' : 'btn-danger'} btn-small" title="Toggle Ban"><i class="fas ${u.status === 'banned' ? 'fa-user-check' : 'fa-user-slash'}"></i></button>
                            <button onclick="adminDeleteEndUser(${u.id})" class="glow-btn btn-danger btn-small" title="Delete User"><i class="fas fa-trash-can"></i></button>
                        </div>
                    </td>
                </tr>
            `;
        });
        html += '</tbody></table>';
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<p style="color:var(--danger); padding:15px;">Failed to load End-Users Directory.</p>';
    }
}
window.loadAdminEndUsers = loadAdminEndUsers;

async function adminResetEndUserHWID(userId) {
    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
    try {
        const res = await fetch(`/api/admin/end-users/${userId}/reset-hwid`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message || 'HWID Reset successful!', 'success');
            loadAdminEndUsers();
        } else {
            showToast(data.detail || 'Failed to reset HWID', 'error');
        }
    } catch (e) {
        showToast('Error resetting HWID', 'error');
    }
}
window.adminResetEndUserHWID = adminResetEndUserHWID;

async function adminToggleEndUserBan(userId) {
    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
    try {
        const res = await fetch(`/api/admin/end-users/${userId}/toggle-ban`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message || 'User status updated!', 'success');
            loadAdminEndUsers();
        } else {
            showToast(data.detail || 'Failed to toggle ban status', 'error');
        }
    } catch (e) {
        showToast('Error toggling ban status', 'error');
    }
}
window.adminToggleEndUserBan = adminToggleEndUserBan;

async function adminDeleteEndUser(userId) {
    if (!confirm('Are you sure you want to permanently delete this End-User account?')) return;
    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
    try {
        const res = await fetch(`/api/admin/end-users/${userId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await res.json();
        if (res.ok) {
            showToast('End-User deleted successfully!', 'info');
            loadAdminEndUsers();
        } else {
            showToast(data.detail || 'Failed to delete End-User', 'error');
        }
    } catch (e) {
        showToast('Error deleting End-User', 'error');
    }
}
window.adminDeleteEndUser = adminDeleteEndUser;

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
        list.innerHTML = '';

        // Update Custom Dropdown and hidden select
        populateCustomDropdown(apps);

        // Update Dashboard Stats
        document.getElementById('stat-apps').innerText = apps.length;

        let totalUsers = 0;
        let totalLicenses = 0;

        apps.forEach(app => {
            totalUsers += app.user_count || 0;
            totalLicenses += app.license_count || 0;
        });

        document.getElementById('stat-users').innerText = totalUsers;
        document.getElementById('stat-licenses').innerText = totalLicenses;

        // Update the central growth chart on the Home tab
        updateGrowthChart(totalUsers, totalLicenses);

        const isReseller = localStorage.getItem('user_role') === 'reseller';
        apps.forEach(app => {
            // App Tab Card
            const div = document.createElement('div');
            div.className = 'app-card';

            const deleteBtnHtml = isReseller ? '' : `<button onclick="deleteApp(event, ${app.id})" style="width:auto; padding:8px 12px; height:auto; background:rgba(239, 68, 68, 0.15); color:#ef4444; border:1px solid rgba(239,68,68,0.3); border-radius:8px; box-shadow:none;"><i class="fas fa-trash"></i></button>`;
            const copyOwnerHtml = app.owner_id === '********' ? '' : `<button class="copy-field-btn" onclick="copyText('${app.owner_id}')" title="Copy Owner ID"><i class="far fa-copy"></i></button>`;
            const copySecretHtml = app.secret === '********' ? '' : `<button class="copy-field-btn" onclick="copyText('${app.secret}')" title="Copy Secret"><i class="far fa-copy"></i></button>`;

            const statusBadge = app.status === 'active'
                ? '<span class="app-badge active"><i class="fas fa-circle-check"></i> Active</span>'
                : '<span class="app-badge maintenance"><i class="fas fa-triangle-exclamation"></i> Maintenance</span>';

            const versionHtml = `<span class="app-card-version"><i class="fas fa-code-branch"></i> v${app.version || '1.0'}</span>`;

            div.innerHTML = `
                <div class="app-card-header">
                    <div class="app-card-title-group">
                        <h3><i class="fas fa-cube" style="color:var(--primary);"></i> ${app.app_name}</h3>
                        <div class="app-card-badges">
                            ${statusBadge}
                            ${versionHtml}
                        </div>
                    </div>
                    ${deleteBtnHtml}
                </div>
                
                <div class="app-card-body">
                    <div class="app-field-container">
                        <span class="field-label">Owner ID</span>
                        <div class="app-field-box">
                            <span class="field-value">${app.owner_id}</span>
                            ${copyOwnerHtml}
                        </div>
                    </div>
                    
                    <div class="app-field-container">
                        <span class="field-label">Shared Secret Key</span>
                        <div class="app-field-box">
                            <span class="field-value">${app.secret}</span>
                            ${copySecretHtml}
                        </div>
                    </div>

                    <div class="app-card-stats-row">
                        <div class="app-stat-badge">
                            <i class="fas fa-users"></i>
                            <div>
                                <span class="stat-count">${app.user_count || 0}</span>
                                <span class="stat-lbl">Active Users</span>
                            </div>
                        </div>
                        <div class="app-stat-badge">
                            <i class="fas fa-key"></i>
                            <div>
                                <span class="stat-count">${app.license_count || 0}</span>
                                <span class="stat-lbl">Keys Issued</span>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="app-card-footer">
                    <button onclick="quickManageWorkspace(${app.id})" class="glow-btn btn-small"><i class="fas fa-briefcase"></i> Manage Workspace</button>
                    <button onclick="showTab('docs')" class="glow-btn btn-small btn-secondary"><i class="fas fa-book"></i> C# SDK Guide</button>
                </div>
            `;
            list.appendChild(div);
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
        const webhookInput = document.getElementById('settings-webhook');
        if (webhookInput) webhookInput.value = app.webhook_url || '';
        document.getElementById('settings-version').value = app.version || '1.0';
        document.getElementById('settings-dev-msg').value = app.dev_message || '';
        const downloadInput = document.getElementById('settings-download-url');
        if (downloadInput) downloadInput.value = app.download_url || '';
    }

    document.getElementById('app-workspace-content').style.display = 'block';

    const isReseller = localStorage.getItem('user_role') === 'reseller';
    if (isReseller) {
        const perms = JSON.parse(localStorage.getItem('reseller_perms') || '{}');
        document.getElementById('btn-tab-users').style.display = perms.can_manage_users ? 'block' : 'none';
        document.getElementById('btn-tab-licenses').style.display = perms.can_manage_licenses ? 'block' : 'none';
        document.getElementById('btn-tab-logs').style.display = perms.can_view_logs ? 'block' : 'none';
        document.getElementById('btn-tab-settings').style.display = perms.can_modify_app_settings ? 'block' : 'none';

        let targetTab = null;
        if (perms.can_manage_users) targetTab = 'users';
        else if (perms.can_manage_licenses) targetTab = 'licenses';
        else if (perms.can_view_logs) targetTab = 'logs';
        else if (perms.can_modify_app_settings) targetTab = 'settings';

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
        let html = '<table class="pro-table" id="user-table"><tr><th>User</th><th>Last IP</th><th>HWID</th><th>Status</th><th>HWID Lock</th><th>Expires At</th><th>Actions</th></tr>';
        users.forEach(u => {
            let statusBadge = u.status === 'banned'
                ? '<span class="status-badge status-banned"><i class="fas fa-user-slash"></i> BANNED</span>'
                : '<span class="status-badge status-active"><i class="fas fa-user-check"></i> UNBANNED</span>';
            let lockBadge = u.hwid_lock
                ? '<span class="lock-badge lock-enabled"><i class="fas fa-lock"></i> LOCKED</span>'
                : '<span class="lock-badge lock-disabled"><i class="fas fa-lock-open"></i> UNLOCKED</span>';
            const resetBtnHtml = canReset ? `<button class="row-action-btn btn-reset" onclick="resetUserHWID(${u.id})" title="Reset HWID"><i class="fas fa-undo"></i></button>` : '';
            html += `<tr>
                <td>${u.username} <button onclick="copyToClipboard('${u.username}')" style="background:transparent;border:none;color:var(--text-muted);cursor:pointer;padding:0;width:auto;margin:0 5px;box-shadow:none;"><i class="fas fa-copy"></i></button></td>
                <td><span style="color:var(--primary); font-family:monospace;">${u.last_ip || 'Never'}</span></td>
                <td><span style="font-family:monospace; color:var(--text-muted);">${u.hwid ? u.hwid.substring(0, 8) + '...' : 'Not Set'}</span></td>
                <td>${statusBadge}</td>
                <td>${lockBadge}</td>
                <td>${u.expires_at}</td>
                <td>
                    <div class="action-btn-cell">
                        <button class="row-action-btn btn-ban" onclick="toggleBanUser(${u.id})" title="Ban/Unban"><i class="fas fa-gavel"></i></button>
                        ${resetBtnHtml}
                        <button class="row-action-btn btn-delete" onclick="deleteUser(${u.id})" title="Delete User"><i class="fas fa-trash"></i></button>
                    </div>
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
        let html = '<table class="pro-table" id="license-table"><tr><th>Key</th><th>Last IP</th><th>Status</th><th>HWID Lock</th><th>Duration</th><th>Expires</th><th>Actions</th></tr>';
        licenses.forEach(l => {
            let statusBadge = l.status === 'banned'
                ? '<span class="status-badge status-banned"><i class="fas fa-ban"></i> BANNED</span>'
                : '<span class="status-badge status-active"><i class="fas fa-check-circle"></i> UNBANNED</span>';
            let lockBadge = l.hwid_lock
                ? '<span class="lock-badge lock-enabled"><i class="fas fa-lock"></i> LOCKED</span>'
                : '<span class="lock-badge lock-disabled"><i class="fas fa-lock-open"></i> UNLOCKED</span>';
            const resetBtnHtml = canReset ? `<button class="row-action-btn btn-reset" onclick="resetLicenseHWID(${l.id})" title="Reset HWID"><i class="fas fa-undo"></i></button>` : '';
            html += `<tr>
                <td><span style="font-family:monospace; color:var(--primary);">${l.license_key}</span> <button onclick="copyToClipboard('${l.license_key}')" style="background:transparent;border:none;color:var(--text-muted);cursor:pointer;padding:0;width:auto;margin:0 5px;box-shadow:none;"><i class="fas fa-copy"></i></button></td>
                <td><span style="font-family:monospace;">${l.last_ip || 'Never'}</span></td>
                <td>${statusBadge}</td>
                <td>${lockBadge}</td>
                <td>${l.duration_days} Days</td>
                <td>${l.expires_at}</td>
                <td>
                    <div class="action-btn-cell">
                        <button class="row-action-btn btn-ban" onclick="toggleBanLicense(${l.id})" title="Ban/Unban"><i class="fas fa-gavel"></i></button>
                        ${resetBtnHtml}
                        <button class="row-action-btn btn-delete" onclick="deleteLicense(${l.id})" title="Delete License"><i class="fas fa-trash"></i></button>
                    </div>
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
    const webhookInput = document.getElementById('settings-webhook');
    const webhook = webhookInput ? webhookInput.value : '';
    const version = document.getElementById('settings-version').value;
    const devMsg = document.getElementById('settings-dev-msg').value;
    const downloadInput = document.getElementById('settings-download-url');
    const downloadUrl = downloadInput ? downloadInput.value : '';

    try {
        const res = await fetch(`${API_URL}/apps/${currentAppId}/settings`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify({
                status: status,
                webhook_url: webhook,
                version: version,
                dev_message: devMsg,
                download_url: downloadUrl
            })
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
            const remember = document.getElementById('save-login-checkbox') && document.getElementById('save-login-checkbox').checked;
            const storage = remember ? localStorage : sessionStorage;

            // Clear leftovers
            localStorage.removeItem('token');
            localStorage.removeItem('email');
            localStorage.removeItem('user_role');
            localStorage.removeItem('reseller_perms');
            sessionStorage.removeItem('token');
            sessionStorage.removeItem('email');
            sessionStorage.removeItem('user_role');
            sessionStorage.removeItem('reseller_perms');

            storage.setItem('token', data.access_token);
            storage.setItem('user_role', 'reseller');
            storage.setItem('reseller_perms', JSON.stringify(data.permissions));
            storage.setItem('email', username);

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
            if (r.can_manage_apps) perms.push('Manage Apps');
            const permText = perms.join(', ') || 'No Permissions';

            const dateStr = new Date(r.created_at).toLocaleDateString();

            html += `
                <tr>
                    <td><strong>${r.username}</strong></td>
                    <td style="max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${appNames}</td>
                    <td style="color: var(--primary); font-size: 13px;">${permText}</td>
                    <td>${dateStr}</td>
                    <td>
                        <button class="action-btn icon-btn" onclick="editReseller(${r.id}, '${r.username}', [${r.allowed_apps.join(',')}], ${r.is_admin}, ${r.can_view_secret}, ${r.can_manage_users}, ${r.can_manage_licenses}, ${r.can_reset_hwid}, ${r.can_view_logs}, ${r.can_ban_users}, ${r.can_clean_banned}, ${r.can_modify_app_settings}, ${r.can_manage_apps})" title="Edit"><i class="fas fa-edit"></i></button>
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
        can_modify_app_settings: document.getElementById('perm-modify-app-settings').checked,
        can_manage_apps: document.getElementById('perm-manage-apps').checked
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

function editReseller(id, username, allowedApps, isAdmin, viewSecret, manageUsers, manageLicenses, resetHwid, viewLogs, banUsers, cleanBanned, modifyAppSettings, canManageApps) {
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
    document.getElementById('perm-manage-apps').checked = canManageApps;

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

async function loadHomeData() {
    const token = localStorage.getItem('token');
    if (!token) return logout();

    // 1. Fetch apps and calculate stats (this updates stats cards and growth chart)
    try {
        const res = await fetch(`${API_URL}/apps`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (res.ok) {
            const apps = await res.json();
            currentApps = apps;

            // Populate workspace selectors
            populateCustomDropdown(apps);

            // Update stats
            const statApps = document.getElementById('stat-apps');
            if (statApps) statApps.innerText = apps.length;

            let totalUsers = 0;
            let totalLicenses = 0;
            apps.forEach(app => {
                totalUsers += app.user_count || 0;
                totalLicenses += app.license_count || 0;
            });

            const statUsers = document.getElementById('stat-users');
            if (statUsers) statUsers.innerText = totalUsers;

            const statLicenses = document.getElementById('stat-licenses');
            if (statLicenses) statLicenses.innerText = totalLicenses;

            // Render growth chart on Home overview tab
            updateGrowthChart(totalUsers, totalLicenses);
        }
    } catch (e) {
        console.error('Failed to load apps overview in home data', e);
    }

    // 2. Fetch global unified logs
    try {
        const logList = document.getElementById('global-log-list');
        if (logList) {
            const res = await fetch('/api/creator/global-logs', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
                const logs = await res.json();
                logList.innerHTML = '';
                if (logs.length === 0) {
                    logList.innerHTML = '<span class="terminal-placeholder">Awaiting log activities from API client stream...</span>';
                    return;
                }

                logs.forEach(log => {
                    const line = document.createElement('div');
                    line.className = 'terminal-line';
                    line.style.margin = '4px 0';
                    line.style.fontSize = '12px';
                    line.style.lineHeight = '1.4';

                    // Color tags based on action type
                    let actionColor = 'var(--primary)';
                    if (log.action.includes('SUCCESS')) actionColor = '#10b981'; // success emerald
                    else if (log.action.includes('FAILED') || log.action.includes('FAIL') || log.action.includes('BAN')) actionColor = '#ef4444'; // danger red
                    else if (log.action.includes('RESET')) actionColor = '#f59e0b'; // warning amber

                    const logDate = new Date(log.created_at);
                    const time = logDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

                    line.innerHTML = `
                        <span class="terminal-timestamp" style="color:var(--text-muted); margin-right:4px;">[${time}]</span>
                        <span class="terminal-app" style="color:#a78bfa; font-weight:600; margin-right:4px;">[${log.app_name}]</span>
                        <span class="terminal-action" style="color:${actionColor}; font-weight:bold; margin-right:6px;">${log.action}</span>
                        <span class="terminal-desc" style="color:#e2e8f0;">${log.description}</span>
                    `;
                    logList.appendChild(line);
                });
            } else {
                logList.innerHTML = '<span class="terminal-placeholder" style="color:#ef4444;">Error loading activity logs.</span>';
            }
        }
    } catch (e) {
        console.error('Failed to load global logs', e);
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

async function saveProfileDetails() {
    const fullName = document.getElementById('profile-full-name').value.trim();
    const password = document.getElementById('profile-password').value;

    const token = localStorage.getItem('token');
    if (!token) return logout();

    const payload = {};
    if (fullName) payload.full_name = fullName;
    if (password) payload.password = password;

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
            document.getElementById('profile-password').value = '';
        } else {
            const data = await res.json();
            showToast(data.detail || 'Failed to update profile', 'error');
        }
    } catch (e) {
        showToast('Error updating profile details', 'error');
    }
}

function populateCustomDropdown(apps) {
    const nativeSelector = document.getElementById('app-selector');
    if (nativeSelector) {
        nativeSelector.innerHTML = '<option value="">-- Choose Application --</option>';
        apps.forEach(app => {
            const opt = document.createElement('option');
            opt.value = app.id;
            opt.text = app.app_name;
            nativeSelector.appendChild(opt);
        });
    }

    const customOptions = document.getElementById('custom-app-selector-options');
    if (customOptions) {
        customOptions.innerHTML = '';

        // Add default option
        const defOpt = document.createElement('div');
        defOpt.className = 'custom-dropdown-option';
        defOpt.innerText = '-- Choose Application --';
        defOpt.onclick = () => selectCustomApp("", "-- Choose Application --");
        customOptions.appendChild(defOpt);

        apps.forEach(app => {
            const optDiv = document.createElement('div');
            optDiv.className = 'custom-dropdown-option';
            optDiv.innerHTML = `<i class="fas fa-cube" style="color:var(--primary); margin-right:8px;"></i>${app.app_name}`;
            optDiv.onclick = () => selectCustomApp(app.id, app.app_name);
            customOptions.appendChild(optDiv);
        });
    }
}

function selectCustomApp(appId, appName) {
    const nativeSelector = document.getElementById('app-selector');
    if (nativeSelector) {
        nativeSelector.value = appId;
        nativeSelector.dispatchEvent(new Event('change'));
    }

    const triggerText = document.getElementById('custom-app-selector-trigger-text');
    if (triggerText) {
        triggerText.innerHTML = appId ? `<i class="fas fa-cube" style="color:var(--primary); margin-right:8px;"></i>${appName}` : appName;
    }

    const container = document.getElementById('custom-app-selector-container');
    if (container) {
        container.classList.remove('open');
    }
}

function quickManageWorkspace(appId) {
    const app = currentApps.find(a => a.id == appId);
    if (app) {
        showTab('workspace');
        selectCustomApp(appId, app.app_name);
    }
}

// Switch Developer Docs Language Tab
function switchDocLanguage(lang) {
    // Hide all language content containers
    document.querySelectorAll('.doc-lang-content').forEach(el => el.style.display = 'none');

    // Remove active class from language selector buttons
    document.querySelectorAll('.doc-lang-btn').forEach(btn => btn.classList.remove('active'));

    // Show selected container
    const activeContent = document.getElementById(`doc-content-${lang}`);
    if (activeContent) activeContent.style.display = 'block';

    // Set active button state
    const activeBtn = document.getElementById(`doc-btn-${lang}`);
    if (activeBtn) activeBtn.classList.add('active');
}
window.switchDocLanguage = switchDocLanguage;

// Initialize custom select click triggers & auto-login persistent state check
document.addEventListener('DOMContentLoaded', () => {
    // Check if token exists to automatically restore session
    const savedToken = localStorage.getItem('token') || sessionStorage.getItem('token');
    if (savedToken) {
        showDashboard();
    }

    setTimeout(() => {
        const trigger = document.getElementById('custom-app-selector-trigger');
        const container = document.getElementById('custom-app-selector-container');

        if (trigger && container) {
            trigger.onclick = (e) => {
                e.stopPropagation();
                container.classList.toggle('open');
            };
        }

        document.addEventListener('click', (e) => {
            if (container && !container.contains(e.target)) {
                container.classList.remove('open');
            }
        });
    }, 500);
});

function clearAITabChat() {
    const msgContainer = document.getElementById('ai-chat-messages');
    if (msgContainer) {
        msgContainer.innerHTML = `
            <div class="ai-msg bot">
                <div class="ai-msg-sender-label" style="color: #a78bfa !important;"><i class="fas fa-brain" style="color: #a78bfa !important;"></i> LegitAuth</div>
                <div class="ai-msg-bubble">
                    👋 Welcome to <strong>LegitAuth AI Assistant</strong>! <br>
                    I can assist you with platform configuration, SDK integrations (C#, C++, Python), account management, and error troubleshooting. <br>
                    <em>How can I help you today?</em>
                </div>
            </div>
        `;
    }
}
window.clearAITabChat = clearAITabChat;

async function sendUserAIMessage() {
    const input = document.getElementById('ai-chat-input');
    const msgContainer = document.getElementById('ai-chat-messages');
    const langSelect = document.getElementById('ai-language-select');
    if (!input || !msgContainer) return;

    const userText = input.value.trim();
    if (!userText) return;

    const selectedLang = langSelect ? langSelect.value : 'Hinglish';

    // Append User Message with registered user name label in RED
    const displayName = window.currentUserName || localStorage.getItem('creator_full_name') || localStorage.getItem('email') || 'You';
    const userDiv = document.createElement('div');
    userDiv.className = 'ai-msg user';
    userDiv.innerHTML = `
        <div class="ai-msg-sender-label" style="color: #ef4444 !important;"><i class="fas fa-user" style="color: #ef4444 !important;"></i> ${escapeHtml(displayName)}</div>
        <div class="ai-msg-bubble">${escapeHtml(userText)}</div>
    `;
    msgContainer.appendChild(userDiv);

    input.value = '';
    msgContainer.scrollTop = msgContainer.scrollHeight;

    // Append Bot Thinking Placeholder with "LegitAuth" label in PURPLE
    const botDiv = document.createElement('div');
    botDiv.className = 'ai-msg bot';
    botDiv.innerHTML = `
        <div class="ai-msg-sender-label" style="color: #a78bfa !important;"><i class="fas fa-brain" style="color: #a78bfa !important;"></i> LegitAuth</div>
        <div class="ai-msg-bubble"><i class="fas fa-circle-notch fa-spin"></i> Thinking...</div>
    `;
    msgContainer.appendChild(botDiv);
    msgContainer.scrollTop = msgContainer.scrollHeight;

    try {
        const res = await fetch('/api/ai/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: userText, language: selectedLang })
        });
        const data = await res.json();
        
        const replyText = (res.ok && data.reply) ? data.reply : (data.detail || 'Error connecting to LegitAuth AI.');
        botDiv.querySelector('.ai-msg-bubble').innerHTML = formatAIMarkdown(replyText);
        msgContainer.scrollTop = msgContainer.scrollHeight;
    } catch (e) {
        botDiv.querySelector('.ai-msg-bubble').innerHTML = '⚠️ Error communicating with LegitAuth AI Assistant.';
    }
}
window.sendUserAIMessage = sendUserAIMessage;

function escapeHtml(text) {
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function formatAIMarkdown(text) {
    if (!text) return '';
    let formatted = escapeHtml(text);

    // Format completed markdown code blocks ```lang ... ```
    formatted = formatted.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
        return `
            <pre><button class="ai-code-copy-btn" onclick="copyText('${escapeForJs(code)}')"><i class="fas fa-copy"></i> Copy</button><code>${code}</code></pre>
        `;
    });

    // Format unclosed code blocks if truncated
    formatted = formatted.replace(/```(\w+)?\n([\s\S]*)$/g, (match, lang, code) => {
        return `
            <pre><button class="ai-code-copy-btn" onclick="copyText('${escapeForJs(code)}')"><i class="fas fa-copy"></i> Copy</button><code>${code}</code></pre>
        `;
    });

    // Format inline code `code`
    formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Format bold **text**
    formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // Format line breaks
    formatted = formatted.replace(/\n/g, '<br>');

    return formatted;
}

function escapeForJs(str) {
    return str.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, '\\n').replace(/\r/g, '');
}


