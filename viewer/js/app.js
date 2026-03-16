/* ── DETEGASA Compliance Viewer — App Logic ────────────────────────────── */

// ── State ────────────────────────────────────────────────────────────────
const state = {
    data: null,          // Raw loaded JSON
    items: [],           // result.items
    filtered: [],        // After filters
    filters: {
        status: [],      // Active status filters (empty = all)
        categories: [],  // Active category filters (empty = all)
        risks: [],       // Active risk filters (empty = all)
        search: '',
    },
    sort: { col: null, dir: 'asc' },
};

// Charts
let statusChart = null;
let categoryChart = null;

// ── Status / Risk display config ─────────────────────────────────────────
const STATUS_LABELS = {
    compliant: 'Compliant',
    non_compliant: 'Non-Compliant',
    partial: 'Partial',
    clarification_needed: 'Clarification',
    not_applicable: 'N/A',
    deviation_acceptable: 'Deviation OK',
};
const STATUS_COLORS = {
    compliant: '#059669',
    non_compliant: '#dc2626',
    partial: '#d97706',
    clarification_needed: '#7c3aed',
    not_applicable: '#6b7280',
    deviation_acceptable: '#2563eb',
};

const RISK_LABELS = {
    disqualifying: 'Disqualifying',
    high: 'High',
    medium: 'Medium',
    low: 'Low',
};

// ── Init ─────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    setupFileInput();
    setupDragDrop();
    setupDemoButtons();
    setupFilterListeners();
    setupTableSort();
    setupDetailPanel();
    setupExport();
});

// ── File Loading ─────────────────────────────────────────────────────────
function setupFileInput() {
    const input = document.getElementById('file-input');
    input.addEventListener('change', (e) => {
        if (e.target.files[0]) loadFromFile(e.target.files[0]);
    });
}

function setupDragDrop() {
    const zone = document.getElementById('drop-zone');
    ['dragenter', 'dragover'].forEach(evt =>
        zone.addEventListener(evt, (e) => { e.preventDefault(); zone.classList.add('drag-over'); })
    );
    ['dragleave', 'drop'].forEach(evt =>
        zone.addEventListener(evt, () => zone.classList.remove('drag-over'))
    );
    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        const file = e.dataTransfer.files[0];
        if (file && file.name.endsWith('.json')) loadFromFile(file);
    });
}

function setupDemoButtons() {
    document.getElementById('demo-btn').addEventListener('click', loadDemoData);
    document.getElementById('demo-btn-zone').addEventListener('click', loadDemoData);
}

function loadFromFile(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            const json = JSON.parse(e.target.result);
            if (validateData(json)) {
                setData(json, file.name);
            } else {
                alert('JSON no valido. Debe contener result.items y result.summary.');
            }
        } catch (err) {
            alert('Error al leer JSON: ' + err.message);
        }
    };
    reader.readAsText(file);
}

async function loadDemoData() {
    try {
        const resp = await fetch('data/demo_data.json');
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const json = await resp.json();
        if (validateData(json)) {
            setData(json, 'demo_data.json');
        }
    } catch (err) {
        alert('No se pudo cargar demo_data.json: ' + err.message +
              '\n\nSi abriste el fichero directamente (file://), usa un servidor local:\n' +
              'python -m http.server 8080 --directory viewer/');
    }
}

function validateData(json) {
    return json && json.result && Array.isArray(json.result.items) && json.result.summary;
}

function setData(json, filename) {
    state.data = json;
    state.items = json.result.items;
    state.filtered = [...state.items];
    state.filters = { status: [], categories: [], risks: [], search: '' };
    state.sort = { col: null, dir: 'asc' };

    // Show app, hide drop zone
    document.getElementById('drop-zone').classList.add('hidden');
    document.getElementById('app').classList.remove('hidden');
    document.getElementById('footer').classList.remove('hidden');

    // Show filename
    const badge = document.getElementById('file-name');
    badge.textContent = filename;
    badge.classList.remove('hidden');

    // Build UI
    buildFilters();
    renderAll();
}

// ── Dashboard Rendering ──────────────────────────────────────────────────
function renderAll() {
    applyFilters();
    renderScoreCard();
    renderStatusCards();
    renderStatusChart();
    renderCategoryChart();
    renderGapsList();
    renderTable();
    renderFooter();
    updateFilterCount();
}

function renderScoreCard() {
    const score = state.data.result.overall_score;
    const el = document.getElementById('score-value');
    el.textContent = score.toFixed(1) + '%';
    el.className = 'score-value ' +
        (score >= 80 ? 'score-green' : score >= 50 ? 'score-orange' : 'score-red');

    const ids = document.getElementById('score-ids');
    const r = state.data.result;
    ids.innerHTML = `${r.product_id || ''}<br>${r.tender_id || ''}`;
}

function renderStatusCards() {
    const s = state.data.result.summary;
    const total = s.total_requirements || 1;

    const cards = [
        { id: 'card-compliant', count: s.compliant_count },
        { id: 'card-non_compliant', count: s.non_compliant_count },
        { id: 'card-partial', count: s.partial_count },
        { id: 'card-clarification', count: s.clarification_count },
    ];

    cards.forEach(({ id, count }) => {
        const card = document.getElementById(id);
        card.querySelector('.card-count').textContent = count;
        card.querySelector('.card-pct').textContent = ((count / total) * 100).toFixed(1) + '%';
    });

    // Click on card to filter
    document.getElementById('card-compliant').onclick = () => toggleStatusFilter('compliant');
    document.getElementById('card-non_compliant').onclick = () => toggleStatusFilter('non_compliant');
    document.getElementById('card-partial').onclick = () => toggleStatusFilter('partial');
    document.getElementById('card-clarification').onclick = () => toggleStatusFilter('clarification_needed');
}

function toggleStatusFilter(status) {
    const idx = state.filters.status.indexOf(status);
    if (idx >= 0) {
        state.filters.status.splice(idx, 1);
    } else {
        state.filters.status = [status];
    }
    syncFilterUI();
    renderAll();
}

function renderStatusChart() {
    const counts = {};
    state.items.forEach(item => {
        counts[item.status] = (counts[item.status] || 0) + 1;
    });

    const labels = Object.keys(counts).map(s => STATUS_LABELS[s] || s);
    const data = Object.values(counts);
    const colors = Object.keys(counts).map(s => STATUS_COLORS[s] || '#999');

    const ctx = document.getElementById('status-chart').getContext('2d');
    if (statusChart) statusChart.destroy();
    statusChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{ data, backgroundColor: colors, borderWidth: 2, borderColor: '#fff' }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { position: 'right', labels: { boxWidth: 12, padding: 10, font: { size: 11 } } },
            },
        },
    });
}

function renderCategoryChart() {
    // Build category → status counts
    const catStatus = {};
    state.items.forEach(item => {
        if (!catStatus[item.category]) catStatus[item.category] = {};
        catStatus[item.category][item.status] = (catStatus[item.category][item.status] || 0) + 1;
    });

    const categories = Object.keys(catStatus).sort();
    const allStatuses = [...new Set(state.items.map(i => i.status))];

    const datasets = allStatuses.map(status => ({
        label: STATUS_LABELS[status] || status,
        data: categories.map(cat => catStatus[cat][status] || 0),
        backgroundColor: STATUS_COLORS[status] || '#999',
    }));

    const ctx = document.getElementById('category-chart').getContext('2d');
    if (categoryChart) categoryChart.destroy();
    categoryChart = new Chart(ctx, {
        type: 'bar',
        data: { labels: categories, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            scales: {
                x: { stacked: true, ticks: { font: { size: 11 } } },
                y: { stacked: true, beginAtZero: true, ticks: { stepSize: 1 } },
            },
            plugins: {
                legend: { position: 'top', labels: { boxWidth: 12, padding: 8, font: { size: 10 } } },
            },
        },
    });
}

function renderGapsList() {
    const s = state.data.result.summary;

    const dqList = document.getElementById('disqualifying-list');
    const devList = document.getElementById('deviations-list');
    const alertsRow = document.getElementById('alerts-row');

    const hasGaps = (s.disqualifying_gaps && s.disqualifying_gaps.length > 0);
    const hasDevs = (s.key_deviations && s.key_deviations.length > 0);

    if (!hasGaps && !hasDevs) {
        alertsRow.classList.add('hidden');
        return;
    }
    alertsRow.classList.remove('hidden');

    const dqBox = document.getElementById('alert-disqualifying');
    const devBox = document.getElementById('alert-deviations');

    if (hasGaps) {
        dqBox.classList.remove('hidden');
        dqList.innerHTML = s.disqualifying_gaps.map(g => `<li>${escapeHtml(g)}</li>`).join('');
    } else {
        dqBox.classList.add('hidden');
    }

    if (hasDevs) {
        devBox.classList.remove('hidden');
        devList.innerHTML = s.key_deviations.map(d => `<li>${escapeHtml(d)}</li>`).join('');
    } else {
        devBox.classList.add('hidden');
    }
}

// ── Filters ──────────────────────────────────────────────────────────────
function buildFilters() {
    // Status filter checkboxes
    const statusContainer = document.getElementById('status-filters');
    const allStatuses = [...new Set(state.items.map(i => i.status))];
    statusContainer.innerHTML = allStatuses.map(s =>
        `<label data-status="${s}">
            <input type="checkbox" value="${s}"> ${STATUS_LABELS[s] || s}
        </label>`
    ).join('');

    // Category checkboxes
    const catContainer = document.getElementById('category-filters');
    const allCats = [...new Set(state.items.map(i => i.category))].sort();
    catContainer.innerHTML = allCats.map(c =>
        `<label data-category="${c}">
            <input type="checkbox" value="${c}"> ${c}
        </label>`
    ).join('');

    // Risk filter checkboxes
    const riskContainer = document.getElementById('risk-filters');
    const allRisks = [...new Set(state.items.map(i => i.risk_level))];
    const riskOrder = ['disqualifying', 'high', 'medium', 'low'];
    const sortedRisks = riskOrder.filter(r => allRisks.includes(r));
    riskContainer.innerHTML = sortedRisks.map(r =>
        `<label data-risk="${r}">
            <input type="checkbox" value="${r}"> ${RISK_LABELS[r] || r}
        </label>`
    ).join('');
}

function setupFilterListeners() {
    // Status checkboxes
    document.getElementById('status-filters').addEventListener('change', (e) => {
        if (e.target.type === 'checkbox') {
            const val = e.target.value;
            const label = e.target.closest('label');
            if (e.target.checked) {
                state.filters.status.push(val);
                label.classList.add('active');
            } else {
                state.filters.status = state.filters.status.filter(s => s !== val);
                label.classList.remove('active');
            }
            renderAll();
        }
    });

    // Category checkboxes
    document.getElementById('category-filters').addEventListener('change', (e) => {
        if (e.target.type === 'checkbox') {
            const val = e.target.value;
            const label = e.target.closest('label');
            if (e.target.checked) {
                state.filters.categories.push(val);
                label.classList.add('active');
            } else {
                state.filters.categories = state.filters.categories.filter(c => c !== val);
                label.classList.remove('active');
            }
            renderAll();
        }
    });

    // Risk checkboxes
    document.getElementById('risk-filters').addEventListener('change', (e) => {
        if (e.target.type === 'checkbox') {
            const val = e.target.value;
            const label = e.target.closest('label');
            if (e.target.checked) {
                state.filters.risks.push(val);
                label.classList.add('active');
            } else {
                state.filters.risks = state.filters.risks.filter(r => r !== val);
                label.classList.remove('active');
            }
            renderAll();
        }
    });

    // Search
    let searchTimeout;
    document.getElementById('search-input').addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            state.filters.search = e.target.value.toLowerCase().trim();
            renderAll();
        }, 200);
    });

    // Clear filters
    document.getElementById('clear-filters-btn').addEventListener('click', () => {
        state.filters = { status: [], categories: [], risks: [], search: '' };
        document.getElementById('search-input').value = '';
        syncFilterUI();
        renderAll();
    });
}

function syncFilterUI() {
    // Sync status checkboxes
    document.querySelectorAll('#status-filters label').forEach(label => {
        const cb = label.querySelector('input');
        const isActive = state.filters.status.includes(cb.value);
        cb.checked = isActive;
        label.classList.toggle('active', isActive);
    });
    // Sync category checkboxes
    document.querySelectorAll('#category-filters label').forEach(label => {
        const cb = label.querySelector('input');
        const isActive = state.filters.categories.includes(cb.value);
        cb.checked = isActive;
        label.classList.toggle('active', isActive);
    });
    // Sync risk checkboxes
    document.querySelectorAll('#risk-filters label').forEach(label => {
        const cb = label.querySelector('input');
        const isActive = state.filters.risks.includes(cb.value);
        cb.checked = isActive;
        label.classList.toggle('active', isActive);
    });
}

function applyFilters() {
    let items = [...state.items];

    // Status filter
    if (state.filters.status.length > 0) {
        items = items.filter(i => state.filters.status.includes(i.status));
    }

    // Category filter
    if (state.filters.categories.length > 0) {
        items = items.filter(i => state.filters.categories.includes(i.category));
    }

    // Risk filter
    if (state.filters.risks.length > 0) {
        items = items.filter(i => state.filters.risks.includes(i.risk_level));
    }

    // Text search
    if (state.filters.search) {
        const q = state.filters.search;
        items = items.filter(i =>
            (i.requirement_id || '').toLowerCase().includes(q) ||
            (i.requirement_text || '').toLowerCase().includes(q) ||
            (i.product_value || '').toLowerCase().includes(q) ||
            (i.tender_value || '').toLowerCase().includes(q) ||
            (i.gap_description || '').toLowerCase().includes(q) ||
            (i.category || '').toLowerCase().includes(q) ||
            (i.source_section || '').toLowerCase().includes(q)
        );
    }

    // Sort
    if (state.sort.col) {
        const col = state.sort.col;
        const dir = state.sort.dir === 'asc' ? 1 : -1;
        items.sort((a, b) => {
            const va = (a[col] || '').toString().toLowerCase();
            const vb = (b[col] || '').toString().toLowerCase();
            return va < vb ? -dir : va > vb ? dir : 0;
        });
    }

    state.filtered = items;
}

function updateFilterCount() {
    document.getElementById('filter-count').textContent =
        `${state.filtered.length} / ${state.items.length}`;
}

// ── Table ────────────────────────────────────────────────────────────────
function renderTable() {
    const tbody = document.getElementById('items-tbody');
    const empty = document.getElementById('table-empty');

    if (state.filtered.length === 0) {
        tbody.innerHTML = '';
        empty.classList.remove('hidden');
        return;
    }
    empty.classList.add('hidden');

    tbody.innerHTML = state.filtered.map(item => `
        <tr data-id="${item.requirement_id}">
            <td class="cell-mono">${escapeHtml(item.requirement_id || '')}</td>
            <td class="cell-mono">${escapeHtml(item.source_section || '-')}</td>
            <td><span class="badge badge-category">${escapeHtml(item.category || '')}</span></td>
            <td>${escapeHtml(truncate(item.requirement_text, 80))}</td>
            <td class="cell-mono">${item.product_value ? escapeHtml(item.product_value) : '<span class="cell-null">-</span>'}</td>
            <td class="cell-mono">${escapeHtml(item.tender_value || '-')}</td>
            <td><span class="badge badge-${item.status}">${STATUS_LABELS[item.status] || item.status}</span></td>
            <td><span class="badge badge-risk-${item.risk_level}">${RISK_LABELS[item.risk_level] || item.risk_level}</span></td>
        </tr>
    `).join('');

    // Row click → detail
    tbody.querySelectorAll('tr').forEach(tr => {
        tr.addEventListener('click', () => {
            const id = tr.dataset.id;
            const item = state.items.find(i => i.requirement_id === id);
            if (item) showDetail(item);
        });
    });
}

function setupTableSort() {
    document.querySelectorAll('.items-table th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const col = th.dataset.col;
            if (state.sort.col === col) {
                state.sort.dir = state.sort.dir === 'asc' ? 'desc' : 'asc';
            } else {
                state.sort.col = col;
                state.sort.dir = 'asc';
            }
            // Update sort arrows
            document.querySelectorAll('.items-table th').forEach(h => {
                h.classList.remove('sorted');
                const arrow = h.querySelector('.sort-arrow');
                if (arrow) arrow.remove();
            });
            th.classList.add('sorted');
            const arrow = document.createElement('span');
            arrow.className = 'sort-arrow';
            arrow.textContent = state.sort.dir === 'asc' ? ' \u25B2' : ' \u25BC';
            th.appendChild(arrow);

            renderAll();
        });
    });
}

// ── Detail Panel ─────────────────────────────────────────────────────────
function setupDetailPanel() {
    document.getElementById('detail-close').addEventListener('click', closeDetail);
    document.getElementById('detail-overlay').addEventListener('click', closeDetail);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeDetail();
    });
}

function showDetail(item) {
    const panel = document.getElementById('detail-panel');
    const overlay = document.getElementById('detail-overlay');
    const body = document.getElementById('detail-body');
    const title = document.getElementById('detail-title');

    title.textContent = item.requirement_id;

    body.innerHTML = `
        <div class="detail-field">
            <div class="detail-field-label">Status</div>
            <div class="detail-field-value">
                <span class="badge badge-${item.status}">${STATUS_LABELS[item.status] || item.status}</span>
                <span class="badge badge-risk-${item.risk_level}" style="margin-left: 6px">${RISK_LABELS[item.risk_level] || item.risk_level}</span>
            </div>
        </div>

        <div class="detail-field">
            <div class="detail-field-label">Categor&iacute;a</div>
            <div class="detail-field-value">
                <span class="badge badge-category">${escapeHtml(item.category || '')}</span>
                ${item.source_section ? `<span style="margin-left: 8px; color: #6b7280; font-size: 0.85rem">Secci&oacute;n ${escapeHtml(item.source_section)}</span>` : ''}
            </div>
        </div>

        <hr class="detail-divider">

        <div class="detail-field">
            <div class="detail-field-label">Requisito</div>
            <div class="detail-field-value">${escapeHtml(item.requirement_text || '')}</div>
        </div>

        <div class="detail-comparison">
            <div>
                <div class="comp-label">Producto ofrece</div>
                <div class="comp-value">${item.product_value ? escapeHtml(item.product_value) : '<span class="cell-null">No especificado</span>'}</div>
            </div>
            <div>
                <div class="comp-label">Tender requiere</div>
                <div class="comp-value">${escapeHtml(item.tender_value || '-')}</div>
            </div>
        </div>

        ${item.gap_description ? `
            <div class="detail-field">
                <div class="detail-field-label">Gap / Desviaci&oacute;n</div>
                <div class="detail-gap">${escapeHtml(item.gap_description)}</div>
            </div>
        ` : ''}

        ${item.modification_needed ? `
            <div class="detail-field">
                <div class="detail-field-label">Modificaci&oacute;n necesaria</div>
                <div class="detail-field-value">${escapeHtml(item.modification_needed)}</div>
            </div>
        ` : ''}

        ${item.cost_impact ? `
            <hr class="detail-divider">
            <div class="detail-field">
                <div class="detail-field-label">Impacto de coste</div>
                <div class="detail-field-value mono">
                    ${item.cost_impact.estimated_delta_eur.toLocaleString('es-ES')} EUR
                    (confianza: ${item.cost_impact.confidence})
                    ${item.cost_impact.notes ? `<br><span style="color: #6b7280">${escapeHtml(item.cost_impact.notes)}</span>` : ''}
                </div>
            </div>
        ` : ''}

        ${item.source_document ? `
            <hr class="detail-divider">
            <div class="detail-field">
                <div class="detail-field-label">Documento fuente</div>
                <div class="detail-field-value cell-mono" style="font-size: 0.8rem">${escapeHtml(item.source_document)}</div>
            </div>
        ` : ''}
    `;

    panel.classList.remove('hidden');
    overlay.classList.remove('hidden');
    // Trigger animation
    requestAnimationFrame(() => {
        panel.classList.add('open');
        overlay.classList.add('open');
    });
}

function closeDetail() {
    const panel = document.getElementById('detail-panel');
    const overlay = document.getElementById('detail-overlay');
    panel.classList.remove('open');
    overlay.classList.remove('open');
    setTimeout(() => {
        panel.classList.add('hidden');
        overlay.classList.add('hidden');
    }, 300);
}

// ── Footer ───────────────────────────────────────────────────────────────
function renderFooter() {
    const run = state.data.run || {};
    const stats = state.data.engine_stats || {};
    const parts = [];

    if (run.timestamp) parts.push(`Run: ${run.timestamp}`);
    if (run.provider && run.provider !== 'none') parts.push(`Provider: ${run.provider}`);
    if (run.model && run.model !== 'none') parts.push(`Model: ${run.model}`);
    if (run.eval_time_s) parts.push(`Tiempo: ${run.eval_time_s}s`);
    if (run.llm_cost) parts.push(`Coste LLM: $${run.llm_cost.toFixed(4)}`);
    if (run.llm_calls) parts.push(`Llamadas LLM: ${run.llm_calls}`);

    // Matcher stats
    const matchers = Object.entries(stats)
        .filter(([k, v]) => k !== 'total' && v > 0)
        .map(([k, v]) => `${k}: ${v}`)
        .join(', ');
    if (matchers) parts.push(`Matchers: ${matchers}`);

    document.getElementById('footer-meta').textContent = parts.join('  |  ');
}

// ── CSV Export ───────────────────────────────────────────────────────────
function setupExport() {
    document.getElementById('export-btn').addEventListener('click', () => {
        if (state.filtered.length === 0) return;

        const headers = [
            'requirement_id', 'source_section', 'category', 'requirement_text',
            'product_value', 'tender_value', 'status', 'risk_level', 'gap_description'
        ];
        const csvRows = [headers.join(';')];

        state.filtered.forEach(item => {
            const row = headers.map(h => {
                const val = (item[h] || '').toString().replace(/"/g, '""');
                return `"${val}"`;
            });
            csvRows.push(row.join(';'));
        });

        const blob = new Blob(['\uFEFF' + csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `compliance_export_${state.filtered.length}items.csv`;
        a.click();
        URL.revokeObjectURL(url);
    });
}

// ── Helpers ──────────────────────────────────────────────────────────────
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function truncate(str, maxLen) {
    if (!str) return '';
    return str.length > maxLen ? str.substring(0, maxLen) + '...' : str;
}
