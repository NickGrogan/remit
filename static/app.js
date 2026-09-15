/**
 * REMIT Insider — Frontend Application
 * Real-time alert feed with SSE, filtering, and flash notifications.
 */

// ── State ──────────────────────────────────────────
let allAlerts = [];
let currentFilter = 'all';
let lastSeenId = null;
let sseSource = null;
let audioCtx = null;

// ── Clock ──────────────────────────────────────────
function updateClock() {
    const now = new Date();
    document.getElementById('clock').textContent = now.toUTCString().slice(17, 25);
    document.getElementById('date-display').textContent = now.toUTCString().slice(0, 16);
}
setInterval(updateClock, 1000);
updateClock();

// ── Audio Chime for Flash Alerts ───────────────────
function playFlashChime() {
    try {
        if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.frequency.setValueAtTime(880, audioCtx.currentTime);
        osc.frequency.setValueAtTime(1100, audioCtx.currentTime + 0.1);
        osc.frequency.setValueAtTime(880, audioCtx.currentTime + 0.2);
        gain.gain.setValueAtTime(0.3, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.5);
        osc.start(audioCtx.currentTime);
        osc.stop(audioCtx.currentTime + 0.5);
    } catch (e) { /* Audio not available */ }
}

// ── Flash Overlay ──────────────────────────────────
function showFlash(headline) {
    const overlay = document.getElementById('flash-overlay');
    document.getElementById('flash-text').textContent = headline;
    overlay.classList.remove('hidden');
    playFlashChime();
    // Auto-dismiss after 15s
    setTimeout(() => overlay.classList.add('hidden'), 15000);
}

function dismissFlash() {
    document.getElementById('flash-overlay').classList.add('hidden');
}

// ── Stats Update ───────────────────────────────────
function updateStats(stats) {
    const mwEl = document.getElementById('stat-mw');
    const outEl = document.getElementById('stat-outages');
    const flashEl = document.getElementById('stat-flash');
    const pollEl = document.getElementById('stat-poll');

    mwEl.textContent = stats.total_mw_offline != null
        ? Number(stats.total_mw_offline).toLocaleString('en-GB', { maximumFractionDigits: 0 })
        : '—';
    outEl.textContent = stats.active_outages ?? '—';
    flashEl.textContent = stats.flash_count ?? '—';

    if (stats.last_poll) {
        const d = new Date(stats.last_poll);
        pollEl.textContent = d.toUTCString().slice(17, 25) + ' UTC';
    }
}

// ── Ticker Tape ────────────────────────────────────
function updateTicker(alerts) {
    const tape = document.getElementById('ticker-tape');
    if (!alerts.length) return;

    const items = alerts.slice(0, 15).map(a => {
        const sevClass = {
            'FLASH': 'text-red-400',
            'MAJOR': 'text-orange-400',
            'MINOR': 'text-blue-400',
        }[a.severity] || 'text-green-400';

        if (a.event_type === 'RETURN') {
            return `<span class="text-green-400 font-mono text-xs">▲ ${a.asset_name} RETURNED ${a.normal_mw}MW</span>`;
        }
        return `<span class="${sevClass} font-mono text-xs">▼ ${a.asset_name} ${a.impact_mw}MW ${a.unavailability_type}</span>`;
    });

    // Duplicate for seamless scroll
    tape.innerHTML = items.join('<span class="text-terminal-border mx-2">│</span>') +
        '<span class="text-terminal-border mx-6">│</span>' +
        items.join('<span class="text-terminal-border mx-2">│</span>');
}

// ── Alert Card Rendering ───────────────────────────
function severityBorderClass(severity, eventType) {
    if (eventType === 'RETURN') return 'alert-card-return';
    switch (severity) {
        case 'FLASH': return 'alert-card-flash';
        case 'MAJOR': return 'alert-card-major';
        default: return 'alert-card-minor';
    }
}

function severityBadge(severity) {
    const cfg = {
        'FLASH': { bg: 'bg-red-500/20', text: 'text-red-400', border: 'border-red-500/30', label: '⚡ FLASH' },
        'MAJOR': { bg: 'bg-orange-500/20', text: 'text-orange-400', border: 'border-orange-500/30', label: 'MAJOR' },
        'MINOR': { bg: 'bg-blue-500/20', text: 'text-blue-400', border: 'border-blue-500/30', label: 'MINOR' },
    }[severity] || { bg: 'bg-green-500/20', text: 'text-green-400', border: 'border-green-500/30', label: severity };
    return `<span class="font-mono text-[10px] font-bold px-1.5 py-0.5 rounded ${cfg.bg} ${cfg.text} border ${cfg.border}">${cfg.label}</span>`;
}

function typeBadge(eventType) {
    const cfg = {
        'TRIP': { bg: 'bg-red-500/10', text: 'text-red-300', label: 'TRIP' },
        'OUTAGE': { bg: 'bg-orange-500/10', text: 'text-orange-300', label: 'PLANNED' },
        'RETURN': { bg: 'bg-green-500/10', text: 'text-green-300', label: 'RETURN' },
        'REDUCED': { bg: 'bg-yellow-500/10', text: 'text-yellow-300', label: 'REDUCED' },
        'UPDATE': { bg: 'bg-blue-500/10', text: 'text-blue-300', label: 'UPDATE' },
    }[eventType] || { bg: 'bg-gray-500/10', text: 'text-gray-300', label: eventType };
    return `<span class="font-mono text-[10px] px-1.5 py-0.5 rounded ${cfg.bg} ${cfg.text}">${cfg.label}</span>`;
}

function renderAlertCard(alert, idx) {
    const borderClass = severityBorderClass(alert.severity, alert.event_type);
    const isFlash = alert.severity === 'FLASH' && alert.event_type !== 'RETURN';
    const flashClass = isFlash ? 'animate-flash-pulse' : '';

    return `
        <div class="group ${borderClass} bg-terminal-surface/60 hover:bg-terminal-surface rounded-r-lg px-4 py-3 cursor-pointer transition-all duration-200 animate-fade-in ${flashClass}"
             onclick="showDetail(${idx})"
             style="animation-delay: ${Math.min(idx * 30, 300)}ms">
            <div class="flex items-start justify-between gap-3">
                <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2 mb-1 flex-wrap">
                        ${severityBadge(alert.severity)}
                        ${typeBadge(alert.event_type)}
                        <span class="text-[10px] font-mono text-terminal-muted">${alert.published_relative}</span>
                    </div>
                    <h3 class="font-semibold text-sm text-terminal-text leading-snug mb-0.5 truncate">${escHtml(alert.headline)}</h3>
                    <p class="text-xs text-terminal-muted font-mono truncate">${escHtml(alert.detail)}</p>
                </div>
                <div class="text-right flex-shrink-0 hidden sm:block">
                    <div class="font-mono font-bold text-lg tabular-nums ${alert.event_type === 'RETURN' ? 'text-green-400' : 'text-red-400'}">
                        ${alert.event_type === 'RETURN' ? '+' : '-'}${alert.impact_mw || alert.normal_mw}<span class="text-xs text-terminal-muted ml-0.5">MW</span>
                    </div>
                    <div class="text-[10px] font-mono text-terminal-muted">${escHtml(alert.fuel_label)}</div>
                </div>
            </div>
            <div class="flex items-center gap-4 mt-1.5 text-[10px] font-mono text-terminal-muted/70">
                <span>📅 ${escHtml(alert.event_start)}</span>
                <span>→ ${escHtml(alert.event_end)}</span>
                <span class="hidden md:inline">ID: ${escHtml(alert.asset_id)}</span>
            </div>
        </div>`;
}

function escHtml(str) {
    if (!str) return '';
    const el = document.createElement('span');
    el.textContent = str;
    return el.innerHTML;
}

// ── Side Panel Detail ──────────────────────────────
function showDetail(idx) {
    const alert = getFilteredAlerts()[idx];
    if (!alert) return;

    const panel = document.getElementById('side-panel');
    const detail = document.getElementById('side-detail');
    panel.classList.remove('hidden');

    detail.innerHTML = `
        <div class="space-y-4">
            <div class="flex items-center gap-2 flex-wrap">
                ${severityBadge(alert.severity)}
                ${typeBadge(alert.event_type)}
            </div>
            <h2 class="font-bold text-base text-terminal-text">${escHtml(alert.headline)}</h2>
            <p class="text-xs font-mono text-terminal-muted">${escHtml(alert.detail)}</p>

            <div class="border-t border-terminal-border pt-3 space-y-2">
                <div class="grid grid-cols-2 gap-3 text-xs font-mono">
                    <div>
                        <div class="text-terminal-muted/60 text-[10px] uppercase tracking-wider mb-0.5">Normal Capacity</div>
                        <div class="text-terminal-text font-semibold">${alert.normal_mw} MW</div>
                    </div>
                    <div>
                        <div class="text-terminal-muted/60 text-[10px] uppercase tracking-wider mb-0.5">Available</div>
                        <div class="text-terminal-text font-semibold">${alert.available_mw} MW</div>
                    </div>
                    <div>
                        <div class="text-terminal-muted/60 text-[10px] uppercase tracking-wider mb-0.5">Impact</div>
                        <div class="font-bold ${alert.event_type === 'RETURN' ? 'text-green-400' : 'text-red-400'}">${alert.impact_mw} MW</div>
                    </div>
                    <div>
                        <div class="text-terminal-muted/60 text-[10px] uppercase tracking-wider mb-0.5">Fuel Type</div>
                        <div class="text-terminal-text">${escHtml(alert.fuel_label)}</div>
                    </div>
                </div>
            </div>

            <div class="border-t border-terminal-border pt-3 space-y-2 text-xs font-mono">
                <div>
                    <span class="text-terminal-muted/60">Asset ID:</span>
                    <span class="text-terminal-text ml-2">${escHtml(alert.asset_id)}</span>
                </div>
                <div>
                    <span class="text-terminal-muted/60">Participant:</span>
                    <span class="text-terminal-text ml-2">${escHtml(alert.participant)}</span>
                </div>
                <div>
                    <span class="text-terminal-muted/60">Type:</span>
                    <span class="text-terminal-text ml-2">${escHtml(alert.unavailability_type)}</span>
                </div>
                <div>
                    <span class="text-terminal-muted/60">Status:</span>
                    <span class="text-terminal-text ml-2">${escHtml(alert.event_status)}</span>
                </div>
                <div>
                    <span class="text-terminal-muted/60">Cause:</span>
                    <span class="text-terminal-text ml-2">${escHtml(alert.cause) || '—'}</span>
                </div>
                <div>
                    <span class="text-terminal-muted/60">Event Start:</span>
                    <span class="text-terminal-text ml-2">${escHtml(alert.event_start)}</span>
                </div>
                <div>
                    <span class="text-terminal-muted/60">Event End:</span>
                    <span class="text-terminal-text ml-2">${escHtml(alert.event_end)}</span>
                </div>
                <div>
                    <span class="text-terminal-muted/60">Published:</span>
                    <span class="text-terminal-text ml-2">${escHtml(alert.published)}</span>
                </div>
                <div>
                    <span class="text-terminal-muted/60">MRID:</span>
                    <span class="text-terminal-text ml-2 break-all text-[10px]">${escHtml(alert.mrid)}</span>
                </div>
            </div>
        </div>`;
}

function closeSidePanel() {
    document.getElementById('side-panel').classList.add('hidden');
}

// ── Filtering ──────────────────────────────────────
function getFilteredAlerts() {
    if (currentFilter === 'all') return allAlerts;
    if (currentFilter === 'flash') return allAlerts.filter(a => a.severity === 'FLASH');
    if (currentFilter === 'trip') return allAlerts.filter(a => a.event_type === 'TRIP' || a.event_type === 'OUTAGE');
    if (currentFilter === 'return') return allAlerts.filter(a => a.event_type === 'RETURN');
    return allAlerts;
}

function filterAlerts(filter) {
    currentFilter = filter;
    // Update button styles
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.toggle('ring-1', btn.dataset.filter === filter);
        btn.classList.toggle('ring-terminal-accent/50', btn.dataset.filter === filter);
    });
    renderFeed();
}

// ── Feed Rendering ─────────────────────────────────
function renderFeed() {
    const feed = document.getElementById('alert-feed');
    const filtered = getFilteredAlerts();

    document.getElementById('alert-count-badge').textContent = filtered.length;

    if (filtered.length === 0) {
        feed.innerHTML = `
            <div class="flex items-center justify-center h-full">
                <div class="text-center">
                    <div class="text-4xl mb-3">📭</div>
                    <p class="font-mono text-terminal-muted text-sm">No alerts match this filter</p>
                </div>
            </div>`;
        return;
    }

    feed.innerHTML = filtered.map((a, i) => renderAlertCard(a, i)).join('');
}

// ── Data Fetching ──────────────────────────────────
async function fetchAlerts() {
    try {
        const resp = await fetch('/api/alerts');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        const newAlerts = data.alerts || [];

        // Detect flash alerts
        if (allAlerts.length > 0 && newAlerts.length > 0) {
            const oldIds = new Set(allAlerts.map(a => a.id));
            for (const a of newAlerts) {
                if (!oldIds.has(a.id) && a.severity === 'FLASH' && a.event_type !== 'RETURN') {
                    showFlash(a.headline);
                    break;
                }
            }
        }

        allAlerts = newAlerts;
        renderFeed();
        updateTicker(allAlerts);

        // Connection status
        setConnectionStatus('connected');
    } catch (e) {
        console.error('Fetch error:', e);
        setConnectionStatus('disconnected');
    }
}

async function fetchStats() {
    try {
        const resp = await fetch('/api/stats');
        if (!resp.ok) return;
        const stats = await resp.json();
        updateStats(stats);
    } catch (e) { /* ignore */ }
}

// ── Connection Status ──────────────────────────────
function setConnectionStatus(status) {
    const dot = document.getElementById('connection-dot');
    const text = document.getElementById('connection-text');
    dot.className = 'status-dot ' + status;
    text.textContent = status.toUpperCase();
}

// ── SSE Stream ─────────────────────────────────────
function connectSSE() {
    if (sseSource) sseSource.close();

    sseSource = new EventSource('/api/alerts/stream');

    sseSource.onopen = () => setConnectionStatus('connected');

    sseSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.alerts) {
                // Merge SSE updates with existing
                const sseAlerts = data.alerts;
                const existingIds = new Set(allAlerts.map(a => a.id));

                for (const a of sseAlerts) {
                    if (!existingIds.has(a.id)) {
                        allAlerts.unshift(a);
                        if (a.severity === 'FLASH' && a.event_type !== 'RETURN') {
                            showFlash(a.headline);
                        }
                    }
                }

                renderFeed();
                updateTicker(allAlerts);
            }
            if (data.stats) updateStats(data.stats);
            setConnectionStatus('connected');
        } catch (e) {
            console.error('SSE parse error:', e);
        }
    };

    sseSource.onerror = () => {
        setConnectionStatus('disconnected');
        sseSource.close();
        // Reconnect after 5 seconds
        setTimeout(connectSSE, 5000);
    };
}

// ── Init ───────────────────────────────────────────
(async function init() {
    // Initial fetch
    await fetchAlerts();
    await fetchStats();

    // Polling fallback every 15 seconds
    setInterval(fetchAlerts, 15000);
    setInterval(fetchStats, 15000);

    // Also try SSE for faster updates
    connectSSE();
})();
