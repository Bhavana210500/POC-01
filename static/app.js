// ================================================
// HELIX AIOPS PLATFORM — Dashboard Application
// ================================================

const API_BASE = '';
let currentTickets = [];
let selectedTicketId = null;
let refreshInterval = null;
let currentSearchQuery = '';
let lastEscalatedCount = 0;
let currentActiveTab = 'active';
let suppressedAlerts = [];

// ── Initialize ──────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initDashboard();
    startAutoRefresh();
    startClock();
    loadSimulateTemplates();

    // Close simulate menu on outside click
    document.addEventListener('click', (e) => {
        const menu = document.getElementById('simulate-menu');
        const fab = document.querySelector('.fab');
        if (menu && !menu.contains(e.target) && !fab.contains(e.target)) {
            menu.classList.remove('show');
        }
    });
});

async function initDashboard() {
    await Promise.all([
        refreshStats(),
        refreshTickets(),
        refreshAgents()
    ]);
}

function startAutoRefresh() {
    refreshInterval = setInterval(async () => {
        await refreshStats();
        if (!currentSearchQuery) {
            await refreshTickets();
        }
        await refreshAgents();
        if (selectedTicketId) {
            // --- FIX 1 & 4: Preserve approval form values; skip re-render if operator is typing ---
            const remediationTextarea = document.getElementById('approval-remediation');
            const commentInput = document.getElementById('approval-comment');
            const remediationTypeSelect = document.getElementById('approval-remediation-type');

            // If the approval form is visible and the operator has typed something, skip re-render
            const hasUnsavedInput = remediationTextarea && remediationTextarea.value.trim().length > 0;
            if (hasUnsavedInput) {
                // Still refresh stats and agents, but don't touch the detail panel
                return;
            }

            // Save any partial values before re-render (edge case: comment may have text even if remediation is empty)
            const savedRemediation = remediationTextarea ? remediationTextarea.value : '';
            const savedComment = commentInput ? commentInput.value : '';
            const savedType = remediationTypeSelect ? remediationTypeSelect.value : 'text';

            const detailContainer = document.getElementById('ticket-detail');
            const hasFocus = detailContainer && detailContainer.contains(document.activeElement);
            if (!hasFocus) {
                await showTicketDetail(selectedTicketId);

                // Restore form values after re-render
                const newTextarea = document.getElementById('approval-remediation');
                const newComment = document.getElementById('approval-comment');
                const newTypeSelect = document.getElementById('approval-remediation-type');
                if (newTextarea && savedRemediation) newTextarea.value = savedRemediation;
                if (newComment && savedComment) newComment.value = savedComment;
                if (newTypeSelect && savedType) newTypeSelect.value = savedType;
            }
        }
    }, 3000);
}

function startClock() {
    function updateClock() {
        const now = new Date();
        const el = document.getElementById('header-time');
        if (el) {
            el.textContent = now.toLocaleTimeString('en-US', {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: true
            });
        }
    }
    updateClock();
    setInterval(updateClock, 1000);
}

// ── Stats ───────────────────────────────────────
async function refreshStats() {
    try {
        const res = await fetch(`${API_BASE}/api/dashboard/stats`);
        const data = await res.json();
        animateCounter('stat-total', data.total_incidents || 0);
        animateCounter('stat-resolved', data.resolved || 0);
        animateCounter('stat-pending', data.pending_approval || 0);
        const agentCount = (data.agents || []).filter(a => a.status === 'processing').length;
        animateCounter('stat-active-agents', agentCount);

        updateBreakdown('priority-breakdown', data.by_priority || {});
        updateBreakdown('category-breakdown', data.by_category || {});
    } catch (e) {
        console.error('Stats error:', e);
    }
}

function animateCounter(elementId, target) {
    const el = document.getElementById(elementId);
    if (!el) return;
    const current = parseInt(el.textContent) || 0;
    if (current === target) return;

    const diff = target - current;
    const steps = 20;
    const increment = diff / steps;
    let step = 0;

    const timer = setInterval(() => {
        step++;
        el.textContent = Math.round(current + increment * step);
        if (step >= steps) {
            el.textContent = target;
            clearInterval(timer);
        }
    }, 30);
}

// ── Tickets ─────────────────────────────────────
async function refreshTickets() {
    try {
        const url = currentSearchQuery ? `${API_BASE}/api/tickets/search?q=${encodeURIComponent(currentSearchQuery)}` : `${API_BASE}/api/tickets`;
        const res = await fetch(url);
        const data = await res.json();
        currentTickets = data.tickets || [];
        
        // Check for new L2 escalated tickets
        const escalated = currentTickets.filter(t => t.status === 'escalated');
        if (escalated.length > lastEscalatedCount) {
            showNotification(`⚠️ Warning: New ticket escalated! Contact L2 Support immediately at L2-operations@nordea.com`, 'error');
        }
        lastEscalatedCount = escalated.length;
        
        // Update L2 tab badge counter
        const badge = document.getElementById('escalated-badge');
        if (badge) {
            if (lastEscalatedCount > 0) {
                badge.textContent = lastEscalatedCount;
                badge.style.display = 'inline-flex';
            } else {
                badge.style.display = 'none';
            }
        }

        // Fetch suppressed / non-ticketing alerts
        try {
            const resSuppressed = await fetch(`${API_BASE}/api/tickets?status=suppressed`);
            const dataSuppressed = await resSuppressed.json();
            suppressedAlerts = dataSuppressed.tickets || [];
            
            // Update non-ticketing badge count
            const suppressedBadge = document.getElementById('non-ticketing-badge');
            if (suppressedBadge) {
                if (suppressedAlerts.length > 0) {
                    suppressedBadge.textContent = suppressedAlerts.length;
                    suppressedBadge.style.display = 'inline-flex';
                } else {
                    suppressedBadge.style.display = 'none';
                }
            }
        } catch (e) {
            console.error('Failed to fetch suppressed alerts:', e);
        }
        
        // Keep active tab content updated in real-time
        if (currentActiveTab === 'history') {
            renderHistoryMatrix();
        } else if (currentActiveTab === 'escalated') {
            renderEscalatedTasks();
        } else if (currentActiveTab === 'non_ticketing') {
            renderNonTicketingAlerts();
        }
        
        applyFilters();
    } catch (e) {
        console.error('Tickets error:', e);
    }
}

function applyFilters() {
    const statusSelect = document.getElementById('status-filter-select');
    const durationSelect = document.getElementById('duration-filter-select');
    
    const statusValue = statusSelect ? statusSelect.value : 'all';
    const durationValue = durationSelect ? durationSelect.value : 'all';
    
    let filtered = currentTickets;
    
    // Status Filter
    if (statusValue === 'resolved') {
        filtered = filtered.filter(t => t.status === 'resolved' || t.status === 'closed');
    } else if (statusValue === 'awaiting_approval') {
        filtered = filtered.filter(t => t.status === 'awaiting_approval');
    } else if (statusValue === 'escalated') {
        filtered = filtered.filter(t => t.status === 'escalated');
    } else if (statusValue === 'other') {
        const otherStatuses = ['new', 'triaged', 'investigating', 'diagnosed', 'auto_healing', 'manual_remediation'];
        filtered = filtered.filter(t => otherStatuses.includes(t.status));
    }
    
    // Duration Filter
    if (durationValue !== 'all') {
        const now = new Date();
        filtered = filtered.filter(t => {
            if (!t.created_at) return true;
            let dateStr = t.created_at;
            if (dateStr.indexOf('T') === -1) dateStr = dateStr.replace(' ', 'T');
            if (!dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.match(/-\d{2}:\d{2}$/)) dateStr += 'Z';
            const tDate = new Date(dateStr); 
            const diffMs = now - tDate;
            
            if (durationValue === '1h') return diffMs <= 60 * 60 * 1000;
            if (durationValue === '24h') return diffMs <= 24 * 60 * 60 * 1000;
            if (durationValue === '7d') return diffMs <= 7 * 24 * 60 * 60 * 1000;
            return true;
        });
    }
    
    renderTicketList(filtered);
}

// ── Tab Management ──────────────────────────────
function switchTab(tabId) {
    currentActiveTab = tabId;
    
    // Toggle active tab classes
    document.querySelectorAll('.nav-tab').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-content-section').forEach(sec => {
        sec.classList.remove('active');
        sec.style.display = 'none';
    });
    
    const activeBtn = document.getElementById(`tab-btn-${tabId}`);
    if (activeBtn) activeBtn.classList.add('active');
    
    const activeSec = document.getElementById(`tab-content-${tabId}`);
    if (activeSec) {
        activeSec.classList.add('active');
        activeSec.style.display = 'block';
    }
    
    // Trigger render logic based on active tab
    if (tabId === 'history') {
        renderHistoryMatrix();
    } else if (tabId === 'escalated') {
        renderEscalatedTasks();
    } else if (tabId === 'non_ticketing') {
        renderNonTicketingAlerts();
    }
}

function renderHistoryMatrix() {
    const container = document.getElementById('matrix-list-body');
    if (!container) return;
    
    if (currentTickets.length === 0) {
        container.innerHTML = `
            <tr>
                <td colspan="7" class="empty-state">No incidents in the system history.</td>
            </tr>`;
        return;
    }
    
    container.innerHTML = currentTickets.map(t => {
        let mode = 'Pending / Triage';
        let modeClass = 'p4';
        let mappedScript = 'None';
        
        try {
            const meta = JSON.parse(t.metadata || '{}');
            mappedScript = meta.recommended_script || 'None';
        } catch (e) {}

        if (t.status === 'resolved' || t.status === 'closed') {
            if (t.confidence_score >= 0.7) {
                mode = 'Auto-Healed';
                modeClass = 'success';
            } else {
                mode = 'Manual Intervention';
                modeClass = 'warning';
                if (mappedScript === 'None') {
                    mappedScript = `${t.id}_remediate.py`;
                }
            }
        } else if (t.status === 'escalated') {
            mode = 'Escalated to L2';
            modeClass = 'danger';
        } else if (['investigating', 'diagnosed', 'auto_healing', 'manual_remediation'].includes(t.status)) {
            mode = 'Self-Healing Active';
            modeClass = 'p3';
        }
        
        const similarity = t.confidence_score !== undefined ? `${((t.confidence_score || 0) * 100).toFixed(0)}%` : 'N/A';
        const resolutionText = t.resolution || t.recommended_action || 'Pending resolution details...';
        
        return `
            <tr>
                <td class="ticket-id">${escapeHtml(t.id)}</td>
                <td class="ticket-title">${escapeHtml(t.title)}</td>
                <td>${escapeHtml(t.category || 'N/A')}</td>
                <td><span class="priority-badge priority-${modeClass}">${mode}</span></td>
                <td style="white-space: normal; word-break: break-word; max-width: 300px; color: var(--text-primary);">
                    ${escapeHtml(resolutionText)}
                </td>
                <td class="ticket-id" style="font-family: monospace; font-size: 0.75rem;">${escapeHtml(mappedScript)}</td>
                <td><span class="confidence" style="font-weight:600; color:var(--accent-cyan);">${similarity}</span></td>
            </tr>
        `;
    }).join('');
}

function renderEscalatedTasks() {
    const container = document.getElementById('escalated-list-body');
    if (!container) return;
    
    const escalated = currentTickets.filter(t => t.status === 'escalated');
    
    if (escalated.length === 0) {
        container.innerHTML = `
            <tr>
                <td colspan="6" class="empty-state">No escalated tasks currently active. All systems stable.</td>
            </tr>`;
        return;
    }
    
    container.innerHTML = escalated.map(t => {
        let escalationNote = 'Rejected by operator - escalated for L2 response';
        try {
            const meta = JSON.parse(t.metadata || '{}');
            if (meta.comment) escalationNote = meta.comment;
        } catch (e) {}

        return `
            <tr>
                <td class="ticket-id">${escapeHtml(t.id)}</td>
                <td class="ticket-title">${escapeHtml(t.title)}</td>
                <td><span class="priority-badge priority-${t.priority}">${(t.priority || '').toUpperCase()}</span></td>
                <td>${timeAgo(t.updated_at)}</td>
                <td style="white-space: normal; word-break: break-word; max-width: 250px; color: #fca5a5;">
                    ${escapeHtml(t.root_cause || 'Investigating...')}
                </td>
                <td style="white-space: normal; word-break: break-word; max-width: 250px; color: var(--text-secondary);">
                    ${escapeHtml(escalationNote)}
                </td>
            </tr>
        `;
    }).join('');
}

async function searchIncidents() {
    const q = document.getElementById('incident-search-input').value.trim();
    if (q) {
        currentSearchQuery = q;
        await refreshTickets();
    }
}

async function clearSearch() {
    document.getElementById('incident-search-input').value = '';
    currentSearchQuery = '';
    await refreshTickets();
}

function renderTicketList(tickets) {
    const container = document.getElementById('ticket-list-body');
    if (!container) return;

    if (tickets.length === 0) {
        container.innerHTML = `
            <tr>
                <td colspan="6" class="empty-state">
                    <div class="empty-state-content">
                        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity="0.3">
                            <circle cx="12" cy="12" r="10"/>
                            <line x1="12" y1="8" x2="12" y2="12"/>
                            <line x1="12" y1="16" x2="12.01" y2="16"/>
                        </svg>
                        <p>${currentSearchQuery ? 'No incidents matched your search.' : 'No incidents yet. Click <strong>"Simulate Alert"</strong> to get started!'}</p>
                    </div>
                </td>
            </tr>`;
        return;
    }

    container.innerHTML = tickets.map(t => `
        <tr class="ticket-row ${selectedTicketId === t.id ? 'selected' : ''}" onclick="showTicketDetail('${t.id}')">
            <td class="ticket-id">${escapeHtml(t.id)}</td>
            <td class="ticket-title">${escapeHtml(t.title)}</td>
            <td><span class="priority-badge priority-${t.priority}">${(t.priority || '').toUpperCase()}</span></td>
            <td><span class="status-badge status-${t.status}"><span class="status-dot"></span>${formatStatus(t.status)}</span></td>
            <td>${escapeHtml(t.category || 'N/A')}</td>
            <td>${timeAgo(t.created_at)}</td>
        </tr>
    `).join('');
}

// ── Ticket Detail ───────────────────────────────
async function showTicketDetail(ticketId) {
    selectedTicketId = ticketId;
    try {
        const res = await fetch(`${API_BASE}/api/tickets/${ticketId}`);
        const data = await res.json();
        renderTicketDetail(data.ticket, data.timeline);

        // Highlight selected row
        document.querySelectorAll('.ticket-row').forEach(r => r.classList.remove('selected'));
        const rows = document.querySelectorAll('.ticket-row');
        rows.forEach(row => {
            if (row.querySelector('.ticket-id')?.textContent === ticketId) {
                row.classList.add('selected');
            }
        });
    } catch (e) {
        console.error('Detail error:', e);
    }
}

function renderTicketDetail(ticket, timeline) {
    const container = document.getElementById('ticket-detail');
    if (!container || !ticket) return;

    const isAwaitingApproval = ticket.status === 'awaiting_approval';

    container.innerHTML = `
        <div class="detail-header">
            <div class="detail-title-row">
                <h2>${escapeHtml(ticket.id)}</h2>
                <div style="display: flex; gap: 8px; align-items: center;">
                    <button class="btn-business-translate" onclick="openBusinessModal('${ticket.id}')" style="background: rgba(6, 182, 212, 0.12); border: 1px solid rgba(6, 182, 212, 0.3); color: var(--accent-cyan); padding: 4px 10px; border-radius: 20px; font-size: 0.7rem; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; transition: var(--transition); outline: none;" onmouseover="this.style.background='rgba(6, 182, 212, 0.22)'; this.style.borderColor='rgba(6, 182, 212, 0.5)';" onmouseout="this.style.background='rgba(6, 182, 212, 0.12)'; this.style.borderColor='rgba(6, 182, 212, 0.3)';">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
                        Business Translation
                    </button>
                    <button class="btn-maximize-detail" onclick="openAuditModal('${ticket.id}')" style="background: rgba(139, 92, 246, 0.12); border: 1px solid rgba(139, 92, 246, 0.3); color: var(--accent-purple); padding: 4px 10px; border-radius: 20px; font-size: 0.7rem; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; transition: var(--transition); outline: none;" onmouseover="this.style.background='rgba(139, 92, 246, 0.22)'; this.style.borderColor='rgba(139, 92, 246, 0.5)';" onmouseout="this.style.background='rgba(139, 92, 246, 0.12)'; this.style.borderColor='rgba(139, 92, 246, 0.3)';">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h6v6"/><path d="M9 21H3v-6"/><path d="M21 3l-7 7"/><path d="M3 21l7-7"/></svg>
                        Maximize View
                    </button>
                    <span class="status-badge status-${ticket.status}"><span class="status-dot"></span>${formatStatus(ticket.status)}</span>
                </div>
            </div>
            <h3>${escapeHtml(ticket.title)}</h3>
        </div>

        <div class="detail-meta">
            <div class="meta-item">
                <span class="meta-label">Priority</span>
                <span class="priority-badge priority-${ticket.priority}">${(ticket.priority || '').toUpperCase()}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Category</span>
                <span>${escapeHtml(ticket.category || 'N/A')}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Source</span>
                <span>${escapeHtml(ticket.source || 'N/A')}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Confidence</span>
                <span class="confidence">${((ticket.confidence_score || 0) * 100).toFixed(0)}%</span>
            </div>
        </div>

        <div class="detail-section">
            <h4>Description</h4>
            <p>${escapeHtml(ticket.description || 'No description')}</p>
        </div>

        ${ticket.root_cause ? `
        <div class="detail-section">
            <h4>Root Cause</h4>
            <p class="root-cause">${escapeHtml(ticket.root_cause)}</p>
        </div>` : ''}

        ${ticket.recommended_action ? `
        <div class="detail-section">
            <h4>Recommended Action</h4>
            <p class="recommended-action">${escapeHtml(ticket.recommended_action)}</p>
        </div>` : ''}

        ${ticket.resolution ? `
        <div class="detail-section">
            <h4>Resolution</h4>
            <p class="resolution">${escapeHtml(ticket.resolution)}</p>
        </div>` : ''}

        ${isAwaitingApproval ? `
        <div class="approval-panel" style="background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.2); padding: 1.2rem; border-radius: 8px; margin-top: 1rem;">
            <h4 style="color: #f59e0b; display: flex; align-items: center; gap: 0.5rem; margin-top: 0;">⚠️ Human Operator Intervention Required</h4>
            <p style="margin-bottom: 1rem; font-size: 0.9rem; color: #d1d5db;">Classified below confidence threshold. Please provide the resolution process so the ML model can execute it in the background and learn from it.</p>
            
            <div style="margin-bottom: 0.8rem;">
                <label style="display: block; font-size: 0.8rem; color: #9ca3af; margin-bottom: 0.3rem;">Remediation Input Type</label>
                <select id="approval-remediation-type" style="width: 100%; padding: 0.5rem; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.15); color: #fff; border-radius: 6px; outline: none;">
                    <option value="text">Natural Language Instructions / Commands</option>
                    <option value="python">Custom Python Script Code</option>
                </select>
            </div>
            
            <div style="margin-bottom: 0.8rem;">
                <label style="display: block; font-size: 0.8rem; color: #9ca3af; margin-bottom: 0.3rem;">Remediation Process / Code</label>
                <textarea id="approval-remediation" rows="4" placeholder="Enter process, commands, or python code... (e.g. 'please restart service nginx' or write python code)" style="width: 100%; padding: 0.6rem; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.15); color: #fff; border-radius: 6px; font-family: monospace; font-size: 0.85rem; resize: vertical; outline: none;"></textarea>
            </div>

            <div style="margin-bottom: 1rem;">
                <label style="display: block; font-size: 0.8rem; color: #9ca3af; margin-bottom: 0.3rem;">Operator Action Notes / Comments</label>
                <input type="text" id="approval-comment" placeholder="Add operator comment (optional)..." style="width: 100%; padding: 0.5rem 0.6rem; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.15); color: #fff; border-radius: 6px; outline: none;">
            </div>

            <div class="approval-buttons" style="display: flex; gap: 0.8rem;">
                <button class="btn btn-approve" onclick="approveTicket('${ticket.id}', true)" style="flex: 1; padding: 0.6rem; border-radius: 6px; background: #10b981; color: #fff; border: none; cursor: pointer; font-weight: 500; display: flex; align-items: center; justify-content: center; gap: 0.4rem;">✓ Approve &amp; Remediate</button>
                <button class="btn btn-reject" onclick="approveTicket('${ticket.id}', false)" style="flex: 1; padding: 0.6rem; border-radius: 6px; background: #ef4444; color: #fff; border: none; cursor: pointer; font-weight: 500; display: flex; align-items: center; justify-content: center; gap: 0.4rem;">✗ Reject &amp; Escalate</button>
            </div>
        </div>` : ''}

        <div class="detail-section">
            <h4>Timeline</h4>
            <div class="timeline">
                ${(timeline || []).map((entry, i) => `
                    <div class="timeline-entry agent-${entry.agent_id || 'system'}" style="animation-delay: ${i * 0.06}s">
                        <div class="timeline-dot"></div>
                        <div class="timeline-content">
                            <div class="timeline-header">
                                <span class="timeline-agent">${escapeHtml(entry.agent_name || 'System')}</span>
                                <span class="timeline-action">${formatAction(entry.action)}</span>
                                <span class="timeline-time">${timeAgo(entry.timestamp)}</span>
                            </div>
                            <p class="timeline-details">${escapeHtml(entry.details || '')}</p>
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

// ── Approval ────────────────────────────────────
async function approveTicket(ticketId, approved) {
    const comment = document.getElementById('approval-comment')?.value || '';
    const remediation = document.getElementById('approval-remediation')?.value || '';
    const remediation_type = document.getElementById('approval-remediation-type')?.value || 'text';
    
    if (approved && !remediation.trim()) {
        showNotification('Please specify the remediation process or instructions', 'warning');
        return;
    }

    // --- FIX 3: Immediately disable buttons and show loading state to prevent double-submit ---
    const approveBtn = document.querySelector('.btn-approve');
    const rejectBtn = document.querySelector('.btn-reject');
    if (approveBtn) { approveBtn.disabled = true; approveBtn.style.opacity = '0.6'; approveBtn.innerHTML = approved ? '⏳ Processing...' : '✓ Approve & Remediate'; }
    if (rejectBtn) { rejectBtn.disabled = true; rejectBtn.style.opacity = '0.6'; rejectBtn.innerHTML = !approved ? '⏳ Escalating...' : '✗ Reject & Escalate'; }
    
    try {
        const res = await fetch(`${API_BASE}/api/tickets/${ticketId}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                approved, 
                comment,
                remediation_steps: remediation,
                remediation_type: remediation_type
            })
        });

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || `HTTP ${res.status}`);
        }

        showNotification(
            approved
                ? '✅ Ticket approved. Generating and executing remediation script in background...'
                : '⚠️ Ticket rejected and escalated to L2',
            approved ? 'success' : 'warning'
        );
        await refreshTickets();
        setTimeout(() => showTicketDetail(ticketId), 1000);
    } catch (e) {
        showNotification(`Error processing approval: ${e.message}`, 'error');
        // Re-enable buttons on failure so operator can retry
        if (approveBtn) { approveBtn.disabled = false; approveBtn.style.opacity = '1'; approveBtn.innerHTML = '✓ Approve & Remediate'; }
        if (rejectBtn) { rejectBtn.disabled = false; rejectBtn.style.opacity = '1'; rejectBtn.innerHTML = '✗ Reject & Escalate'; }
    }
}

// ── Agents ──────────────────────────────────────
async function refreshAgents() {
    try {
        const res = await fetch(`${API_BASE}/api/agents/status`);
        const data = await res.json();
        updateAgentNodes(data.agents || []);
    } catch (e) {
        console.error('Agents error:', e);
    }
}

function updateAgentNodes(agents) {
    const idMap = {
        'agent-01': 'ticket_creator',
        'agent-02': 'root_cause',
        'agent-03': 'knowledge_base',
        'agent-04': 'self_healing',
        'agent-05': 'remediation'
    };
    agents.forEach(agent => {
        const elementId = `agent-node-${idMap[agent.agent_id] || agent.agent_id}`;
        const node = document.getElementById(elementId);
        if (node) {
            const isActive = agent.status === 'processing';
            node.classList.toggle('active', isActive);
            const taskCount = node.querySelector('.agent-tasks');
            if (taskCount) taskCount.textContent = agent.tasks_completed || 0;
        }
    });
}

// ── Simulate ────────────────────────────────────
async function simulateAlert(templateIndex = null) {
    try {
        const body = templateIndex !== null ? { template_index: templateIndex } : {};
        const res = await fetch(`${API_BASE}/api/simulate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await res.json();
        showNotification(
            `Alert simulated: ${data.alerts?.[0]?.title || 'New incident triggered'}`,
            'info'
        );

        // Refresh after a short delay to see the ticket appear
        setTimeout(refreshTickets, 1500);
        setTimeout(refreshStats, 1500);
        setTimeout(refreshAgents, 2000);
    } catch (e) {
        showNotification('Error simulating alert', 'error');
    }
}

function toggleSimulateMenu() {
    const menu = document.getElementById('simulate-menu');
    if (menu) menu.classList.toggle('show');
}

async function loadSimulateTemplates() {
    try {
        const res = await fetch(`${API_BASE}/api/alerts/templates`);
        const data = await res.json();
        const menu = document.getElementById('simulate-menu-items');
        if (menu && data.templates) {
            menu.innerHTML = data.templates.map(t => `
                <button class="simulate-item severity-${t.severity}" onclick="simulateAlert(${t.index}); toggleSimulateMenu();">
                    <span class="severity-indicator"></span>
                    ${escapeHtml(t.title)}
                </button>
            `).join('');
        }
    } catch (e) {
        console.error('Templates error:', e);
        const menu = document.getElementById('simulate-menu-items');
        if (menu) {
            menu.innerHTML = '<div class="simulate-loading">Could not load templates</div>';
        }
    }
}

// ── Utility Functions ───────────────────────────
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function formatStatus(status) {
    if (!status) return 'Unknown';
    return status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

function formatAction(action) {
    if (!action) return '';
    return action.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

function timeAgo(timestamp) {
    if (!timestamp) return 'N/A';
    const now = new Date();
    const then = new Date(timestamp);
    const diff = Math.floor((now - then) / 1000);

    if (diff < 0) return 'just now';
    if (diff < 5) return 'just now';
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

function updateBreakdown(elementId, data) {
    const el = document.getElementById(elementId);
    if (!el || !data) return;
    const entries = Object.entries(data);
    if (entries.length === 0) {
        el.innerHTML = '<span class="empty-breakdown">No data</span>';
        return;
    }
    el.innerHTML = entries.map(([key, val]) =>
        `<div class="breakdown-item">
            <span class="breakdown-label">${escapeHtml(key)}</span>
            <span class="breakdown-value">${val}</span>
        </div>`
    ).join('');
}

// ── Notifications ───────────────────────────────
function showNotification(message, type = 'info') {
    let container = document.getElementById('notifications');
    if (!container) {
        container = document.createElement('div');
        container.id = 'notifications';
        document.body.appendChild(container);
    }

    const notif = document.createElement('div');
    notif.className = `notification notification-${type}`;
    notif.innerHTML = `<span>${escapeHtml(message)}</span><button onclick="this.parentElement.remove()">&times;</button>`;
    container.appendChild(notif);

    // Trigger show animation
    requestAnimationFrame(() => {
        notif.classList.add('show');
    });

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        notif.classList.remove('show');
        setTimeout(() => notif.remove(), 300);
    }, 5000);
}

// ── Splunk Simulator ───────────────────────────

async function injectSplunkLog() {
    const rawLog = document.getElementById('splunk-log-input').value;
    if (!rawLog) return;
    
    try {
        const url = `${API_BASE}/api/webhooks/splunk`;
        const payload = {
            result: {
                _raw: rawLog,
                host: "splunk-simulated-host",
                source: "splunk_web_generator"
            },
            search_name: "Simulated Splunk Log Alert"
        };
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        showNotification(data.message || 'Log injected successfully', 'success');
        setTimeout(refreshTickets, 1500);
    } catch (e) {
        showNotification('Failed to inject log', 'error');
    }
}

// ── Business Translation Modal Controls ───────────────────────────

function openBusinessModal(ticketId) {
    const ticket = currentTickets.find(t => t.id === ticketId) || suppressedAlerts.find(t => t.id === ticketId);
    if (!ticket) return;

    const modal = document.getElementById('business-modal');
    if (!modal) return;

    // Set simple details
    document.getElementById('biz-category').textContent = ticket.category || 'General';
    document.getElementById('biz-title').textContent = ticket.title || 'System Incident';

    // Translate technical indicators
    const translation = getBusinessTranslation(ticket);
    document.getElementById('biz-explanation').textContent = translation.explanation;
    document.getElementById('biz-impact').textContent = translation.impact;
    document.getElementById('biz-action').textContent = translation.action;

    // Show modal
    modal.classList.add('show');
}

function closeBusinessModal(event) {
    const modal = document.getElementById('business-modal');
    if (modal) {
        modal.classList.remove('show');
    }
}

function getBusinessTranslation(ticket) {
    const title = (ticket.title || '').toLowerCase();
    const desc = (ticket.description || '').toLowerCase();
    const status = ticket.status || '';
    
    let explanation = "The system has detected an anomaly in the logs. A background check has been initiated to inspect system services.";
    let impact = "No direct customer impact has been reported yet, but performance might be slightly degraded.";
    let action = "Helix Agents are tracking system health and standby for automated recovery steps.";

    if (title.includes('cpu') || desc.includes('cpu') || desc.includes('processor')) {
        explanation = "The main server's processor (CPU) is working at maximum capacity, similar to a computer running too many heavy applications at once.";
        impact = "Users might experience minor delays or slow loading times when loading pages or trying to checkout.";
        action = "Helix Auto-Healing Agent is scanning active processes to locate any runaway services and will automatically optimize resource distribution.";
    } 
    else if (title.includes('disk') || desc.includes('disk') || desc.includes('space') || desc.includes('partition') || desc.includes('storage')) {
        explanation = "The server's hard drive space is almost completely full, leaving no room to save log files or process new local operations.";
        impact = "New orders, updates, or logins might fail to register if the database is unable to write new transaction logs.";
        action = "Helix Self-Healing Agent has triggered a disk-space cleanup sequence: compressing old archived logs, emptying temp folders, and rotating file sizes.";
    }
    else if (title.includes('oom') || title.includes('memory') || desc.includes('memory') || desc.includes('leak') || desc.includes('heap')) {
        explanation = "The application ran out of temporary memory space (OOM / Out of Memory) and was forced to crash to prevent server instability.";
        impact = "The affected app instance is temporarily offline, which could cause brief interruptions or errors for active users.";
        action = "Helix Self-Healing Agent is preparing to clean up stale process files and restart the application instance safely.";
    }
    else if (title.includes('pool') || title.includes('connection') || desc.includes('connection pool') || desc.includes('database connection')) {
        explanation = "The database has run out of available connection lines, meaning it is too busy to handle any new database queries.";
        impact = "Database queries will time out, meaning users will see errors during search, login, or saving transactions.";
        action = "Helix Auto-Healing Agent is restarting the connection manager pool and terminating any hung/idle connections to free up lines.";
    }
    else if (title.includes('ssl') || title.includes('certificate') || desc.includes('ssl') || desc.includes('expiry')) {
        explanation = "The secure lock certificate (SSL/TLS) for the platform is expiring soon, which is necessary to keep web connections encrypted.";
        impact = "If expired, web browsers will block access to the website with security warning messages to visitors.";
        action = "Helix automated renewal script has been queued to request a brand new security certificate and update the web gateways.";
    }
    else if (title.includes('brute') || title.includes('force') || title.includes('login failed') || desc.includes('auth.log')) {
        explanation = "An unusual spike of failed login attempts was detected from external networks, resembling a brute-force hacking attempt.";
        impact = "No security breach has occurred, but login performance may suffer, and accounts might be locked for safety.";
        action = "Helix Remediation Agent is adding the offending IP addresses to the firewall blocklist to prevent further access.";
    }
    else if (title.includes('latency') || title.includes('slow') || desc.includes('latency') || desc.includes('slow') || desc.includes('timeout')) {
        explanation = "Network or API response times are significantly slower than normal, causing requests to take a long time to complete.";
        impact = "Customers will face page loading lag. Integration partners might encounter gateway timeouts.";
        action = "Helix is analyzing network routes, checking database indexes, and will restart application services if lag persists.";
    }
    else if (title.includes('abend') || title.includes('fatal') || title.includes('crash') || desc.includes('abend') || desc.includes('fatal') || desc.includes('crash')) {
        explanation = "The software encountered a critical internal error and terminated abnormally (crashed).";
        impact = "Transactions processed by this application module are stalled until the service is restarted.";
        action = "Helix is checking for buffer lockups, cleaning temporary file directories, and restarting the service.";
    }
    
    // Status specifics
    if (status === 'resolved' || status === 'closed') {
        action = "Resolved. The Helix AIOps system has successfully completed remediation and restored the service to a healthy state.";
    } else if (status === 'escalated') {
        action = "Escalated. The issue required advanced system intervention and was escalated to Level 2 engineering support.";
    } else if (status === 'awaiting_approval') {
        action = "Awaiting Operator Review. An operator has been notified to check the diagnosis and approve the remediation script.";
    }

    return { explanation, impact, action };
}

// ── Audit Console Modal Controls ───────────────────────────

async function openAuditModal(ticketId) {
    const ticket = currentTickets.find(t => t.id === ticketId) || suppressedAlerts.find(t => t.id === ticketId);
    if (!ticket) return;

    const modal = document.getElementById('audit-modal');
    if (!modal) return;

    // Fill standard metadata fields
    document.getElementById('audit-ticket-id').textContent = ticket.id;
    document.getElementById('audit-ticket-title').textContent = ticket.title;
    document.getElementById('audit-category').textContent = ticket.category || 'N/A';
    document.getElementById('audit-source').textContent = ticket.source || 'N/A';
    document.getElementById('audit-confidence').textContent = ticket.confidence_score !== undefined ? `${((ticket.confidence_score || 0) * 100).toFixed(0)}%` : 'N/A';
    document.getElementById('audit-sla').textContent = ticket.sla_deadline ? timeAgo(ticket.sla_deadline) : 'N/A';

    // Badge styling matching priority & status
    const priorityEl = document.getElementById('audit-priority');
    priorityEl.className = `priority-badge priority-${ticket.priority}`;
    priorityEl.textContent = (ticket.priority || '').toUpperCase();

    const statusEl = document.getElementById('audit-status');
    statusEl.className = `status-badge status-${ticket.status}`;
    statusEl.innerHTML = `<span class="status-dot"></span>${formatStatus(ticket.status)}`;

    // Time values
    document.getElementById('audit-created-at').textContent = formatTimestamp(ticket.created_at);
    document.getElementById('audit-updated-at').textContent = formatTimestamp(ticket.updated_at);
    document.getElementById('audit-resolved-at').textContent = ticket.resolved_at ? formatTimestamp(ticket.resolved_at) : 'Active / Unresolved';

    // Rich description / root cause / solution
    document.getElementById('audit-description').textContent = ticket.description || 'No description';
    document.getElementById('audit-root-cause').textContent = ticket.root_cause || 'Investigation details pending...';
    document.getElementById('audit-solution').textContent = ticket.resolution || ticket.recommended_action || 'Remediation solution pending...';

    // Fetch timeline detail
    try {
        const res = await fetch(`${API_BASE}/api/tickets/${ticketId}`);
        const data = await res.json();
        renderAuditTimeline(data.timeline || []);
    } catch (e) {
        console.error('Audit timeline fetch error:', e);
        document.getElementById('audit-timeline-entries').innerHTML = '<div class="empty-state">Could not load timeline trail.</div>';
    }

    // Show modal
    modal.classList.add('show');
}

function closeAuditModal(event) {
    const modal = document.getElementById('audit-modal');
    if (modal) {
        modal.classList.remove('show');
    }
}

function renderAuditTimeline(timeline) {
    const container = document.getElementById('audit-timeline-entries');
    if (!container) return;

    if (timeline.length === 0) {
        container.innerHTML = '<div class="empty-state">No agent entries recorded in timeline.</div>';
        return;
    }

    container.innerHTML = timeline.map((entry, i) => `
        <div class="timeline-entry agent-${entry.agent_id || 'system'}" style="animation-delay: ${i * 0.05}s">
            <div class="timeline-dot"></div>
            <div class="timeline-content">
                <div class="timeline-header">
                    <span class="timeline-agent">${escapeHtml(entry.agent_name || 'System')}</span>
                    <span class="timeline-action">${formatAction(entry.action)}</span>
                    <span class="timeline-time">${formatTimestamp(entry.timestamp)}</span>
                </div>
                <p class="timeline-details" style="font-size: 0.8rem; margin-top: 4px; color: var(--text-secondary);">${escapeHtml(entry.details || '')}</p>
            </div>
        </div>
    `).join('');
}

function formatTimestamp(isoString) {
    if (!isoString) return 'N/A';
    try {
        const d = new Date(isoString);
        return d.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    } catch (e) {
        return isoString;
    }
}

function renderNonTicketingAlerts() {
    const container = document.getElementById('non-ticketing-list-body');
    if (!container) return;
    
    if (suppressedAlerts.length === 0) {
        container.innerHTML = `
            <tr>
                <td colspan="5" class="empty-state">No suppressed non-ticketing alerts. All systems stable.</td>
            </tr>`;
        return;
    }
    
    container.innerHTML = suppressedAlerts.map(t => {
        let reason = 'Suppressed - developer environment logs';
        if (t.root_cause && t.root_cause.includes('Bypassed:')) {
            reason = t.root_cause.replace('Bypassed: Non-ticketing alert. Reason: ', '');
        }
        let host = 'dev-host';
        try {
            const meta = JSON.parse(t.metadata || '{}');
            host = meta.host || 'dev-host';
        } catch (e) {}

        return `
            <tr class="ticket-row" onclick="openAuditModal('${t.id}')" style="cursor: pointer;">
                <td class="ticket-id">${escapeHtml(t.id)}</td>
                <td class="ticket-title">${escapeHtml(t.title)}</td>
                <td><span class="priority-badge priority-p4" style="text-transform:none; font-family:monospace; border-radius: 4px; padding: 2px 6px;">${escapeHtml(host)}</span></td>
                <td style="color: var(--text-secondary); font-weight: 500;">
                    🛡️ ${escapeHtml(reason)}
                </td>
                <td>${formatTimestamp(t.created_at)}</td>
            </tr>
        `;
    }).join('');
}

// ── Splunk Settings (removed from UI) ───────────
// Backend Splunk polling continues to run via main.py background task.
// These are kept as no-ops to prevent any reference errors.
function loadSplunkUiSettings() {}
function loadSplunkConfig() {}


// ── Root Cause Feedback ──────────────────────────────
function toggleRCFixInput() {
    const sel = document.getElementById('rc-feedback-select');
    const fixDiv = document.getElementById('rc-feedback-fix-div');
    if (sel.value === 'no') {
        fixDiv.style.display = 'block';
    } else {
        fixDiv.style.display = 'none';
    }
}

async function submitRootCauseFeedback() {
    const ticketId = document.getElementById('audit-ticket-id').textContent;
    const isCorrect = document.getElementById('rc-feedback-select').value;
    const correctRootCause = document.getElementById('rc-feedback-text').value;
    
    if (!isCorrect) {
        alert("Please select Yes or No.");
        return;
    }
    
    if (isCorrect === 'no' && !correctRootCause.trim()) {
        alert("Please provide the correct root cause.");
        return;
    }
    
    try {
        const res = await fetch(`${API_BASE}/api/tickets/${ticketId}/root_cause_feedback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                is_correct: isCorrect === 'yes',
                correct_root_cause: isCorrect === 'yes' ? null : correctRootCause
            })
        });
        
        if (res.ok) {
            alert("Feedback submitted successfully! The ML model will learn from this.");
            document.getElementById('rc-feedback-select').value = '';
            document.getElementById('rc-feedback-fix-div').style.display = 'none';
            document.getElementById('rc-feedback-text').value = '';
        } else {
            alert("Failed to submit feedback.");
        }
    } catch (e) {
        console.error(e);
        alert("Error submitting feedback.");
    }
}


