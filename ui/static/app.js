/* CareCue Frontend - Vanilla JS with Hash-based Routing */

const API_BASE = '/api';
let currentCaregiverId = null;
let currentPatientId = null;
let caregivers = [];
let doctors = [];
let pharmacies = [];
let currentPrescriptions = [];
let editingPrescriptionId = null;

// --- View State Management ---
const VALID_VIEWS = ['dashboard', 'patients', 'medications', 'patient-meds', 'doctors', 'pharmacies'];
let medsFilterPatient = 'all';
let medsFilterStatus = 'all';
let allMedications = [];
let currentView = 'dashboard';

// Initialize view from hash on load
function initViewFromHash() {
    const hash = window.location.hash.slice(1) || 'dashboard';
    if (VALID_VIEWS.includes(hash)) {
        currentView = hash;
    } else {
        currentView = 'dashboard';
        window.location.hash = 'dashboard';
    }
}

// Navigate to a view (updates hash, sidebar, and content)
function navigateTo(view) {
    if (!VALID_VIEWS.includes(view)) return;
    
    // Update hash (triggers hashchange event)
    if (window.location.hash.slice(1) !== view) {
        window.location.hash = view;
    } else {
        // Same view, but we might need to refresh data
        activateView(view);
    }
}

// Activate a view (internal - called by hashchange or direct navigation)
function activateView(view) {
    currentView = view;
    
    // Update sidebar active state
    document.querySelectorAll('.nav-item[data-view]').forEach(item => {
        item.classList.toggle('active', item.dataset.view === view);
    });
    
    // Update view visibility
    document.querySelectorAll('.view').forEach(v => {
        v.classList.toggle('active', v.dataset.view === view);
    });
    
    // Update page title
    const titles = {
        dashboard: 'Dashboard',
        patients: 'Patients',
        medications: 'Medications',
        'patient-meds': 'Manage Medications',
        doctors: 'Doctors',
        pharmacies: 'Pharmacies'
    };
    document.getElementById('page-title').textContent = titles[view] || view;
    
    // Update add button
    updateAddButton(view);
    
    // Load view data
    if (view === 'dashboard') loadDashboard();
    else if (view === 'patients') loadPatients();
    else if (view === 'medications') loadMedications();
    else if (view === 'patient-meds') loadPatientMeds();
    else if (view === 'doctors') loadDoctors();
    else if (view === 'pharmacies') loadPharmacies();
}

// Update add button based on current view
// Single CTA per view: each legacy view owns its Add button in its
// in-view header, so the top-bar button stays hidden to avoid duplicates.
function updateAddButton(view) {
    const addBtn = document.getElementById('add-btn');
    addBtn.style.display = 'none';
    addBtn.onclick = null;
}

// Listen for hash changes
window.addEventListener('hashchange', () => {
    const hash = window.location.hash.slice(1);
    if (VALID_VIEWS.includes(hash)) {
        activateView(hash);
    }
});

// --- Loading State Utilities ---

function showLoading(containerId, message = 'Loading...') {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = `
        <div class="loading-state">
            <div class="spinner"></div>
            <div class="loading-message">${message}</div>
        </div>
    `;
}

function showErrorState(containerId, message, retryAction = null) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const retryBtn = retryAction 
        ? `<button class="btn btn-primary btn-sm" onclick="${retryAction}">Retry</button>`
        : '';
    container.innerHTML = `
        <div class="error-state">
            <div class="error-state-icon"><i data-lucide="alert-triangle"></i></div>
            <div class="error-state-title">Failed to Load</div>
            <div class="error-state-text">${message}</div>
            ${retryBtn}
        </div>
    `;
}

function showButtonLoading(buttonId, loading = true) {
    const btn = document.getElementById(buttonId);
    if (!btn) return;
    if (loading) {
        btn.disabled = true;
        btn.dataset.originalText = btn.innerHTML;
        btn.innerHTML = '<span class="spinner btn-spinner"></span> Loading...';
    } else {
        btn.disabled = false;
        btn.innerHTML = btn.dataset.originalText || btn.innerHTML;
    }
}

function setFormSubmitting(formId, submitting = true) {
    const form = document.getElementById(formId);
    if (!form) return;
    const submitBtn = form.querySelector('button[type="submit"]');
    if (!submitBtn) return;
    if (submitting) {
        submitBtn.disabled = true;
        submitBtn.dataset.originalText = submitBtn.innerHTML;
        submitBtn.innerHTML = '<span class="spinner btn-spinner"></span> Saving...';
    } else {
        submitBtn.disabled = false;
        submitBtn.innerHTML = submitBtn.dataset.originalText || submitBtn.innerHTML;
    }
}

function showFormError(formId, message) {
    const form = document.getElementById(formId);
    if (!form) return;
    let errorEl = form.querySelector('.form-error');
    if (!errorEl) {
        errorEl = document.createElement('div');
        errorEl.className = 'form-error';
        form.insertBefore(errorEl, form.firstChild);
    }
    errorEl.textContent = message;
    errorEl.style.display = 'block';
}

function clearFormError(formId) {
    const form = document.getElementById(formId);
    if (!form) return;
    const errorEl = form.querySelector('.form-error');
    if (errorEl) errorEl.style.display = 'none';
}

// --- Loading State Utilities ---

async function apiRequest(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const config = {
        headers: { 'Content-Type': 'application/json' },
        ...options
    };
    if (config.body && typeof config.body === 'object') {
        config.body = JSON.stringify(config.body);
    }
    const response = await fetch(url, config);
    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
    }
    // Handle 204 No Content and other responses without body
    if (response.status === 204 || response.headers.get('content-length') === '0') {
        return null;
    }
    return response.json();
}

function showLoading(containerId, message = 'Loading...') {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = `
        <div class="loading-state">
            <div class="spinner"></div>
            <div class="loading-message">${message}</div>
        </div>
    `;
}

function formatDate(dateStr) {
    if (!dateStr) return 'N/A';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function getStatusBadge(status, text) {
    return `<span class="badge badge-${status}">${text}</span>`;
}

function getRefillStatus(rx) {
    if (rx.is_refill_overdue) return { status: 'overdue', text: 'REFILL LATE' };
    if (rx.is_refill_due_soon) return { status: 'due-soon', text: 'REFILL DUE SOON' };
    return { status: 'ok', text: 'OK' };
}

function getAdherenceClass(adherence) {
    if (adherence >= 90) return 'good';
    if (adherence >= 70) return 'warning';
    return 'danger';
}

// Plain-language labels for conflict types
function conflictTypeLabel(type) {
    const map = {
        'duplicate_medication': 'Same medicine, different brand names',
        'duplicate_generic': 'Same medicine, different brand names',
        'therapeutic_duplication': 'Similar medicines from different doctors',
        'drug_interaction': 'These medicines may not work well together',
    };
    // Handle ARB / drug-class style keys like "arb_medications"
    if (map[type]) return map[type];
    if (type && type.includes('medication')) return 'Similar medicines from different doctors';
    return type ? type.replace(/_/g, ' ') : 'Medicine conflict';
}

// Plain-language conflict message rewriter
function plainConflictMessage(c) {
    if (!c.message) return conflictTypeLabel(c.type);
    let msg = c.message;
    // "Duplicate generic 'X' prescribed by N doctors" → plain
    msg = msg.replace(/Duplicate generic '(.+?)' prescribed by (\d+) different doctor\(s\)/i,
        "Same medicine ($1) from $2 different doctors");
    msg = msg.replace(/Duplicate medication '(.+?)' prescribed by (\d+) different doctor\(s\)/i,
        "Same medicine ($1) from $2 different doctors");
    msg = msg.replace(/Therapeutic duplication: multiple (.+?) medications from different doctors/i,
        "Similar medicines ($1) from different doctors");
    msg = msg.replace(/Therapeutic duplication: multiple (.+?) from different doctors/i,
        "Similar medicines ($1) from different doctors");
    return msg;
}

// --- Form Validation Utilities ---
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function validateEmail(email) {
    return EMAIL_REGEX.test(email);
}

function validateRequired(value) {
    return value !== null && value !== undefined && value.toString().trim() !== '';
}

function validatePositiveNumber(value) {
    const num = parseFloat(value);
    return !isNaN(num) && num > 0;
}

function validateNonNegativeNumber(value) {
    const num = parseFloat(value);
    return !isNaN(num) && num >= 0;
}

function validateDateNotFuture(dateStr) {
    if (!dateStr) return false;
    const date = new Date(dateStr);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return date <= today;
}

function showFieldError(fieldName, formId, message) {
    const form = document.getElementById(formId);
    const input = form.querySelector(`[name="${fieldName}"]`);
    const errorEl = form.querySelector(`[data-for="${fieldName}"]`);
    
    if (input) {
        input.classList.add('error');
        input.classList.remove('valid');
    }
    if (errorEl) {
        errorEl.textContent = message;
        errorEl.classList.add('visible');
    }
}

function clearFieldError(fieldName, formId) {
    const form = document.getElementById(formId);
    const input = form.querySelector(`[name="${fieldName}"]`);
    const errorEl = form.querySelector(`[data-for="${fieldName}"]`);
    
    if (input) {
        input.classList.remove('error');
    }
    if (errorEl) {
        errorEl.textContent = '';
        errorEl.classList.remove('visible');
    }
}

function clearAllErrors(formId) {
    const form = document.getElementById(formId);
    form.querySelectorAll('.error-message').forEach(el => {
        el.textContent = '';
        el.classList.remove('visible');
    });
    form.querySelectorAll('input, select, textarea').forEach(el => {
        el.classList.remove('error', 'valid');
    });
}

function validateField(fieldName, formId, rules) {
    const form = document.getElementById(formId);
    const input = form.querySelector(`[name="${fieldName}"]`);
    const value = input ? input.value : '';
    
    for (const rule of rules) {
        if (!rule.validator(value)) {
            showFieldError(fieldName, formId, rule.message);
            return false;
        }
    }
    clearFieldError(fieldName, formId);
    if (input) input.classList.add('valid');
    return true;
}

function validateForm(formId, validationRules) {
    clearAllErrors(formId);
    let isValid = true;
    
    for (const [fieldName, rules] of Object.entries(validationRules)) {
        if (!validateField(fieldName, formId, rules)) {
            isValid = false;
        }
    }
    
    return isValid;
}

// --- Toast Notifications ---
function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span>${message}</span>
        <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
    `;
    container.appendChild(toast);
    
    if (duration > 0) {
        setTimeout(() => {
            toast.style.animation = 'slideIn 0.3s ease reverse';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }
}

function showSuccess(message) {
    showToast(message, 'success');
}

function showError(message) {
    showToast(message, 'error');
}

function showInfo(message) {
    showToast(message, 'info');
}

// --- DELETE Operations ---

async function deleteWithConfirm(type, id, name, refreshFn) {
    showConfirm(
        `Delete ${type}`,
        `Are you sure you want to delete "${name}"? This cannot be undone.`,
        async () => {
            try {
                await apiRequest(`/${type}s/${id}`, { method: 'DELETE' });
                showSuccess(`${type} deleted successfully`);
                if (refreshFn) refreshFn();
            } catch (error) {
                showError(error.message);
            }
        }
    );
}

function deletePatient(id, name) {
    deleteWithConfirm('patient', id, name, () => { loadPatients(); loadDashboard(); });
}

function deletePrescription(id, medName) {
    deleteWithConfirm('prescription', id, medName, () => { loadPatientMeds(); loadDashboard(); });
}

function deleteDoctor(id, name) {
    deleteWithConfirm('doctor', id, name, loadDoctors);
}

function deletePharmacy(id, name) {
    deleteWithConfirm('pharmacy', id, name, loadPharmacies);
}

// --- Custom Modal System (replaces window.alert/confirm) ---

let confirmCallback = null;

function openModal(modalId) {
    document.getElementById('modal-overlay').classList.add('active');
    document.getElementById(modalId).classList.add('active');
    document.body.style.overflow = 'hidden';
    // Initialize Lucide icons for dynamically added modal content
    setTimeout(initLucideIcons, 0);
}

function closeModal(event) {
    if (event && event.target !== event.currentTarget && !event.target.closest('.modal')) return;
    document.getElementById('modal-overlay').classList.remove('active');
    document.querySelectorAll('.modal').forEach(m => m.classList.remove('active'));
    document.body.style.overflow = '';
    confirmCallback = null;
}

// Custom confirm dialog (replaces window.confirm)
function showConfirm(title, message, onConfirm) {
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-message').textContent = message;
    confirmCallback = onConfirm;
    openModal('confirm-modal');
}

// Custom alert dialog (replaces window.alert)
function showAlert(title, message) {
    document.getElementById('alert-title').textContent = title;
    document.getElementById('alert-message').textContent = message;
    openModal('alert-modal');
}

// Handle confirm OK button
document.getElementById('confirm-ok').addEventListener('click', () => {
    if (confirmCallback) {
        confirmCallback();
        confirmCallback = null;
    }
    closeModal();
});

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
});

// Close modal on overlay click
document.getElementById('modal-overlay').addEventListener('click', closeModal);

// --- Caregiver Loading ---

async function loadCaregivers() {
    try {
        caregivers = await apiRequest('/caregivers');
        const select = document.getElementById('caregiver-select');
        select.innerHTML = caregivers.map(c => 
            `<option value="${c.id}">${c.name} (${c.email})</option>`
        ).join('');
        select.disabled = false;
        
        if (caregivers.length > 0) {
            currentCaregiverId = caregivers[0].id;
            select.value = currentCaregiverId;
            updateCaregiverInfo(caregivers[0]);
            // Don't navigate here - let hashchange handle it
            activateView(currentView);
        }
        
        select.addEventListener('change', (e) => {
            currentCaregiverId = e.target.value;
            const caregiver = caregivers.find(c => c.id === currentCaregiverId);
            updateCaregiverInfo(caregiver);
            activateView(currentView);
        });
    } catch (error) {
        console.error('Failed to load caregivers:', error);
        showAlert('Error', 'Failed to load caregivers: ' + error.message);
    }
}

function updateCaregiverInfo(caregiver) {
    document.getElementById('caregiver-email').textContent = caregiver.email;
    document.getElementById('caregiver-timezone').textContent = caregiver.timezone;
    document.getElementById('caregiver-info').style.display = 'block';
}

// --- Dashboard ---

async function loadDashboard() {
    if (!currentCaregiverId) return;
    const summaryEl = document.getElementById('stats-grid');
    const boardEl = document.getElementById('patients-grid');
    const dateEl = document.getElementById('cue-date');
    if (dateEl) {
        dateEl.textContent = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
    }

    if (summaryEl) summaryEl.innerHTML = `<div class="cue-loading"><div class="spinner"></div><p>Loading data...</p></div>`;
    if (boardEl) boardEl.innerHTML = `<div class="cue-loading"><div class="spinner"></div><p>Loading patients...</p></div>`;
    initLucideIcons();

    try {
        const data = await apiRequest(`/dashboard?caregiver_id=${currentCaregiverId}`);
        renderStats(data);
        renderPatientCards(data.patients);
        initLucideIcons();
        const sub = document.getElementById('cue-board-sub');
        if (sub) sub.textContent = `${data.patients.length} patient${data.patients.length === 1 ? '' : 's'} · sorted by urgency`;
    } catch (error) {
        console.error('Failed to load dashboard:', error);
        if (summaryEl) summaryEl.innerHTML = `<div class="cue-error"><i data-lucide="alert-triangle"></i><div class="cue-error-title">Dashboard didn’t load</div><p>${escapeHtml(error.message)}</p><button class="btn btn-primary btn-sm" onclick="loadDashboard()">Retry</button></div>`;
        if (boardEl) boardEl.innerHTML = `<div class="cue-error"><i data-lucide="alert-triangle"></i><div class="cue-error-title">Patients didn’t load</div><p>Check connection and try again.</p><button class="btn btn-primary btn-sm" onclick="loadDashboard()">Retry</button></div>`;
        initLucideIcons();
    }
}

function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function initialsOf(name) {
    return String(name || '?').trim().split(/\s+/).slice(0, 2).map(w => w[0] || '').join('').toUpperCase();
}

function renderStats(data) {
    const grid = document.getElementById('stats-grid');
    if (!grid) return;
    const overdue = data.total_overdue || 0;
    const dueSoon = data.total_due_soon || 0;
    const conflicts = data.total_conflicts || 0;
    const lowAdh = data.total_low_adherence || 0;

    const focus = overdue > 0
        ? { kind: 'urgent', icon: 'siren', kicker: 'Action needed', n: overdue, label: overdue === 1 ? 'refill late' : 'refills late' }
        : conflicts > 0
        ? { kind: 'urgent', icon: 'alert-triangle', kicker: 'Needs review', n: conflicts, label: conflicts === 1 ? 'drug conflict' : 'drug conflicts' }
        : dueSoon > 0
        ? { kind: 'warn', icon: 'clock', kicker: 'Coming up', n: dueSoon, label: dueSoon === 1 ? 'refill due soon' : 'refills due soon' }
        : { kind: 'calm', icon: 'check-circle-2', kicker: 'All clear', n: 0, label: 'issues' };

    const topItems = [];
    (data.patients || []).forEach(p => {
        (p.prescriptions || []).forEach(rx => {
            if (rx.is_refill_overdue) topItems.push({ t: 'overdue', med: `${rx.medication_name} ${rx.strength}`, who: p.patient.name, when: rx.next_refill_due ? formatDate(rx.next_refill_due) : 'due' });
        });
        (p.conflicts || []).slice(0, 2).forEach(c => {
            topItems.push({ t: 'conflict', med: conflictTypeLabel(c.type), who: p.patient.name, when: c.severity });
        });
    });
    const shown = topItems.slice(0, 3);

    const focusTitle = focus.kind === 'calm'
        ? 'Nothing needs attention right now'
        : focus.kind === 'warn'
        ? 'A few refills are coming up'
        : 'Handle these first - the rest can wait';
    const focusDesc = focus.kind === 'calm'
        ? 'All refills are covered, no medicine conflicts, doses taken on time. We\'ll alert you when something needs action.'
        : focus.kind === 'warn'
        ? 'No late refills yet. A few are coming up soon - order them now to stay on track.'
        : `${overdue} refill${overdue === 1 ? '' : 's'} late${conflicts ? ` and ${conflicts} conflict${conflicts === 1 ? '' : 's'}` : ''} need your decision.`;

    grid.innerHTML = `
        <div class="cue-focus ${focus.kind === 'calm' ? 'is-calm' : focus.kind === 'warn' ? 'is-warn' : 'is-urgent'}">
            <div class="cue-score">
                <div class="cue-score-num">${focus.n}</div>
                <div class="cue-score-label">${escapeHtml(focus.label)}</div>
                <div class="cue-score-sub">${focus.kind === 'calm' ? 'quiet monitor' : 'highest priority'}</div>
            </div>
            <div class="cue-focus-body">
                <p class="cue-focus-kicker">${escapeHtml(focus.kicker)}</p>
                <h3 class="cue-focus-title">${escapeHtml(focusTitle)}</h3>
                <p class="cue-focus-desc">${escapeHtml(focusDesc)}</p>
                ${shown.length ? `<div class="cue-focus-list">${shown.map(it => `
                    <div class="cue-focus-item"><strong>${escapeHtml(it.med)}</strong><span>${escapeHtml(it.who)} · ${escapeHtml(it.when)}</span></div>
                `).join('')}</div>` : ''}
            </div>
        </div>
        <div class="cue-rail">
            <div class="cue-mini tone-amber">
                <i data-lucide="clock" class="cue-mini-icon"></i>
                <div><div class="cue-mini-num">${dueSoon}</div><div class="cue-mini-label">Refills due in 7 days</div></div>
                <span class="cue-mini-hint ${dueSoon ? 'is-warm' : 'is-quiet'}">${dueSoon ? 'order now' : 'clear'}</span>
            </div>
            <div class="cue-mini tone-rose">
                <i data-lucide="alert-triangle" class="cue-mini-icon"></i>
                <div><div class="cue-mini-num">${conflicts}</div><div class="cue-mini-label">Medicine conflicts</div></div>
                <span class="cue-mini-hint ${conflicts ? 'is-hot' : 'is-quiet'}">${conflicts ? 'check' : 'clear'}</span>
            </div>
            <div class="cue-mini tone-teal">
                <i data-lucide="activity" class="cue-mini-icon"></i>
                <div><div class="cue-mini-num">${lowAdh}</div><div class="cue-mini-label">Missed doses</div></div>
                <span class="cue-mini-hint ${lowAdh ? 'is-warm' : 'is-quiet'}">${lowAdh ? 'check in' : 'all good'}</span>
            </div>
        </div>
    `;
}

// Helper: Render empty state with icon, title, text, and optional CTA button
function renderEmptyState(icon, title, text, ctaText = null, ctaAction = null) {
    const cta = ctaText && ctaAction 
        ? `<button class="btn btn-primary" onclick="${ctaAction}">${ctaText}</button>` 
        : '';
    return `
        <div class="empty-state">
            <div class="empty-state-icon">${icon}</div>
            <div class="empty-state-title">${title}</div>
            <div class="empty-state-text">${text}</div>
            ${cta ? `<div class="empty-state-cta">${cta}</div>` : ''}
        </div>
    `;
}

function cueEmpty(icon, title, text, ctaText = null, ctaAction = null) {
    return `<div class="cue-empty"><i data-lucide="${icon}"></i><strong>${escapeHtml(title)}</strong><span>${escapeHtml(text)}</span>${ctaText ? `<div><button onclick="${ctaAction}">${escapeHtml(ctaText)}</button></div>` : ''}</div>`;
}

function renderPatientCards(patients) {
    const grid = document.getElementById('patients-grid');
    if (!grid) return;
    if (!patients || patients.length === 0) {
        grid.innerHTML = renderEmptyState(
            '<i data-lucide="users"></i>',
            'No Patients Yet',
            'Add a patient to start tracking medications',
            'Add Patient',
            "openModal('patient-modal')"
        );
        initLucideIcons();
        return;
    }
    const ordered = [...patients].sort((a, b) =>
        ((b.overdue_count || 0) * 3 + (b.conflicts_count || b.conflicts?.length || 0) * 2 + (b.due_soon_count || 0))
        - ((a.overdue_count || 0) * 3 + (a.conflicts_count || a.conflicts?.length || 0) * 2 + (a.due_soon_count || 0))
    );
    grid.innerHTML = ordered.map(p => {
        const rxList = p.prescriptions || [];
        const conflicts = p.conflicts || [];
        const overdueRx = rxList.filter(r => r.is_refill_overdue);
        const soonRx = rxList.filter(r => !r.is_refill_overdue && r.is_refill_due_soon);
        const urgent = overdueRx.length + conflicts.length > 0;
        const pills = [];
        if (overdueRx.length) pills.push(`<span class="cue-pill is-critical"><i data-lucide="siren"></i>${overdueRx.length} refill late</span>`);
        if (soonRx.length) pills.push(`<span class="cue-pill is-warn"><i data-lucide="clock"></i>${soonRx.length} refill due soon</span>`);
        if (conflicts.length) pills.push(`<span class="cue-pill is-critical"><i data-lucide="alert-triangle"></i>${conflicts.length} medicine conflict${conflicts.length === 1 ? '' : 's'}</span>`);
        if (!pills.length) pills.push(`<span class="cue-pill is-ok"><i data-lucide="check-circle-2"></i>good</span>`);
        if (p.adherence === null || p.adherence === undefined) pills.push(`<span class="cue-pill is-neutral"><i data-lucide="activity"></i>no data</span>`);

        return `
        <article class="cue-patient cue-patient-compact ${urgent ? 'has-urgent' : ''}" onclick="selectPatient('${p.patient.id}')" style="cursor:pointer;">
            <div class="cue-patient-top">
                <div class="cue-avatar">${escapeHtml(initialsOf(p.patient.name))}</div>
                <div class="cue-patient-id">
                    <div class="cue-patient-name">${escapeHtml(p.patient.name)} <span style="font-weight:400;color:var(--color-muted);font-size:0.85rem">age ${p.patient.age}</span></div>
                    <div class="cue-pill-row">${pills.join('')}</div>
                </div>
                <div class="cue-manage-btn"><i data-lucide="arrow-right"></i></div>
            </div>
        </article>`;
    }).join('');
    initLucideIcons();
}

// --- Patients View ---

async function loadPatients() {
    if (!currentCaregiverId) return;
    const container = document.getElementById('patients-list');
    if (!container) return;
    
    showLoading('patients-list', 'Loading patients...');
    
    try {
        const patients = await apiRequest(`/patients?caregiver_id=${currentCaregiverId}`);
        renderPatientsList(patients);
        initLucideIcons();
    } catch (error) {
        console.error('Failed to load patients:', error);
        showErrorState('patients-list', 'Failed to load patients: ' + error.message, 'loadPatients()');
    }
}

function renderPatientsList(patients) {
    const container = document.getElementById('patients-list');
    if (patients.length === 0) {
        container.innerHTML = renderEmptyState(
            '<i data-lucide="users"></i>',
            'No Patients',
            'Add your first patient to get started'
        );
        return;
    }
    container.innerHTML = patients.map(p => `
        <div class="list-item">
            <div class="list-item-info">
                <span class="list-item-title">${p.name} (age ${p.age})</span>
                <span class="list-item-meta">DOB: ${formatDate(p.date_of_birth)} ${p.notes ? '• ' + p.notes : ''}</span>
            </div>
            <div class="list-item-actions">
                <button class="btn btn-primary btn-sm" onclick="selectPatient('${p.id}')"><i data-lucide="pill" class="btn-icon"></i> Manage Meds</button>
                <button class="btn btn-danger btn-sm" onclick="deletePatient('${p.id}', '${p.name.replace(/'/g, "\\'")}')"><i data-lucide="trash-2"></i> Delete</button>
            </div>
        </div>
    `).join('');
}

// --- Medications View ---

function selectPatient(patientId) {
    currentPatientId = patientId;
    navigateTo('patient-meds');
    loadPatientMeds();
}

async function ensurePatientSelected() {
    console.log('[CareCue] ensurePatientSelected: start', { currentPatientId, currentCaregiverId });
    if (currentPatientId) {
        console.log('[CareCue] ensurePatientSelected: already set', currentPatientId);
        return true;
    }
    if (!currentCaregiverId) {
        console.log('[CareCue] ensurePatientSelected: no caregiver yet, cannot resolve');
        return false;
    }
    try {
        const patients = await apiRequest(`/patients?caregiver_id=${currentCaregiverId}`);
        if (patients.length > 0) {
            currentPatientId = patients[0].id;
            console.log('[CareCue] ensurePatientSelected: resolved to', currentPatientId);
            return true;
        }
        console.log('[CareCue] ensurePatientSelected: caregiver has zero patients');
    } catch (error) {
        console.error('Failed to resolve patient:', error);
    }
    return false;
}

// --- Medications View (global, cross-patient, read-only) ---

async function loadMedications() {
    if (!currentCaregiverId) return;
    console.log('[CareCue] loadMedications: global fetch for caregiver =', currentCaregiverId);
    showLoading('medications-list', 'Loading all medications...');

    try {
        const [meds, patients] = await Promise.all([
            apiRequest(`/medications?caregiver_id=${currentCaregiverId}`),
            apiRequest(`/patients?caregiver_id=${currentCaregiverId}`)
        ]);
        allMedications = meds || [];
        const patientFilter = document.getElementById('meds-filter-patient');
        const knownIds = new Set((patients || []).map(p => p.id));
        if (currentPatientId && knownIds.has(currentPatientId)) {
            medsFilterPatient = currentPatientId;
        } else {
            medsFilterPatient = 'all';
        }
        if (patientFilter) {
            patientFilter.innerHTML = `<option value="all">All Patients</option>` + (patients || []).map(p =>
                `<option value="${p.id}" ${p.id === medsFilterPatient ? 'selected' : ''}>${escapeHtml(p.name)}</option>`
            ).join('');
        }
        const summary = document.getElementById('meds-summary-line');
        if (summary) summary.textContent = `${allMedications.length} medication${allMedications.length === 1 ? '' : 's'} across ${patients.length} patient${patients.length === 1 ? '' : 's'}, sorted by urgency`;
        renderMedications();
        initLucideIcons();
    } catch (error) {
        console.error('Failed to load medications:', error);
        showErrorState('medications-list', 'Failed to load medications: ' + error.message, 'loadMedications()');
        initLucideIcons();
    }
}

function medsStatusOf(rx) {
    return getRefillStatus(rx).status;
}

function renderMedications() {
    const container = document.getElementById('medications-list');
    if (!container) return;
    let list = [...(allMedications || [])];
    if (medsFilterPatient !== 'all') {
        list = list.filter(rx => rx.patient_id === medsFilterPatient);
    }
    if (medsFilterStatus !== 'all') {
        list = list.filter(rx => medsStatusOf(rx) === medsFilterStatus);
    }
    if (list.length === 0) {
        const isFiltered = medsFilterPatient !== 'all' || medsFilterStatus !== 'all';
        container.innerHTML = renderEmptyState(
            '<i data-lucide="pill"></i>',
            isFiltered ? 'No Matches' : 'No Medications',
            isFiltered
                ? 'No medications match these filters - try widening them'
                : 'No prescriptions yet - add the first one from a patient Manage Meds view'
        );
        initLucideIcons();
        return;
    }
    const rank = { 'overdue': 0, 'due-soon': 1, 'ok': 2 };
    list.sort((a, b) => {
        const sa = rank[medsStatusOf(a)] ?? 3, sb = rank[medsStatusOf(b)] ?? 3;
        if (sa !== sb) return sa - sb;
        return (a.next_refill_due || '').localeCompare(b.next_refill_due || '');
    });
    container.innerHTML = list.map(rx => {
        const refill = getRefillStatus(rx);
        const doc = (rx.doctor_name || '').replace(/^Dr\.?\s*/i, '');
        return `
            <div class="list-item meds-row">
                <div class="meds-patient">
                    <span class="cue-avatar cue-avatar-sm">${escapeHtml(initialsOf(rx.patient_name))}</span>
                    <span class="meds-patient-name" title="${escapeHtml(rx.patient_name)}">${escapeHtml(rx.patient_name)}</span>
                </div>
                <div class="list-item-info">
                    <span class="list-item-title">${escapeHtml(rx.medication_name)} ${escapeHtml(rx.strength)}</span>
                    <span class="list-item-meta">Dr. ${escapeHtml(doc)} • ${rx.dose_amount} ${escapeHtml(rx.dose_unit)} • ${escapeHtml(rx.frequency)}${rx.instructions ? ' • ' + escapeHtml(rx.instructions) : ''}</span>
                </div>
                <div class="list-item-actions">
                    ${getStatusBadge(refill.status, refill.text)}
                    <span class="list-item-meta">Due ${rx.next_refill_due ? formatDate(rx.next_refill_due) : '-'} • ${rx.refills_remaining}/${rx.total_refills_allowed} left</span>
                    <button class="btn btn-secondary btn-sm" onclick="selectPatient('${rx.patient_id}')"><i data-lucide="arrow-right" class="btn-icon"></i> Manage</button>
                </div>
            </div>
        `;
    }).join('');
    initLucideIcons();
}

// --- Patient Medications Detail (per-patient Manage Meds - add/edit here) ---

async function loadPatientMeds() {
    if (!await ensurePatientSelected()) {
        document.getElementById('patient-meds-name').textContent = 'Manage Medications';
        document.getElementById('patient-meds-list').innerHTML = renderEmptyState(
            '<i data-lucide="users"></i>',
            'No Patient Selected',
            'Select a patient from the Patients view to manage their medications'
        );
        initLucideIcons();
        return;
    }

    const pid = currentPatientId;
    console.log('[CareCue] loadPatientMeds: fetching with patientId =', pid);
    showLoading('patient-meds-list', 'Loading medications...');

    try {
        const [patient, prescriptions, availableDoctors, availablePharmacies] = await Promise.all([
            apiRequest(`/patients/${pid}`),
            apiRequest(`/prescriptions?patient_id=${pid}`),
            apiRequest('/doctors'),
            apiRequest(`/pharmacies?patient_id=${pid}`)
        ]);
        document.getElementById('patient-meds-name').textContent = `Medications for ${patient.name}`;
        renderTelegramLinkSection(patient);
        renderPatientPrescriptions(prescriptions);
        doctors = availableDoctors;
        pharmacies = availablePharmacies;
        initLucideIcons();
    } catch (error) {
        console.error('Failed to load medications:', error);
        showErrorState('patient-meds-list', 'Failed to load medications: ' + error.message, 'loadPatientMeds()');
        initLucideIcons();
    }
}

function renderTelegramLinkSection(patient) {
    const section = document.getElementById('telegram-link-section');
    if (!section) return;
    if (patient.telegram_chat_id) {
        section.innerHTML = `
            <div style="display:flex;align-items:center;gap:var(--sp-2);">
                <i data-lucide="check-circle" style="color:#22c55e;width:18px;height:18px;"></i>
                <span style="font-weight:var(--weight-semibold);">Telegram: Linked</span>
                <span style="color:var(--color-muted);font-size:var(--text-small);">(chat_id: ${patient.telegram_chat_id})</span>
            </div>`;
        section.style.display = 'block';
        initLucideIcons();
        return;
    }
    section.innerHTML = `
        <div style="display:flex;align-items:center;gap:var(--sp-2);margin-bottom:var(--sp-2);">
            <i data-lucide="message-circle" style="color:var(--color-accent,#06b6d4);width:18px;height:18px;"></i>
            <span style="font-weight:var(--weight-semibold);">Telegram: Not linked</span>
        </div>
        <p style="margin:0 0 var(--sp-2);font-size:var(--text-small);color:var(--color-muted);">
            To receive dose reminders on Telegram, open Telegram and send the command below to <strong>@CareCueBot</strong>:
        </p>
        <div id="telegram-link-code-box" style="display:flex;align-items:center;gap:var(--sp-2);">
            <button class="btn btn-secondary btn-sm" onclick="generateTelegramLink('${patient.id}')">Generate linking code</button>
        </div>`;
    section.style.display = 'block';
    initLucideIcons();
}

async function generateTelegramLink(patientId) {
    const box = document.getElementById('telegram-link-code-box');
    if (!box) return;
    try {
        const result = await apiRequest(`/patients/${patientId}/telegram-link`, { method: 'POST' });
        if (result.already_linked) {
            loadPatientMeds();
            return;
        }
        box.innerHTML = `
            <code style="background:var(--color-surface-2);padding:var(--sp-2) var(--sp-3);border-radius:var(--r-sm);font-size:1.1rem;font-weight:var(--weight-bold);letter-spacing:0.05em;border:1px solid var(--color-border);color:var(--color-foreground);">/start ${result.code}</code>
            <span style="font-size:var(--text-small);color:var(--color-muted);">→ @${result.bot_username}</span>`;
    } catch (e) {
        box.innerHTML = `<span style="color:#dc2626;">Failed: ${e.message}</span>`;
    }
}

function renderPatientPrescriptions(prescriptions) {
    currentPrescriptions = prescriptions || [];
    const container = document.getElementById('patient-meds-list');
    if (prescriptions.length === 0) {
        container.innerHTML = renderEmptyState(
            '<i data-lucide="pill"></i>',
            'No Prescriptions',
            'Add the first prescription for this patient'
        );
        return;
    }
    container.innerHTML = prescriptions.map(rx => {
        const refill = getRefillStatus(rx);
        return `
            <div class="list-item">
                <div class="list-item-info">
                    <span class="list-item-title">${rx.medication_name} ${rx.strength}</span>
                    <span class="list-item-meta">${rx.dose_amount} ${rx.dose_unit} • ${rx.frequency} • ${rx.instructions || ''}</span>
                </div>
                <div class="list-item-actions">
                    ${getStatusBadge(refill.status, refill.text)}
                    <span class="list-item-meta">Refills: ${rx.refills_remaining}/${rx.total_refills_allowed}</span>
                    <button class="btn btn-secondary btn-sm" onclick="editPrescription('${rx.id}')"><i data-lucide="edit-2" class="btn-icon"></i> Edit</button>
                    <button class="btn btn-danger btn-sm" onclick="deletePrescription('${rx.id}', '${rx.medication_name.replace(/'/g, "\\'")} ${rx.strength}')"><i data-lucide="trash-2"></i> Delete</button>
                </div>
            </div>
        `;
    }).join('');
    initLucideIcons();
}

// --- Doctors View ---

async function loadDoctors() {
    const container = document.getElementById('doctors-list');
    if (!container) return;
    
    showLoading('doctors-list', 'Loading doctors...');
    
    try {
        doctors = await apiRequest('/doctors');
        renderDoctorsList(doctors);
        initLucideIcons();
    } catch (error) {
        console.error('Failed to load doctors:', error);
        showErrorState('doctors-list', 'Failed to load doctors: ' + error.message, 'loadDoctors()');
    }
}

function renderDoctorsList(list) {
    const container = document.getElementById('doctors-list');
    if (list.length === 0) {
        container.innerHTML = renderEmptyState(
            '<i data-lucide="stethoscope"></i>',
            'No Doctors',
            'Add a doctor to associate with prescriptions'
        );
        return;
    }
    container.innerHTML = list.map(d => `
        <div class="list-item">
            <div class="list-item-info">
                <span class="list-item-title">${d.name}</span>
                <span class="list-item-meta">${d.specialty || 'General'} • ${d.practice_name || ''} • ${d.phone || 'No phone'}</span>
            </div>
            <div class="list-item-actions">
                <span class="list-item-meta">${d.prescription_count || 0} prescriptions</span>
                <button class="btn btn-danger btn-sm" onclick="deleteDoctor('${d.id}', '${d.name.replace(/'/g, "\\'")}')"><i data-lucide="trash-2"></i> Delete</button>
            </div>
        </div>
    `).join('');
}

// --- Pharmacies View ---

async function loadPharmacies() {
    console.log('[CareCue] loadPharmacies: called, currentPatientId =', currentPatientId);
    if (!await ensurePatientSelected()) {
        document.getElementById('pharmacy-patient-name').textContent = 'Pharmacies';
        document.getElementById('pharmacies-list').innerHTML = renderEmptyState(
            '<i data-lucide="users"></i>',
            'No Patient Selected',
            'Select a patient from the Patients view to see their pharmacies'
        );
        initLucideIcons();
        return;
    }
    const container = document.getElementById('pharmacies-list');
    if (!container) return;

    // Capture locally so a mid-flight state change can't blank the fetch.
    const pid = currentPatientId;
    console.log('[CareCue] loadPharmacies: fetching with patientId =', pid);
    showLoading('pharmacies-list', 'Loading pharmacies...');

    try {
        const [patient, list] = await Promise.all([
            apiRequest(`/patients/${pid}`),
            apiRequest(`/pharmacies?patient_id=${pid}`)
        ]);
        pharmacies = list;
        document.getElementById('pharmacy-patient-name').textContent = `Pharmacies for ${patient.name}`;
        renderPharmaciesList(list);
        initLucideIcons();
    } catch (error) {
        console.error('Failed to load pharmacies:', error);
        showErrorState('pharmacies-list', 'Failed to load pharmacies: ' + error.message, 'loadPharmacies()');
    }
}

function renderPharmaciesList(list) {
    const container = document.getElementById('pharmacies-list');
    if (list.length === 0) {
        container.innerHTML = renderEmptyState(
            '<i data-lucide="store"></i>',
            'No Pharmacies',
            'Add a pharmacy for this patient'
        );
        return;
    }
    container.innerHTML = list.map(p => `
        <div class="list-item">
            <div class="list-item-info">
                <span class="list-item-title">${p.name} ${p.is_preferred ? '<i data-lucide="star" class="inline-icon"></i>' : ''}</span>
                <span class="list-item-meta">${p.address || ''} • ${p.phone} • ${p.hours || ''}</span>
            </div>
            <div class="list-item-actions">
                ${!p.is_preferred ? `<button class="btn btn-secondary btn-sm" onclick="setPreferredPharmacy('${p.id}')"><i data-lucide="star" class="btn-icon"></i> Make Preferred</button>` : ''}
                <button class="btn btn-danger btn-sm" onclick="deletePharmacy('${p.id}', '${p.name.replace(/'/g, "\\'")}')"><i data-lucide="trash-2"></i> Delete</button>
            </div>
        </div>
    `).join('');
}

// --- Dropdown Loading ---

async function loadDropdowns() {
    doctors = await apiRequest('/doctors');
    pharmacies = await apiRequest(`/pharmacies?patient_id=${currentPatientId}`);
    
    const doctorSelect = document.getElementById('prescription-doctor');
    if (doctors.length === 0) {
        doctorSelect.innerHTML = '<option value="" disabled>No doctors available - add one first</option>';
    } else {
        doctorSelect.innerHTML = doctors.map(d => 
            `<option value="${d.id}">${d.name} (${d.specialty || 'General'})</option>`
        ).join('');
    }
    
    const pharmacySelect = document.getElementById('prescription-pharmacy');
    if (pharmacies.length === 0) {
        pharmacySelect.innerHTML = '<option value="" disabled>No pharmacies available - add one first</option>';
    } else {
        pharmacySelect.innerHTML = pharmacies.map(p => 
            `<option value="${p.id}" ${p.is_preferred ? 'selected' : ''}>${p.name} - ${p.phone}</option>`
        ).join('');
    }
}

async function loadPharmacyDropdowns() {
    pharmacies = await apiRequest(`/pharmacies?patient_id=${currentPatientId}`);
}

// --- Prescription Add/Edit Flow ---

function setPrescriptionModalMode(mode) {
    const titleEl = document.getElementById('prescription-modal-title-text');
    const submitBtn = document.getElementById('prescription-submit-btn');
    if (titleEl) titleEl.textContent = mode === 'edit' ? 'Edit Prescription' : 'Add Prescription';
    if (submitBtn) submitBtn.textContent = mode === 'edit' ? 'Save Changes' : 'Add Prescription';
}

function resetPrescriptionModal() {
    editingPrescriptionId = null;
    const form = document.getElementById('prescription-form');
    if (form) {
        form.reset();
        clearAllErrors('prescription-form');
        clearFormError('prescription-form');
    }
    setPrescriptionModalMode('add');
}

function fillPrescriptionForm(rx) {
    const form = document.getElementById('prescription-form');
    if (!form) return;
    const setVal = (name, value) => {
        const input = form.querySelector(`[name="${name}"]`);
        if (input && value !== null && value !== undefined) input.value = value;
    };
    setVal('medication_name', rx.medication_name);
    setVal('generic_name', rx.generic_name || '');
    setVal('strength', rx.strength);
    setVal('form', rx.form || 'tablet');
    setVal('route', rx.route || 'oral');
    setVal('dose_amount', rx.dose_amount);
    setVal('dose_unit', rx.dose_unit);
    setVal('frequency', rx.frequency);
    setVal('doctor_id', rx.doctor_id);
    setVal('pharmacy_id', rx.pharmacy_id);
    setVal('instructions', rx.instructions || '');
    setVal('refill_cycle_days', rx.refill_cycle_days);
    setVal('refills_remaining', rx.refills_remaining);
    setVal('total_refills_allowed', rx.total_refills_allowed);
    setVal('last_filled_date', rx.last_filled_date || '');
    setVal('prescription_start_date', rx.prescription_start_date || '');
    setVal('ndc_code', rx.ndc_code || '');
    setVal('rxnorm_cui', rx.rxnorm_cui || '');
}

async function openPrescriptionModalForAdd() {
    if (!currentPatientId) {
        showAlert('No Patient Selected', 'Select a patient from the Patients view before adding a prescription.');
        return;
    }
    resetPrescriptionModal();
    try {
        await loadDropdowns();
    } catch (error) {
        showError('Failed to load doctors/pharmacies: ' + error.message);
        return;
    }
    openModal('prescription-modal');
}

async function addPrescriptionForPatient(patientId) {
    currentPatientId = patientId;
    await openPrescriptionModalForAdd();
}

async function editPrescription(id) {
    const rx = (currentPrescriptions || []).find(r => r.id === id);
    if (!rx) {
        showError('Prescription not found. Please reload the list and try again.');
        return;
    }
    if (!currentPatientId) currentPatientId = rx.patient_id;
    editingPrescriptionId = id;
    clearAllErrors('prescription-form');
    clearFormError('prescription-form');
    try {
        await loadDropdowns();
    } catch (error) {
        showError('Failed to load doctors/pharmacies: ' + error.message);
        editingPrescriptionId = null;
        return;
    }
    fillPrescriptionForm(rx);
    setPrescriptionModalMode('edit');
    openModal('prescription-modal');
}

// --- Form Validation Rules ---

const patientValidationRules = {
    name: [
        { validator: v => validateRequired(v), message: 'Patient name is required' },
        { validator: v => v.trim().length <= 100, message: 'Name must be 100 characters or less' }
    ],
    date_of_birth: [
        { validator: v => validateRequired(v), message: 'Date of birth is required' },
        { validator: v => validateDateNotFuture(v), message: 'Date of birth cannot be in the future' }
    ],
    phone: [
        { validator: v => !v || /^\d{10}$/.test(v), message: 'Phone must be exactly 10 digits' }
    ],
    notes: [
        { validator: v => !v || v.length <= 1000, message: 'Notes must be 1000 characters or less' }
    ]
};

const prescriptionValidationRules = {
    medication_name: [
        { validator: v => validateRequired(v), message: 'Medication name is required' },
        { validator: v => v.trim().length <= 200, message: 'Medication name must be 200 characters or less' }
    ],
    strength: [
        { validator: v => validateRequired(v), message: 'Strength is required' },
        { validator: v => v.trim().length <= 50, message: 'Strength must be 50 characters or less' }
    ],
    form: [
        { validator: v => !v || v.trim().length <= 50, message: 'Form must be 50 characters or less' }
    ],
    route: [
        { validator: v => !v || v.trim().length <= 50, message: 'Route must be 50 characters or less' }
    ],
    dose_amount: [
        { validator: v => validateRequired(v), message: 'Dose amount is required' },
        { validator: v => validatePositiveNumber(v), message: 'Dose amount must be a positive number' }
    ],
    dose_unit: [
        { validator: v => validateRequired(v), message: 'Dose unit is required' }
    ],
    frequency: [
        { validator: v => validateRequired(v), message: 'Frequency is required' }
    ],
    doctor_id: [
        { validator: v => validateRequired(v), message: 'Doctor is required' }
    ],
    pharmacy_id: [
        { validator: v => validateRequired(v), message: 'Pharmacy is required' }
    ],
    refill_cycle_days: [
        { validator: v => validateRequired(v), message: 'Refill cycle is required' },
        { validator: v => validatePositiveNumber(v) && parseInt(v) <= 365, message: 'Refill cycle must be 1-365 days' }
    ],
    refills_remaining: [
        { validator: v => !v || validateNonNegativeNumber(v), message: 'Refills remaining must be 0 or greater' }
    ],
    total_refills_allowed: [
        { validator: v => !v || validateNonNegativeNumber(v), message: 'Total refills must be 0 or greater' }
    ],
    last_filled_date: [
        { validator: v => validateRequired(v), message: 'Last filled date is required' }
    ],
    prescription_start_date: [
        { validator: v => validateRequired(v), message: 'Start date is required' }
    ],
    generic_name: [
        { validator: v => !v || v.length <= 200, message: 'Generic name must be 200 characters or less' }
    ],
    form: [
        { validator: v => !v || v.length <= 50, message: 'Form must be 50 characters or less' }
    ],
    route: [
        { validator: v => !v || v.length <= 50, message: 'Route must be 50 characters or less' }
    ],
    instructions: [
        { validator: v => !v || v.length <= 500, message: 'Instructions must be 500 characters or less' }
    ],
    refill_cycle_days: [
        { validator: v => validateRequired(v), message: 'Refill cycle is required' },
        { validator: v => validatePositiveNumber(v) && parseInt(v) <= 365, message: 'Refill cycle must be 1-365 days' }
    ],
    refills_remaining: [
        { validator: v => !v || validateNonNegativeNumber(v), message: 'Refills remaining must be 0 or greater' }
    ],
    total_refills_allowed: [
        { validator: v => !v || validateNonNegativeNumber(v), message: 'Total refills must be 0 or greater' }
    ],
    last_filled_date: [
        { validator: v => validateRequired(v), message: 'Last filled date is required' }
    ],
    prescription_start_date: [
        { validator: v => validateRequired(v), message: 'Start date is required' }
    ],
    ndc_code: [
        { validator: v => !v || v.length <= 50, message: 'NDC code must be 50 characters or less' }
    ],
    rxnorm_cui: [
        { validator: v => !v || v.length <= 50, message: 'RxNorm CUI must be 50 characters or less' }
    ]
};

const doctorValidationRules = {
    name: [
        { validator: v => validateRequired(v), message: 'Doctor name is required' },
        { validator: v => v.trim().length <= 100, message: 'Name must be 100 characters or less' }
    ],
    specialty: [
        { validator: v => !v || v.length <= 100, message: 'Specialty must be 100 characters or less' }
    ],
    practice_name: [
        { validator: v => !v || v.length <= 200, message: 'Practice name must be 200 characters or less' }
    ],
    phone: [
        { validator: v => !v || v.length <= 30, message: 'Phone must be 30 characters or less' }
    ],
    fax: [
        { validator: v => !v || v.length <= 30, message: 'Fax must be 30 characters or less' }
    ],
    email: [
        { validator: v => !v || validateEmail(v), message: 'Invalid email format' }
    ],
    address: [
        { validator: v => !v || v.length <= 300, message: 'Address must be 300 characters or less' }
    ],
    notes: [
        { validator: v => !v || v.length <= 1000, message: 'Notes must be 1000 characters or less' }
    ]
};

const pharmacyValidationRules = {
    name: [
        { validator: v => validateRequired(v), message: 'Pharmacy name is required' },
        { validator: v => v.trim().length <= 150, message: 'Name must be 150 characters or less' }
    ],
    phone: [
        { validator: v => validateRequired(v), message: 'Phone is required' },
        { validator: v => v.trim().length <= 30, message: 'Phone must be 30 characters or less' }
    ],
    address: [
        { validator: v => !v || v.length <= 300, message: 'Address must be 300 characters or less' }
    ],
    fax: [
        { validator: v => !v || v.length <= 30, message: 'Fax must be 30 characters or less' }
    ],
    email: [
        { validator: v => !v || validateEmail(v), message: 'Invalid email format' }
    ],
    hours: [
        { validator: v => !v || v.length <= 200, message: 'Hours must be 200 characters or less' }
    ]
};

// --- Form Handlers ---

document.getElementById('f-patient-phone').addEventListener('input', (e) => {
    e.target.value = e.target.value.replace(/\D/g, '').slice(0, 10);
});

document.getElementById('patient-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    if (!validateForm('patient-form', patientValidationRules)) {
        return;
    }
    
    setFormSubmitting('patient-form', true);
    clearFormError('patient-form');
    
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData);
    data.date_of_birth = data.date_of_birth;
    try {
        await apiRequest(`/patients?caregiver_id=${currentCaregiverId}`, { method: 'POST', body: data });
        showSuccess('Patient added successfully');
        closeModal();
        e.target.reset();
        loadPatients();
        loadDashboard();
    } catch (error) {
        showFormError('patient-form', error.message);
        showError(error.message);
    } finally {
        setFormSubmitting('patient-form', false);
    }
});

document.getElementById('prescription-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    if (!validateForm('prescription-form', prescriptionValidationRules)) {
        return;
    }
    
    setFormSubmitting('prescription-form', true);
    clearFormError('prescription-form');
    
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData);
    data.dose_amount = parseFloat(data.dose_amount);
    data.refill_cycle_days = parseInt(data.refill_cycle_days);
    data.refills_remaining = parseInt(data.refills_remaining);
    data.total_refills_allowed = parseInt(data.total_refills_allowed);
    data.frequency_hours = data.frequency_hours ? parseInt(data.frequency_hours) : null;
    data.last_filled_date = data.last_filled_date;
    data.prescription_start_date = data.prescription_start_date;
    if (!data.generic_name) delete data.generic_name;
    if (!data.form) delete data.form;
    if (!data.route) delete data.route;
    if (!data.instructions) delete data.instructions;
    if (!data.ndc_code) delete data.ndc_code;
    if (!data.rxnorm_cui) delete data.rxnorm_cui;
    try {
        if (editingPrescriptionId) {
            await apiRequest(`/prescriptions/${editingPrescriptionId}`, { method: 'PATCH', body: data });
            showSuccess('Prescription updated successfully');
        } else {
            await apiRequest(`/prescriptions?patient_id=${currentPatientId}`, { method: 'POST', body: data });
            showSuccess('Prescription added successfully');
        }
        editingPrescriptionId = null;
        setPrescriptionModalMode('add');
        closeModal();
        e.target.reset();
        loadPatientMeds();
        loadDashboard();
    } catch (error) {
        showFormError('prescription-form', error.message);
        showError(error.message);
    } finally {
        setFormSubmitting('prescription-form', false);
    }
});

document.getElementById('doctor-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    if (!validateForm('doctor-form', doctorValidationRules)) {
        return;
    }
    
    setFormSubmitting('doctor-form', true);
    clearFormError('doctor-form');
    
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData);
    Object.keys(data).forEach(k => { if (!data[k]) delete data[k]; });
    try {
        await apiRequest('/doctors', { method: 'POST', body: data });
        showSuccess('Doctor added successfully');
        closeModal();
        e.target.reset();
        loadDoctors();
    } catch (error) {
        showFormError('doctor-form', error.message);
        showError(error.message);
    } finally {
        setFormSubmitting('doctor-form', false);
    }
});

document.getElementById('pharmacy-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    if (!validateForm('pharmacy-form', pharmacyValidationRules)) {
        return;
    }
    
    setFormSubmitting('pharmacy-form', true);
    clearFormError('pharmacy-form');
    
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData);
    data.is_preferred = formData.has('is_preferred');
    Object.keys(data).forEach(k => { if (data[k] === '') delete data[k]; });
    try {
        await apiRequest(`/pharmacies?patient_id=${currentPatientId}`, { method: 'POST', body: data });
        showSuccess('Pharmacy added successfully');
        closeModal();
        e.target.reset();
        loadPharmacies();
    } catch (error) {
        showFormError('pharmacy-form', error.message);
        showError(error.message);
    } finally {
        setFormSubmitting('pharmacy-form', false);
    }
});

async function setPreferredPharmacy(id) {
    try {
        for (const p of pharmacies) {
            await apiRequest(`/pharmacies/${p.id}`, { method: 'PATCH', body: { is_preferred: p.id === id } });
        }
        loadPharmacies();
    } catch (error) {
        showAlert('Error', error.message);
    }
}

// --- Initialize ---

function initLucideIcons() {
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
}

// --- Theme (light/dark), persisted, dark by default ---
function currentTheme() {
    return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
}

function applyTheme(theme, persist = true) {
    document.documentElement.dataset.theme = theme;
    if (persist) {
        try { localStorage.setItem('carecue-theme', theme); } catch (e) {}
    }
    const btn = document.getElementById('theme-toggle');
    if (btn) {
        const toLight = theme === 'dark';
        btn.innerHTML = `<i data-lucide="${toLight ? 'sun' : 'moon'}"></i>`;
        const label = toLight ? 'Switch to light mode' : 'Switch to dark mode';
        btn.setAttribute('aria-label', label);
        btn.title = label;
        initLucideIcons();
    }
}

function toggleTheme() {
    applyTheme(currentTheme() === 'dark' ? 'light' : 'dark');
}

document.addEventListener('DOMContentLoaded', () => {
    // Theme first (the <head> script already set it pre-paint) — just sync the toggle icon
    applyTheme(currentTheme(), false);
    const themeBtn = document.getElementById('theme-toggle');
    if (themeBtn) themeBtn.addEventListener('click', toggleTheme);

    // Initialize view from hash
    initViewFromHash();

    // Medications view filters — re-render the already-fetched list
    const patientFilter = document.getElementById('meds-filter-patient');
    if (patientFilter) {
        patientFilter.addEventListener('change', (e) => {
            medsFilterPatient = e.target.value;
            renderMedications();
        });
    }
    const statusFilter = document.getElementById('meds-filter-status');
    if (statusFilter) {
        statusFilter.addEventListener('change', (e) => {
            medsFilterStatus = e.target.value;
            renderMedications();
        });
    }

    // Load caregivers first
    loadCaregivers();
    
    // Set default dates
    const today = new Date().toISOString().split('T')[0];
    document.querySelectorAll('input[type="date"]').forEach(input => {
        if (!input.value) input.value = today;
    });
    
    // Initialize Lucide icons on initial load
    initLucideIcons();
});