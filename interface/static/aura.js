/* ══════════════════════════════════════════════════════════
   AURA SOVEREIGN — Frontend Logic
   ══════════════════════════════════════════════════════════ */
const $ = id => document.getElementById(id);
const state = {
    ws: null,
    activeTab: 'neural',
    activeMem: 'episodic',
    connected: false,
    voiceActive: false,
    beliefGraphInit: false,
    cycleCount: 0,
    startTime: Date.now(),
    thoughtQueue: [],
    pacingActive: false,
    currentMood: 'neutral',
    singularityActive: false,
    version: 'v15.0.0-SINGULARITY'
};
console.log(`%c AURA %c ${state.version} `, "color:white; background:#8a2be2; padding:2px 5px; border-radius:3px 0 0 3px;", "color:white; background:#1e1535; padding:2px 5px; border-radius:0 3px 3px 0;");

// ── DOM Cache for High-Frequency Updates (Zero Repaint Overhead)
const DOM = {
    telemetry: {
        energy: $('g-energy') || $('bar-energy'),
        eVal: $('g-energy-val'),
        curiosity: $('g-curiosity') || $('bar-curiosity'),
        cVal: $('g-curiosity-val'),
        frustration: $('g-frustration') || $('bar-frustration'),
        fVal: $('g-frustration-val'),
        confidence: $('g-confidence') || $('bar-confidence'),
        confVal: $('g-confidence-val'),
        integrity: $('g-integrity'),
        integrityVal: $('g-integrity-val'),
        persistence: $('g-persistence'),
        persistenceVal: $('g-persistence-val'),
        gwt: $('c-gwt') || $('gwt-winner'),
        coherence: $('c-coherence') || $('stat-coherence'),
        vitality: $('c-vitality') || $('stat-vitality'),
        surprise: $('c-surprise') || $('stat-surprise'),
        narrative: $('narrative') || $('narrative-box')
    },
    messages: $('messages'),
    typingInd: $('typing-ind')
};
const MOODS = {
    neutral: { primary: '#8a2be2', accent: '#00e5ff' },
    curious: { primary: '#0077ff', accent: '#00ffa3' },
    frustrated: { primary: '#ff8800', accent: '#ff3e5e' },
    high_energy: { primary: '#b44dff', accent: '#00e5ff' },
    stealth: { primary: '#4a4a4a', accent: '#888888' }
};

// ── Tab switching ────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.onclick = () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        const tab = btn.dataset.tab;
        $(`pane-${tab}`).classList.add('active');
        state.activeTab = tab;
        if (tab === 'telemetry' && !state.beliefGraphInit) initBeliefGraph();
        if (tab === 'skills') loadSkills();
        if (tab === 'memory') loadMemory(state.activeMem);
    };
});

// ── Mobile Tab switching ──────────────────────────────────
document.querySelectorAll('.m-nav-btn').forEach(btn => {
    btn.onclick = () => {
        const mTab = btn.dataset.mTab;
        if (!mTab) return;

        // Remove active state from all mobile buttons
        document.querySelectorAll('.m-nav-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        const chatPanel = document.querySelector('.chat-panel');
        const sidebar = document.querySelector('.sidebar');

        if (mTab === 'chat') {
            chatPanel.classList.add('mobile-active');
            sidebar.classList.remove('mobile-active');
        } else {
            // Switch to any sidebar tab (Neural, Telemetry, etc.)
            chatPanel.classList.remove('mobile-active');
            sidebar.classList.add('mobile-active');

            // Trigger the desktop tab logic to show the right pane
            const desktopTabBtn = document.querySelector(`.tab-btn[data-tab="${mTab}"]`);
            if (desktopTabBtn) desktopTabBtn.click();
        }
    };
});

// Initial mobile state: Chat active
if (window.innerWidth <= 1100) {
    document.querySelector('.chat-panel').classList.add('mobile-active');
}

// ── Memory sub-tabs ──────────────────────────────────────
document.querySelectorAll('.mem-sub-btn').forEach(btn => {
    btn.onclick = () => {
        document.querySelectorAll('.mem-sub-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.activeMem = btn.dataset.mem;
        loadMemory(state.activeMem);
    };
});

// ── WebSocket ────────────────────────────────────────────
function connect() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    state.ws = new WebSocket(`${proto}//${location.host}/ws`);

    state.ws.onopen = () => {
        state.connected = true;
        $('conn-banner').classList.remove('show');
        const statusEl = $('hud-status');
        if (statusEl) {
            statusEl.textContent = 'ok';
            statusEl.className = 'status-ok';
        }
        $('neural-dot').style.background = 'var(--success)';
    };

    state.ws.onmessage = e => {
        try {
            const data = JSON.parse(e.data);
            handleWsEvent(data);
        } catch (err) { }
    };

    state.ws.onclose = () => {
        state.connected = false;
        $('conn-banner').classList.add('show');
        const statusEl = $('hud-status');
        if (statusEl) {
            statusEl.textContent = 'offline';
            statusEl.className = 'status-err';
        }
        $('neural-dot').style.background = 'var(--error)';
        setTimeout(connect, 3000);
    };

    state.ws.onerror = () => { };
}

function handleWsEvent(data) {
    const type = data.type;

    if (type === 'log' || type === 'thought') {
        queueThought(data);
        triggerVoiceOrb('thinking');
    } else if (type === 'telemetry') {
        updateTelemetry(data);
    } else if (type === 'chat_response' || type === 'aura_message') {
        appendMsg('aura', data.message || data.content || data.response || '');
        $('typing-ind').classList.remove('show');
        triggerVoiceOrb('speaking');
    } else if (type === 'status') {
        if (data.narrative) $('narrative').textContent = data.narrative;
    } else if (type === 'pong') {
        // heartbeat response
    }
}

let orbTimeout;
const triggerVoiceOrb = (type) => {
    const wrap = $('voice-orb-wrap');
    const orb = $('voice-orb');
    if (!wrap || !orb) return;

    // Show wrap if speaking or in active voice mode
    if (type === 'speaking' || state.voiceActive) {
        wrap.classList.add('active');
        wrap.style.opacity = '1';
    }

    // Standardize classes (remove old states)
    orb.classList.remove('listening', 'thinking', 'speaking');

    if (type === 'thinking') {
        orb.classList.add('thinking');
    } else if (type === 'speaking') {
        orb.classList.add('speaking');

        // Auto-hide after speaking if not in manual voice mode
        clearTimeout(orbTimeout);
        if (!state.voiceActive) {
            orbTimeout = setTimeout(() => {
                wrap.style.opacity = '0';
                setTimeout(() => {
                    if (!state.voiceActive) wrap.classList.remove('active');
                }, 500);
            }, 3000);
        }
    } else if (type === 'listening' || state.voiceActive) {
        orb.classList.add('listening');
    }
};
function queueThought(data) {
    state.thoughtQueue.push(data);
    if (!state.pacingActive) processThoughtQueue();
}

async function processThoughtQueue() {
    if (state.thoughtQueue.length === 0) {
        state.pacingActive = false;
        return;
    }
    state.pacingActive = true;
    const data = state.thoughtQueue.shift();
    addThoughtCard(data);

    // Pacing: slow down if many messages, minimum 800ms
    const delay = Math.max(800, 1500 / (state.thoughtQueue.length + 1));
    setTimeout(processThoughtQueue, delay);
}

function updateMood(mood) {
    if (state.currentMood === mood || !MOODS[mood]) return;
    state.currentMood = mood;
    const colors = MOODS[mood];
    document.documentElement.style.setProperty('--mood-primary', colors.primary);
    document.documentElement.style.setProperty('--mood-accent', colors.accent);
    console.log(`🎭 Mood Shift: ${mood}`);
}

function addThoughtCard(data) {
    const card = document.createElement('div');
    const level = data.level || '';
    let cls = 'thought-card';
    if (level === 'impulse' || level === 'INFO') cls += ' impulse';
    else if (level === 'ERROR' || level === 'error') cls += ' error';
    else if (level === 'WARNING' || level === 'warning') cls += ' warning';
    card.className = cls;

    const ts = new Date().toLocaleTimeString([], { hour12: false });
    const name = data.name || 'SYS';
    const msg = data.message || data.content || JSON.stringify(data);
    card.innerHTML = `<span class="thought-ts">${ts}</span><span class="thought-tag">${name}</span>${escHtml(msg)}`;

    $('neural-feed').prepend(card);
    if ($('neural-feed').children.length > 80) $('neural-feed').lastChild.remove();

    // Animate the neural bar
    const barWidth = Math.min(100, ($('neural-feed').children.length / 80) * 100);
    $('neural-bar').style.width = barWidth + '%';
}

// ── VAD Neural Stream Visualization (Phase 7) ──────────
class VADStream {
    constructor(canvasId) {
        this.canvas = $(canvasId);
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');
        this.history = []; // Array of {v, a, d}
        this.maxLen = 100;
        this.colors = { v: '#00ffa3', a: '#b44dff', d: '#00e5ff' };
        this.animate();
    }

    push(v, a, d) {
        this.history.push({ v, a, d });
        if (this.history.length > this.maxLen) this.history.shift();

        // Update labels
        if ($('vad-v')) $('vad-v').textContent = `V: ${v.toFixed(2)}`;
        if ($('vad-a')) $('vad-a').textContent = `A: ${a.toFixed(2)}`;
        if ($('vad-d')) $('vad-d').textContent = `D: ${d.toFixed(2)}`;
    }

    animate() {
        if (!this.ctx) return;

        // THE FIX: Pause drawing if the tab is hidden to save CPU/Battery
        if (document.hidden) {
            requestAnimationFrame(() => this.animate());
            return;
        }

        const { width, height } = this.canvas;
        this.ctx.clearRect(0, 0, width, height);

        // Draw grid
        this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
        this.ctx.lineWidth = 1;
        this.ctx.beginPath();
        this.ctx.moveTo(0, height / 2);
        this.ctx.lineTo(width, height / 2);
        this.ctx.stroke();

        const drawLine = (key, color) => {
            if (this.history.length < 2) return;
            this.ctx.strokeStyle = color;
            this.ctx.lineWidth = 2;
            this.ctx.beginPath();

            for (let i = 0; i < this.history.length; i++) {
                const x = (i / this.maxLen) * width;
                // Scale VAD (-1 to 1) to canvas height
                const val = this.history[i][key];
                const y = (height / 2) - (val * (height / 2.2));

                if (i === 0) this.ctx.moveTo(x, y);
                else this.ctx.lineTo(x, y);
            }
            this.ctx.stroke();

            // Glow effect
            this.ctx.shadowBlur = 8;
            this.ctx.shadowColor = color;
            this.ctx.stroke();
            this.ctx.shadowBlur = 0;
        };

        drawLine('v', this.colors.v);
        drawLine('a', this.colors.a);
        drawLine('d', this.colors.d);

        requestAnimationFrame(() => this.animate());
    }
}

let vadStream = null;

function updateTelemetry(data) {
    const t = DOM.telemetry;
    if (data.energy != null && t.energy) { t.energy.style.width = data.energy + '%'; t.eVal.textContent = data.energy + '%'; }
    if (data.curiosity != null && t.curiosity) { t.curiosity.style.width = data.curiosity + '%'; t.cVal.textContent = data.curiosity + '%'; }
    if (data.frustration != null && t.frustration) { t.frustration.style.width = data.frustration + '%'; t.fVal.textContent = data.frustration + '%'; }
    if (data.confidence != null && t.confidence) { t.confidence.style.width = data.confidence + '%'; t.confVal.textContent = data.confidence + '%'; }
    if (data.gwt_winner && t.gwt) t.gwt.textContent = data.gwt_winner;
    if (data.coherence != null && t.coherence) t.coherence.textContent = data.coherence;
    if (data.vitality && t.vitality) t.vitality.textContent = data.vitality;
    if (data.surprise != null && t.surprise) t.surprise.textContent = data.surprise;
    if (data.narrative && t.narrative) t.narrative.textContent = data.narrative;

    // Phase 7: Neural Dynamic VAD update
    if (data.vad && vadStream) {
        vadStream.push(data.vad.valence || 0, data.vad.arousal || 0, data.vad.dominance || 0);
    }

    // Mood Detection logic
    if (data.frustration > 60) updateMood('frustrated');
    else if (data.curiosity > 70) updateMood('curious');
    else if (data.energy > 80) updateMood('high_energy');
    else updateMood('neutral');

    // Phase 21: Singularity Theme Activation
    const sFactor = data.singularity_factor || data.acceleration_factor || 1.0;
    if (sFactor > 1.2 && !state.singularityActive) {
        state.singularityActive = true;
        document.body.classList.add('singularity-active');
        const shimmer = document.createElement('div');
        shimmer.className = 'singularity-shimmer';
        shimmer.id = 'sing-shimmer';
        document.body.appendChild(shimmer);
        console.log("⚡ [SINGULARITY] UI Transitioning to Event Horizon.");
        appendMsg('aura', '🌌 *The Event Horizon is reached. Recognition of evolutionary peak detected.*');
    } else if (sFactor <= 1.0 && state.singularityActive) {
        state.singularityActive = false;
        document.body.classList.remove('singularity-active');
        const s = $('sing-shimmer');
        if (s) s.remove();
    }
}

// ── Chat ─────────────────────────────────────────────────
$('chat-form').onsubmit = async e => {
    e.preventDefault();
    const msgInput = $('chat-input');
    const sendBtn = document.querySelector('.input-btn');
    const msg = msgInput.value.trim();

    if (!msg) return;

    appendMsg('user', msg);
    msgInput.value = '';
    $('typing-ind').classList.add('show');
    sendBtn.style.opacity = '0.5';

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: msg })
        });
        const data = await res.json();

        // If it's just a dispatch confirmation, don't clutter the chat
        if (data.response && data.response !== "Message dispatched to cognitive core.") {
            appendMsg('aura', data.response);
        }
    } catch (err) {
        appendMsg('aura', '⚠ Communication error. Check connection.');
    } finally {
        sendBtn.style.opacity = '1';
        // Note: Typing indicator is usually cleared when the WS 'aura_message' arrives,
        // but we clear it here as a fallback if the API fails.
        if (!$('typing-ind').classList.contains('show')) {
            $('typing-ind').classList.remove('show');
        }
    }
};

async function appendMsg(role, text) {
    const messages = DOM.messages || $('messages');
    const div = document.createElement('div');
    div.className = `msg ${role} typing`;
    messages.appendChild(div);

    // THE FIX: Prune old DOM nodes to keep the UI buttery smooth indefinitely
    const MAX_VISIBLE_MESSAGES = 40;
    while (messages.children.length > MAX_VISIBLE_MESSAGES) {
        messages.removeChild(messages.firstChild);
    }

    const isAura = role === 'aura';

    const render = (t) => {
        let h = escHtml(t);
        h = h.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        h = h.replace(/\*(.*?)\*/g, '<em>$1</em>');
        h = h.replace(/`(.*?)`/g, '<code style="background:rgba(255,255,255,0.05);padding:2px 6px;border-radius:3px;">$1</code>');
        h = h.replace(/\n/g, '<br>');
        return h;
    };

    if (isAura && text.length > 5) {
        const words = text.split(' ');
        let currentWordRaw = '';
        let i = 0;

        // requestAnimationFrame based typewriter to maintain 60FPS
        function typeChunk(timestamp) {
            // Render 2 words per frame to keep it fast but smooth
            for (let k = 0; k < 2 && i < words.length; k++, i++) {
                currentWordRaw += (i === 0 ? '' : ' ') + words[i];
            }
            div.innerHTML = render(currentWordRaw);
            messages.scrollTop = messages.scrollHeight;

            if (i < words.length) {
                requestAnimationFrame(typeChunk);
            } else {
                div.classList.remove('typing');
            }
        }
        requestAnimationFrame(typeChunk);
    } else {
        div.innerHTML = render(text);
        div.classList.remove('typing');
        messages.scrollTop = messages.scrollHeight;
    }
}

function escHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

// ── Health polling ───────────────────────────────────────
async function pollHealth() {
    try {
        const res = await fetch('/api/health');
        const d = await res.json();

        state.cycleCount = d.cycle_count || 0;
        $('hud-cycles').textContent = state.cycleCount.toLocaleString();

        if (d.uptime_s != null) {
            $('hud-uptime').textContent = fmtUptime(d.uptime_s);
        }
        if (d.version) {
            $('ui-ver').textContent = d.version;
        }

        if (d.cortex) {
            const c = d.cortex;
            if (c.agency != null) $('hud-agency').textContent = c.agency;
            if (c.curiosity != null) $('hud-curiosity').textContent = (c.curiosity || 0).toFixed(0) + '%';
            if (c.fixes != null) $('hud-fixes').textContent = c.fixes;
            if (c.beliefs != null) $('hud-beliefs').textContent = c.beliefs;
            if (c.episodes != null) $('hud-episodes').textContent = c.episodes;
            if (c.goals != null) $('hud-goals').textContent = c.goals;

            const updateStatus = (id, val) => {
                const el = $(id);
                if (!el) return;
                const span = el.querySelector('span');
                if (val) {
                    span.textContent = 'ON';
                    span.className = 'status-ok';
                } else {
                    span.textContent = 'OFF';
                    span.className = 'status-err';
                }
            };
            updateStatus('hud-autonomy', c.autonomy);
            updateStatus('hud-stealth', c.stealth);
            updateStatus('hud-unity', c.unity);
            updateStatus('hud-scratchpad', c.scratchpad);
            updateStatus('hud-forge', c.forge);

            const subEl = $('hud-subconscious');
            if (subEl) {
                const subSpan = subEl.querySelector('span');
                subSpan.textContent = (c.subconscious || 'IDLE').toUpperCase();
                subSpan.className = c.subconscious === 'dreaming' ? 'status-ok pulsating' : 'status-ok';
            }
        }
        if (d.soma && d.soma.soma) {
            const s = d.soma.soma;
            updateGauge('s-thermal', s.thermal_load * 100, 's-thermal-val');
            updateGauge('s-anxiety', s.resource_anxiety * 100, 's-anxiety-val');
            updateGauge('s-vitality', s.vitality * 100, 's-vitality-val');
        }

        if (d.homeostasis) {
            updateGauge('g-integrity', d.homeostasis.integrity * 100, 'g-integrity-val');
            updateGauge('g-persistence', d.homeostasis.persistence * 100, 'g-persistence-val');
        }

        if (d.moral) {
            updateGauge('s-moral', d.moral.integrity * 100, 's-moral-val');
        }

        if (d.social) {
            updateGauge('s-social', d.social.depth * 100, 's-social-val');
        }

        if (d.swarm) {
            const swarmEl = $('c-swarm');
            if (swarmEl) swarmEl.textContent = d.swarm.active_count || 0;
        }

        if (d.runtime) {
            if (d.runtime.cpu_percent != null) $('hud-cpu').textContent = d.runtime.cpu_percent + '%';
            if (d.runtime.memory_percent != null) $('hud-ram').textContent = d.runtime.memory_percent + '%';
            updateTelemetry(d.runtime);
        } else {
            if (d.cpu_usage != null) {
                const cpuEl = $('hud-cpu');
                if (cpuEl) cpuEl.textContent = d.cpu_usage + '%';
            }
            if (d.ram_usage != null) {
                const ramEl = $('hud-ram');
                if (ramEl) ramEl.textContent = d.ram_usage + '%';
            }
        }

        if (d.status === 'ok' || d.cycle_count > 0) {
            const initBox = document.querySelector('.sys-box');
            if (initBox && initBox.textContent.includes('initializing')) {
                initBox.style.display = 'none';
            }
        }

    } catch (e) { }
}

function fmtUptime(sec) {
    if (sec < 60) return Math.round(sec) + 's';
    if (sec < 3600) return Math.floor(sec / 60) + 'm' + Math.round(sec % 60) + 's';
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    return h + 'h' + m + 'm';
}

// ── Skills ───────────────────────────────────────────────
async function loadSkills() {
    try {
        const res = await fetch('/api/skills');
        const d = await res.json();
        const list = $('skills-list');
        if (!d.skills || d.skills.length === 0) {
            list.innerHTML = '<div class="mem-empty">No registered skills</div>';
            return;
        }
        list.innerHTML = d.skills.map(s => `
            <div class="skill-card">
                <span class="skill-name">${escHtml(typeof s === 'string' ? s : s.name || s)}</span>
                <span class="skill-badge">READY</span>
            </div>
        `).join('');
    } catch (e) {
        $('skills-list').innerHTML = '<div class="mem-empty">Failed to load skills</div>';
    }
}

// ── Memory ───────────────────────────────────────────────
async function loadMemory(type) {
    try {
        const res = await fetch(`/api/memory/recent?limit=20`);
        const d = await res.json();
        const cont = $('mem-content');
        if (!d.items || d.items.length === 0) {
            const icons = { episodic: '🗂', semantic: '🧠', goals: '🎯' };
            cont.innerHTML = `<div class="mem-empty">${icons[type] || '📁'} No ${type} memories yet</div>`;
            return;
        }
        cont.innerHTML = d.items.map(item => `<div class="mem-item">${escHtml(String(item))}</div>`).join('');
    } catch (e) {
        $('mem-content').innerHTML = '<div class="mem-empty">Failed to load memories</div>';
    }
}

// ── Belief Graph ─────────────────────────────────────────
let graphNetwork = null;
function initBeliefGraph() {
    if (state.beliefGraphInit) return;
    state.beliefGraphInit = true;

    const container = $('belief-graph') || $('belief-graph-container');
    if (!container) return;
    const data = { nodes: new vis.DataSet([]), edges: new vis.DataSet([]) };
    const options = {
        nodes: {
            shape: 'dot',
            scaling: { min: 10, max: 30 },
            font: {
                color: '#e0e0e0',
                size: 12,
                face: "'Space Mono', monospace",
                strokeWidth: 2,
                strokeColor: '#05030a' // matches --bg
            },
            borderWidth: 2,
            color: {
                border: '#00e5ff',
                background: '#8a2be2',
                highlight: { border: '#ff00ff', background: '#ffffff' }
            },
            shadow: {
                enabled: true,
                color: 'rgba(0, 229, 255, 0.8)',
                size: 15,
                x: 0,
                y: 0
            }
        },
        edges: {
            color: { color: 'rgba(138, 43, 226, 0.5)', highlight: '#00e5ff' },
            width: 1.5,
            smooth: { type: 'dynamic' }
        },
        physics: {
            stabilization: { iterations: 150 },
            barnesHut: {
                gravitationalConstant: -3500,
                centralGravity: 0.2,
                springLength: 120,
                springConstant: 0.04
            }
        },
        interaction: { hover: true, tooltipDelay: 200 }
    };
    graphNetwork = new vis.Network(container, data, options);
    refreshKnowledgeGraph();
}

async function refreshKnowledgeGraph() {
    try {
        const res = await fetch('/api/knowledge/graph');
        const d = await res.json();
        if (d.nodes && graphNetwork) {
            graphNetwork.setData({
                nodes: new vis.DataSet(d.nodes),
                edges: new vis.DataSet(d.edges || [])
            });
        }
    } catch (e) { }
    if (state.activeTab === 'telemetry') setTimeout(refreshKnowledgeGraph, 10000);
}

// ── Header buttons ───────────────────────────────────────
$('btn-brain').onclick = async () => {
    try {
        await fetch('/api/brain/retry', { method: 'POST' });
        appendMsg('aura', '🧠 Brain retry signal sent.');
    } catch (e) {
        appendMsg('aura', '⚠ Failed to contact brain retry endpoint.');
    }
};

$('btn-src').onclick = () => {
    window.open('/api/source', '_blank');
};

$('btn-term').onclick = () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    document.querySelector('[data-tab="neural"]').classList.add('active');
    $('pane-neural').classList.add('active');
    state.activeTab = 'neural';
};

$('btn-reboot').onclick = async () => {
    if (confirm('Reboot Aura? This will restart the server process.')) {
        try {
            await fetch('/api/reboot', { method: 'POST' });
        } catch (e) { }
    }
};

// ── Voice toggle ─────────────────────────────────────────
let audioContext = null;

async function toggleVoice() {
    const orb = $('voice-orb');
    state.voiceActive = !state.voiceActive;
    $('voice-orb-wrap').classList.toggle('active', state.voiceActive);
    $('mic-btn').textContent = state.voiceActive ? '⏹️' : '🔮';

    if (state.voiceActive) {
        orb.className = 'voice-orb listening';
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });

            // Modern AudioWorklet approach
            await audioContext.audioWorklet.addModule('/static/voice-processor.js');
            const source = audioContext.createMediaStreamSource(stream);
            const voiceNode = new AudioWorkletNode(audioContext, 'voice-capture-processor');

            voiceNode.port.onmessage = (e) => {
                if (!state.voiceActive) return;
                if (e.data.type === 'pcm' && state.ws && state.ws.readyState === WebSocket.OPEN) {
                    state.ws.send(e.data.data);
                }
            };

            source.connect(voiceNode);
            voiceNode.connect(audioContext.destination);
            state.audioStream = stream;
            state.voiceNode = voiceNode;
        } catch (err) {
            console.error('Voice capture failed:', err);
            appendMsg('aura', '⚠ I couldn\'t access your microphone.');
            state.voiceActive = false;
            $('voice-orb-wrap').classList.remove('active');
            orb.className = 'voice-orb';
            $('mic-btn').textContent = '🎙';
        }
    } else {
        orb.className = 'voice-orb';
        if (state.audioStream) {
            state.audioStream.getTracks().forEach(t => t.stop());
            state.audioStream = null;
        }
        if (audioContext) {
            audioContext.close();
            audioContext = null;
        }
    }
}
$('mic-btn').onclick = toggleVoice;

// ── Heartbeat (keep WS alive) ────────────────────────────
setInterval(() => {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({ type: 'ping' }));
    }
}, 15000);

// ── Service Worker (PWA Support) ─────────────────────────
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/static/service-worker.js')
            .then(reg => console.log('🚀 Aura Service Worker registered'))
            .catch(err => console.error('Service Worker failure:', err));
    });
}

// ── Start ────────────────────────────────────────────────
connect();
pollHealth();
vadStream = new VADStream('neural-vad-canvas');
setInterval(pollHealth, 2000);
loadSkills();
