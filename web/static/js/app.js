/**
 * DMR-ML - 前端逻辑 v2
 * ========================
 * 全屏滚动吸附 + 可收缩侧边栏
 */

// ── 模型预设 ──
const MODEL_PRESETS = {
    adagio: { name: 'Adagio', momentum_window: 20, ma_window: 14, risk_trigger: 0.40, risk_release: 0.33 },
    presto: { name: 'Presto', momentum_window: 10, ma_window: 14, risk_trigger: 0.40, risk_release: 0.33 },
};
let currentModel = 'adagio';
const RUBATO_NAME = 'Rubato';

// ── 全局参数 ──
function getParams() {
    return {
        momentum_window: parseInt(document.getElementById('momentum-window').value),
        ma_window: parseInt(document.getElementById('ma-window').value),
        risk_trigger: parseInt(document.getElementById('risk-trigger').value) / 100,
        risk_release: parseInt(document.getElementById('risk-release').value) / 100,
        include_dmr: document.getElementById('show-dmr').checked,
        include_bench: document.getElementById('show-bench').checked,
        log_scale: document.getElementById('log-scale').checked,
    };
}

function buildQuery(params, keys) {
    return keys.map(k => `${k}=${encodeURIComponent(params[k])}`).join('&');
}

// ── API 请求 ──
async function api(path) {
    const resp = await fetch(path);
    if (!resp.ok) throw new Error(`API error: ${resp.status}`);
    return resp.json();
}

// ── 格式化工具 ──
function pct(v, d = 2) { return (v * 100).toFixed(d) + '%'; }
function num(v, d = 2) { return v.toFixed(d); }
function sign(v) { return v >= 0 ? '+' : ''; }

// ── 指标卡片 guide 文案 ──
const METRIC_GUIDES = {
    '累计收益':  { desc: '从第一天跑到现在，一共赚了多少', max: 300 },
    '年化收益':  { desc: '按复利折算成每年的收益率，方便横向比较', max: 50 },
    '最大回撤':  { desc: '历史上最深的一次回撤幅度，越小越安心', max: 50 },
    '夏普比率':  { desc: '每承担一份风险换回多少超额收益', max: 2 },
    '胜率':      { desc: '赚钱的交易占总交易次数的比例', max: 100 },
};

// ── 渲染指标卡片 ──
function renderMetricCard(label, value, delta, deltaPositive, rawValue) {
    let deltaHTML = '';
    if (delta !== undefined && delta !== null) {
        const cls = deltaPositive ? 'positive' : 'negative';
        const parts = delta.split('|');
        const labelPart = parts.length > 1 ? `<span class="metric-delta-label">${parts[0]}</span><br>` : '';
        const valuePart = parts.length > 1 ? parts[1] : parts[0];
        deltaHTML = `<div class="metric-delta ${cls}">${labelPart}${valuePart}</div>`;
    }
    const g = METRIC_GUIDES[label] || {};
    const guideAttrs = g.desc
        ? ` data-guide-title="${label}" data-guide-desc="${g.desc}" data-guide-max="${g.max || 100}" data-guide-raw="${rawValue !== undefined ? rawValue : 0}" data-guide-display="${value}"`
        : '';
    return `
        <div class="metric-card"${guideAttrs}>
            <div class="metric-label">${label}</div>
            <div class="metric-value">${value}</div>
            ${deltaHTML}
        </div>
    `;
}

// ── Plotly 图表渲染 ──
function renderChart(elementId, figData) {
    const el = document.getElementById(elementId);
    if (!el) return;
    const layout = figData.layout || {};
    layout.autosize = true;
    layout.margin = layout.margin || { l: 50, r: 30, t: 40, b: 40 };
    // 让 flex 容器控制大小，删除后端固定高度
    delete layout.height;
    const isDark = document.body.classList.contains('dark-mode');
    if (isDark) {
        const fg = '#e0ddd8';
        const muted = '#908d88';
        const grid = '#2a2a2e';
        // 全局
        layout.paper_bgcolor = 'rgba(0,0,0,0)';
        layout.plot_bgcolor = 'rgba(0,0,0,0)';
        layout.font = Object.assign(layout.font || {}, { color: fg });
        if (layout.title && layout.title.font) layout.title.font.color = fg;
        if (layout.legend) {
            layout.legend.bgcolor = 'rgba(38,38,42,0.85)';
            layout.legend.bordercolor = grid;
            if (layout.legend.font) layout.legend.font.color = fg;
        }
        // hoverlabel
        layout.hoverlabel = { bgcolor: '#2a2a2e', font: { color: fg }, bordercolor: '#3a3a3e' };
        // 所有轴
        ['xaxis','yaxis','xaxis2','yaxis2','xaxis3','yaxis3','xaxis4','yaxis4'].forEach(ax => {
            if (!layout[ax]) return;
            layout[ax].gridcolor = grid;
            layout[ax].linecolor = grid;
            layout[ax].zerolinecolor = grid;
            layout[ax].tickfont = Object.assign(layout[ax].tickfont || {}, { color: muted });
            if (layout[ax].title_font) layout[ax].title_font.color = muted;
            if (layout[ax].title && layout[ax].title.font) layout[ax].title.font.color = muted;
        });
        // annotations
        if (layout.annotations) {
            layout.annotations = layout.annotations.map(a => {
                const copy = Object.assign({}, a);
                if (copy.font) copy.font = Object.assign({}, copy.font, { color: muted });
                else copy.font = { color: muted };
                if (copy.bgcolor) copy.bgcolor = 'rgba(38,38,42,0.9)';
                if (copy.bordercolor) copy.bordercolor = '#3a3a3e';
                return copy;
            });
        }
        // shapes (hlines etc)
        if (layout.shapes) {
            layout.shapes = layout.shapes.map(s => {
                const copy = Object.assign({}, s);
                if (copy.line && copy.line.color === '#2D2A26') {
                    copy.line = Object.assign({}, copy.line, { color: '#B8B2A8' });
                }
                return copy;
            });
        }
        // traces
        if (figData.data) {
            figData.data.forEach(trace => {
                if (trace.colorbar) {
                    trace.colorbar.tickfont = Object.assign(trace.colorbar.tickfont || {}, { color: muted });
                    if (trace.colorbar.title) {
                        if (trace.colorbar.title.font) trace.colorbar.title.font.color = muted;
                        else trace.colorbar.title.font = { color: muted };
                    }
                }
                if (trace.type === 'heatmap' && trace.textfont) {
                    trace.textfont.color = '#2D2A26';
                }
            });
        }
    }
    layout.dragmode = false;
    Plotly.react(el, figData.data, layout, {
        responsive: true,
        displayModeBar: false,
        scrollZoom: false,
    });
    // 确保图表尺寸与容器匹配
    requestAnimationFrame(() => Plotly.Plots.resize(el));
}


// ============================================================
// 侧边栏
// ============================================================
let _savedParams = null;   // 打开侧边栏时暂存的参数快照
let _refreshClicked = false; // 本次打开侧边栏期间是否点了刷新

function _snapshotParams() {
    return {
        momentum: document.getElementById('momentum-window').value,
        ma: document.getElementById('ma-window').value,
        trigger: document.getElementById('risk-trigger').value,
        release: document.getElementById('risk-release').value,
    };
}
function _restoreParams(snap) {
    if (!snap) return;
    const ids = [
        ['momentum-window', 'momentum-value', '', snap.momentum],
        ['ma-window', 'ma-value', '', snap.ma],
        ['risk-trigger', 'trigger-value', '%', snap.trigger],
        ['risk-release', 'release-value', '%', snap.release],
    ];
    ids.forEach(([sid, vid, suf, val]) => {
        const s = document.getElementById(sid);
        s.value = val;
        document.getElementById(vid).textContent = val + suf;
        updateSliderFill(s);
    });
}

function toggleSidebar() {
    const opening = !document.body.classList.contains('sidebar-open');
    if (opening) {
        // 打开：保存当前参数快照
        _savedParams = _snapshotParams();
        _refreshClicked = false;
    } else {
        // 关闭：如果没刷新，恢复参数
        if (!_refreshClicked) {
            _restoreParams(_savedParams);
        }
        _savedParams = null;
    }
    document.body.classList.toggle('sidebar-open');
}


// ============================================================
// Section 01: 策略概览
// ============================================================
async function loadOverview() {
    const p = getParams();
    const q = buildQuery(p, ['momentum_window', 'ma_window']);

    const data = await api(`/api/overview?${q}`);
    const ml = data.ml;
    const bench = data.benchmark;

    const container = document.getElementById('overview-metrics');
    container.innerHTML = [
        renderMetricCard('累计收益',
            pct(ml.total_return, 1),
            `vs 沪深300:|超额收益 ${sign(ml.total_return - bench.total_return)}${pct(ml.total_return - bench.total_return, 1)}`,
            ml.total_return > bench.total_return, (ml.total_return * 100).toFixed(1)),
        renderMetricCard('年化收益',
            pct(ml.annual_return, 1),
            `vs 沪深300:|超额收益 ${sign(ml.annual_return - bench.annual_return)}${pct(ml.annual_return - bench.annual_return, 1)}`,
            ml.annual_return > bench.annual_return, (ml.annual_return * 100).toFixed(1)),
        renderMetricCard('最大回撤',
            pct(ml.max_drawdown, 1),
            `vs 沪深300:|改善 ${pct(Math.abs(bench.max_drawdown - ml.max_drawdown), 1)}`,
            ml.max_drawdown > bench.max_drawdown, (Math.abs(ml.max_drawdown) * 100).toFixed(1)),
        renderMetricCard('夏普比率',
            num(ml.sharpe_ratio),
            `vs 沪深300:|超越 ${sign(ml.sharpe_ratio - bench.sharpe_ratio)}${num(ml.sharpe_ratio - bench.sharpe_ratio)}`,
            ml.sharpe_ratio > bench.sharpe_ratio, ml.sharpe_ratio.toFixed(2)),
        renderMetricCard('胜率',
            pct(ml.win_rate, 1),
            `交易统计:|盈亏比 ${num(ml.profit_loss_ratio)}`,
            true, (ml.win_rate * 100).toFixed(1)),
    ].join('');

    // 净值走势图
    const chartQ = buildQuery(p, ['momentum_window', 'ma_window', 'include_dmr', 'include_bench', 'log_scale']);
    const fig = await api(`/api/chart/equity?${chartQ}`);
    renderChart('chart-equity', fig);
}


// ============================================================
// Section 02: 今日信号
// ============================================================
async function loadSignal() {
    const p = getParams();
    const q = buildQuery(p, ['momentum_window', 'ma_window', 'risk_trigger', 'risk_release']);
    const signal = await api(`/api/signal?${q}`);

    const card = document.getElementById('signal-card');
    const isAlert = signal.ml_risk.is_alert;
    const badgeCls = isAlert ? 'alert' : 'safe';
    const badgeText = isAlert ? '避险' : '正常';

    card.innerHTML = `
        <div class="signal-position">${signal.final_signal}</div>
        <div class="signal-reason">${signal.final_reason}</div>
        <div class="signal-risk-badge ${badgeCls}">${badgeText}</div>
    `;

    const ind = signal.indicators;
    const indContainer = document.getElementById('indicator-cards');
    indContainer.innerHTML = renderIndicatorCard('沪深300', ind.csi300)
        + renderIndicatorCard('中证1000', ind.csi1000);

    const info = document.getElementById('signal-info');
    info.innerHTML = `
        <div class="info-box-title">信号解读</div>
        <div class="info-row"><span class="label">数据日期</span><span class="value">${signal.data_date}</span></div>
        <div class="info-row"><span class="label">DMR 信号</span><span class="value">${signal.dmr_signal}</span></div>
        <div class="info-row"><span class="label">ML 状态</span><span class="value">${isAlert ? '避险' : '正常'}</span></div>
        <div class="info-row"><span class="label">最终信号</span><span class="value" style="font-weight:700;color:var(--primary)">${signal.final_signal}</span></div>
        <div class="info-row"><span class="label">执行时点</span><span class="value">${signal.execution_time}</span></div>
    `;

    const gauge = document.getElementById('risk-gauge');
    const prob = signal.ml_risk.probability;
    const trigger = signal.ml_risk.trigger_threshold;
    const release = signal.ml_risk.release_threshold || 0.33;
    const barColor = isAlert ? 'var(--danger)' : 'var(--secondary)';
    const statusText = isAlert ? 'RISK OFF' : 'RISK CLEAR';
    gauge.innerHTML = `
        <div class="risk-gauge-title">ML 风险概率</div>
        <div class="risk-gauge-center">
            <div class="risk-gauge-big" style="color:${barColor}">${pct(prob, 1)}</div>
            <div class="risk-gauge-status" style="color:${barColor}">${statusText}</div>
        </div>
        <div class="risk-bar-track">
            <div class="risk-bar-fill" style="width:${prob * 100}%;background:${barColor}"></div>
            <div class="risk-bar-marker" style="left:${release * 100}%" title="解除阈值"></div>
            <div class="risk-bar-marker" style="left:${trigger * 100}%" title="触发阈值"></div>
        </div>
        <div class="risk-labels">
            <div class="risk-label-item" style="left:${release * 100}%">
                <span class="risk-metric-label">解除</span>
                <span class="risk-metric-value">${pct(release, 0)}</span>
            </div>
            <div class="risk-label-item" style="left:${trigger * 100}%">
                <span class="risk-metric-label">触发</span>
                <span class="risk-metric-value">${pct(trigger, 0)}</span>
            </div>
        </div>
    `;
}

function renderIndicatorCard(title, data) {
    const sigCls = data.signal ? 'bullish' : 'bearish';
    const sigText = data.signal ? '多头' : '空头';
    const momColor = data.momentum > 0 ? 'var(--success)' : 'var(--danger)';
    const momArrow = data.momentum > 0 ? '\u25B2' : '\u25BC';
    return `
        <div class="indicator-card">
            <div class="indicator-card-title">${title} 技术指标</div>
            <div class="indicator-row">
                <span class="label">现价</span>
                <span class="value">${data.price.toFixed(2)}</span>
            </div>
            <div class="indicator-row">
                <span class="label">动量</span>
                <span class="value" style="color:${momColor}">${momArrow} ${pct(data.momentum)}</span>
            </div>
            <div class="indicator-row">
                <span class="label">均线</span>
                <span class="value">${data.ma.toFixed(2)}</span>
            </div>
            <div class="indicator-row">
                <span class="label">偏离度</span>
                <span class="value">${pct(data.bias)}</span>
            </div>
            <div class="indicator-signal ${sigCls}">${sigText}</div>
        </div>
    `;
}


// ============================================================
// Section 03: 深度分析
// ============================================================
const chartLoaded = {};

async function loadAnalysisChart(tab) {
    const p = getParams();
    const q = buildQuery(p, ['momentum_window', 'ma_window']);

    if (chartLoaded[tab]) return;

    let endpoint, chartId;
    switch (tab) {
        case 'drawdown':    endpoint = 'drawdown';     chartId = 'chart-drawdown';     break;
        case 'heatmap':     endpoint = 'heatmap';      chartId = 'chart-heatmap';      break;
        case 'distribution': endpoint = 'distribution'; chartId = 'chart-distribution'; break;
        case 'sharpe':      endpoint = 'sharpe';       chartId = 'chart-sharpe';       break;
    }

    const fig = await api(`/api/chart/${endpoint}?${q}`);
    renderChart(chartId, fig);
    chartLoaded[tab] = true;
}


// ============================================================
// Section 04: 交易记录
// ============================================================
async function loadTrades() {
    const p = getParams();
    const q = buildQuery(p, ['momentum_window', 'ma_window']);
    const data = await api(`/api/trades/summary?${q}`);
    const s = data.summary;

    const container = document.getElementById('trade-metrics');
    container.innerHTML = [
        renderMetricCard('总交易次数', s.total_trades, null, null),
        renderMetricCard('盈利/亏损', `${s.winning_trades}/${s.losing_trades}`, null, null),
        renderMetricCard('平均持仓', num(s.avg_holding_days, 1) + ' 天', null, null),
        renderMetricCard('最佳单笔', pct(s.best_trade), null, true),
    ].join('');

    const table = document.getElementById('allocation-table');
    if (data.allocation && data.allocation.length > 0) {
        let html = `<thead><tr>
            <th>年份</th><th>沪深300 (天)</th><th>中证1000 (天)</th><th>空仓 (天)</th><th>市场风格</th>
        </tr></thead><tbody>`;
        for (const row of data.allocation) {
            html += `<tr>
                <td>${row['年份']}</td>
                <td>${row['沪深300 (天)']}</td>
                <td>${row['中证1000 (天)']}</td>
                <td>${row['空仓 (天)']}</td>
                <td>${row['市场风格']}</td>
            </tr>`;
        }
        html += '</tbody>';
        table.innerHTML = html;
    }

    await loadTradeSignals();
}

async function loadTradeSignals() {
    const p = getParams();
    const year = document.getElementById('trade-year').value;
    const asset = document.getElementById('trade-asset').value;
    const q = `year=${year}&asset=${asset}&momentum_window=${p.momentum_window}&ma_window=${p.ma_window}`;
    const fig = await api(`/api/chart/trade-signals?${q}`);
    renderChart('chart-trade-signals', fig);
}


// ============================================================
// 交易状态
// ============================================================
async function loadStatus() {
    const data = await api('/api/status');
    const badge = document.getElementById('status-badge');
    const text = document.getElementById('status-text');
    text.textContent = `${data.datetime} ${data.weekday} \u00B7 ${data.status}`;
    text.classList.add('typing-cursor');
    badge.className = 'status-badge ' + (data.is_trading ? 'trading' : 'closed');
}


// ============================================================
// 标签页切换
// ============================================================
function initTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
            document.getElementById('tab-' + tab).classList.add('active');
            loadAnalysisChart(tab);
            // 切换标签后触发 Plotly 重绘，修复宽度问题
            setTimeout(() => {
                const chartEl = document.getElementById('chart-' + tab);
                if (chartEl && chartEl.data) Plotly.Plots.resize(chartEl);
            }, 60);
        });
    });
}


// ============================================================
// 侧边栏滑块
// ============================================================
function updateSliderFill(slider) {
    const min = +slider.min, max = +slider.max, val = +slider.value;
    const pct = (val - min) / (max - min) * 100;
    slider.style.setProperty('--fill', pct + '%');
}

function initSliders() {
    const pairs = [
        ['momentum-window', 'momentum-value', ''],
        ['ma-window', 'ma-value', ''],
        ['risk-trigger', 'trigger-value', '%'],
        ['risk-release', 'release-value', '%'],
    ];
    pairs.forEach(([sliderId, valueId, suffix]) => {
        const slider = document.getElementById(sliderId);
        const display = document.getElementById(valueId);
        // 同步初始显示值为浏览器实际值
        display.textContent = slider.value + suffix;
        updateSliderFill(slider);
        slider.addEventListener('input', () => {
            display.textContent = slider.value + suffix;
            updateSliderFill(slider);
        });
    });
}

// 参数变更后重新加载（防抖）
let reloadTimer = null;
function initParamListeners() {
    // 显示类参数：静默刷新（不走 loader）
    const displayIds = ['show-dmr', 'show-bench', 'log-scale'];
    displayIds.forEach(id => {
        document.getElementById(id).addEventListener('change', () => {
            clearTimeout(reloadTimer);
            Object.keys(chartLoaded).forEach(k => delete chartLoaded[k]);
            reloadTimer = setTimeout(reloadAll, 300);
        });
    });

    // 策略参数：不自动刷新，只等用户点「刷新数据」按钮

    document.getElementById('trade-year').addEventListener('change', loadTradeSignals);
    document.getElementById('trade-asset').addEventListener('change', loadTradeSignals);
}


// ============================================================
// 点线导航 + 滚动吸附联动
// ============================================================
function initDotNav() {
    const mainContent = document.getElementById('main-content');
    const sections = document.querySelectorAll('.content-section');
    const dots = document.querySelectorAll('.dot-item');

    // 点击跳转
    dots.forEach(dot => {
        dot.addEventListener('click', () => {
            const target = document.getElementById(dot.dataset.section);
            if (target) {
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });

    // 滚动联动 + 切页入场动画
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                // 更新点线导航
                const id = entry.target.id;
                dots.forEach(d => d.classList.remove('active'));
                const active = document.querySelector(`.dot-item[data-section="${id}"]`);
                if (active) active.classList.add('active');
                // 触发入场动画
                entry.target.classList.add('section-active');
                // 确保图表在可见时正确填充容器
                setTimeout(() => {
                    entry.target.querySelectorAll('.chart-box').forEach(el => {
                        if (el.data) Plotly.Plots.resize(el);
                    });
                }, 100);
            } else {
                // 离开页面时移除，下次进入时重新播放
                entry.target.classList.remove('section-active');
            }
        });
    }, {
        root: mainContent,
        rootMargin: '-20% 0px -70% 0px',
    });

    sections.forEach(s => observer.observe(s));
}


// ============================================================
// 首屏滚动提示
// ============================================================
function initScrollHint() {
    const mainContent = document.getElementById('main-content');
    const hint = document.getElementById('scroll-hint');
    if (!hint) return;

    let hidden = false;
    mainContent.addEventListener('scroll', () => {
        if (!hidden && mainContent.scrollTop > 80) {
            hint.classList.add('hidden');
            hidden = true;
        }
    }, { passive: true });
}


// ============================================================
// 环形循环滚动（末页→淡出→瞬移首页→淡入）
// ============================================================
function initLoopScroll() {
    const mainContent = document.getElementById('main-content');
    const lastSection = document.getElementById('section-chart');
    let looping = false;

    function loopToFirst() {
        if (looping) return;
        looping = true;
        // 淡出
        mainContent.style.transition = 'opacity 0.35s ease';
        mainContent.style.opacity = '0';
        setTimeout(() => {
            // 瞬移到顶部（无动画）
            mainContent.style.scrollBehavior = 'auto';
            mainContent.scrollTop = 0;
            mainContent.style.scrollBehavior = 'smooth';
            // 淡入
            requestAnimationFrame(() => {
                mainContent.style.opacity = '1';
                setTimeout(() => {
                    mainContent.style.transition = '';
                    looping = false;
                }, 400);
            });
        }, 350);
    }

    mainContent.addEventListener('wheel', (e) => {
        if (e.deltaY > 0 && lastSection.classList.contains('section-active')) {
            e.preventDefault();
            loopToFirst();
        }
    }, { passive: false });

    // 触屏
    let touchStartY = 0;
    mainContent.addEventListener('touchstart', (e) => {
        touchStartY = e.touches[0].clientY;
    }, { passive: true });
    mainContent.addEventListener('touchend', (e) => {
        const diff = touchStartY - e.changedTouches[0].clientY;
        if (diff > 50 && lastSection.classList.contains('section-active')) {
            loopToFirst();
        }
    }, { passive: true });
}


// ============================================================
// 刷新数据
// ============================================================
async function refreshData() {
    _refreshClicked = true;
    const btn = document.getElementById('refresh-btn');
    btn.disabled = true;
    btn.textContent = '刷新中...';

    // 「确认参数·刷新数据」始终以 Rubato 模式运行——用当前滑杆参数刷新
    currentModel = 'rubato';
    document.getElementById('model-current-name').textContent = RUBATO_NAME;
    document.querySelectorAll('.model-option').forEach(el => el.classList.remove('selected'));
    syncSidebarModelTabs('rubato');

    // 重置数字动画标记
    document.querySelectorAll('.metric-value[data-animated]').forEach(el => {
        delete el.dataset.animated;
    });

    if (window.DMRLoader) DMRLoader.show('切换策略中 · ' + RUBATO_NAME);

    try {
        await api('/api/refresh');
        Object.keys(chartLoaded).forEach(k => delete chartLoaded[k]);
        await reloadAll();
    } catch (e) {
        alert('刷新失败: ' + e.message);
    }

    if (window.DMRLoader) DMRLoader.dataReady();
    btn.disabled = false;
    btn.textContent = '确认参数 · 刷新数据';
}


// ============================================================
// 邮箱订阅
// ============================================================
async function subscribeEmail() {
    const email = document.getElementById('subscribe-email').value.trim();
    const pushTime = document.getElementById('subscribe-time').value;
    const model = document.getElementById('subscribe-model').value;
    const msgEl = document.getElementById('subscribe-msg');

    if (!email) {
        msgEl.style.display = 'block';
        msgEl.style.color = 'var(--warning)';
        msgEl.textContent = '请输入邮箱地址';
        return;
    }

    try {
        const data = await api(`/api/subscribe?email=${encodeURIComponent(email)}&push_time=${encodeURIComponent(pushTime)}&model=${encodeURIComponent(model)}`);
        msgEl.style.display = 'block';
        if (data.status === 'ok') {
            msgEl.style.color = 'var(--success)';
            msgEl.textContent = data.message;
            document.getElementById('subscribe-email').value = '';
        } else {
            msgEl.style.color = 'var(--warning)';
            msgEl.textContent = data.message;
        }
    } catch (e) {
        msgEl.style.display = 'block';
        msgEl.style.color = 'var(--danger)';
        msgEl.textContent = '订阅失败: ' + e.message;
    }
}


async function unsubscribeEmail() {
    const email = document.getElementById('unsubscribe-email').value.trim();
    const msgEl = document.getElementById('unsubscribe-msg');

    if (!email) {
        msgEl.style.display = 'block';
        msgEl.style.color = 'var(--warning)';
        msgEl.textContent = '请输入邮箱地址';
        return;
    }

    try {
        const data = await api(`/api/unsubscribe?email=${encodeURIComponent(email)}`);
        msgEl.style.display = 'block';
        if (data.status === 'ok') {
            msgEl.style.color = 'var(--success)';
            msgEl.textContent = data.message;
            document.getElementById('unsubscribe-email').value = '';
        } else {
            msgEl.style.color = 'var(--warning)';
            msgEl.textContent = data.message;
        }
    } catch (e) {
        msgEl.style.display = 'block';
        msgEl.style.color = 'var(--danger)';
        msgEl.textContent = '操作失败: ' + e.message;
    }
}


// ============================================================
// 加载全部数据
// ============================================================
async function reloadAll() {
    // 清除分析图表缓存，确保切换模型后所有 tab 都重新加载
    Object.keys(chartLoaded).forEach(k => delete chartLoaded[k]);
    try {
        await loadStatus();
        await loadOverview();
        await loadSignal();
        // 加载当前激活的分析 tab
        const activeTab = document.querySelector('.tab-btn.active');
        const tab = activeTab ? activeTab.dataset.tab : 'drawdown';
        await loadAnalysisChart(tab);
        await loadTrades();
    } catch (e) {
        console.error('加载失败:', e);
    }
}


// ============================================================
// 数字滚动动画
// ============================================================
function animateNumbers(section) {
    const values = section.querySelectorAll('.metric-value');
    values.forEach(el => {
        if (el.dataset.animated) return;
        const text = el.textContent.trim();
        // 提取数字和后缀 (如 "326.5%" → 326.5, "%")
        const match = text.match(/^([+-]?)(\d+\.?\d*)\s*(.*)$/);
        if (!match) return;
        const prefix = match[1];
        const target = parseFloat(match[2]);
        const suffix = match[3];
        const decimals = match[2].includes('.') ? match[2].split('.')[1].length : 0;
        const duration = 1200;
        const start = performance.now();
        el.dataset.animated = '1';
        el.dataset.rolling = '1';

        function tick(now) {
            const elapsed = now - start;
            const progress = Math.min(elapsed / duration, 1);
            // ease-out cubic
            const ease = 1 - Math.pow(1 - progress, 3);
            const current = target * ease;
            el.textContent = prefix + current.toFixed(decimals) + suffix;
            if (progress < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
    });
}

// 监听 section-active 触发数字动画
function initNumberRolling() {
    const observer = new MutationObserver(mutations => {
        mutations.forEach(m => {
            if (m.type === 'attributes' && m.attributeName === 'class') {
                const section = m.target;
                if (section.classList.contains('section-active')) {
                    // 延迟等入场动画开始后再滚数字
                    setTimeout(() => animateNumbers(section), 400);
                } else {
                    // 离开时重置，下次进入重新播放
                    section.querySelectorAll('.metric-value[data-animated]').forEach(el => {
                        delete el.dataset.animated;
                    });
                }
            }
        });
    });
    document.querySelectorAll('.content-section').forEach(s => {
        observer.observe(s, { attributes: true });
    });
}


// ============================================================
// tsParticles 粒子背景
// ============================================================
function initParticles() {
    if (typeof tsParticles === 'undefined') return;
    tsParticles.load('particles-bg', {
        particles: {
            number: { value: 38, density: { enable: true, area: 1000 } },
            color: { value: ['#A0403C', '#3D5A80', '#B8B2A8'] },
            opacity: { value: 0.22, random: { enable: true, minimumValue: 0.06 } },
            size: { value: 2.6, random: { enable: true, minimumValue: 1 } },
            move: {
                enable: true, speed: 0.5,
                direction: 'none', random: true,
                outModes: { default: 'out' },
            },
            links: {
                enable: true,
                distance: 180,
                color: '#B8B2A8',
                opacity: 0.16,
                width: 1,
            },
        },
        interactivity: {
            events: {
                onHover: { enable: true, mode: 'grab' },
            },
            modes: {
                grab: { distance: 180, links: { opacity: 0.3 } },
            },
        },
        detectRetina: true,
    });
}


// ============================================================
// 打字光标效果（状态栏）
// ============================================================
function initTypingCursor() {
    const statusText = document.getElementById('status-text');
    if (statusText) statusText.classList.add('typing-cursor');
}


// ============================================================
// 指导模式
// ============================================================
function initGuideMode() {
    const panel = document.getElementById('guide-panel');
    const titleEl = document.getElementById('guide-panel-title');
    const descEl = document.getElementById('guide-panel-desc');
    const rangeRow = document.getElementById('guide-panel-range');
    const rangeLabel = document.getElementById('guide-panel-range-label');
    const barFill = document.getElementById('guide-panel-bar-fill');
    const toggle = document.getElementById('guide-mode');

    function bindTargets() {
        document.querySelectorAll('[data-guide-title]').forEach(el => {
            if (el._guideBound) return;
            el._guideBound = true;

            el.addEventListener('mouseenter', () => {
                if (!toggle.checked) return;
                const title = el.getAttribute('data-guide-title');
                const desc = el.getAttribute('data-guide-desc') || el.getAttribute('data-guide-content') || '';
                const rawVal = el.getAttribute('data-guide-raw');
                const maxVal = el.getAttribute('data-guide-max');
                const displayVal = el.getAttribute('data-guide-display') || '';
                if (!title) return;

                // 暂停 tips 循环，锁定为指标解读模式
                guideActive = true;
                stopTipCycle();

                titleEl.textContent = title;
                titleEl.style.color = '';
                descEl.textContent = desc;
                descEl.style.color = '';
                if (rawVal && maxVal) {
                    const raw = parseFloat(rawVal);
                    const max = parseFloat(maxVal);
                    const barPct = Math.min(Math.max((raw / max) * 100, 5), 100);
                    rangeRow.style.display = 'flex';
                    rangeLabel.textContent = displayVal;
                    barFill.style.width = barPct + '%';
                    barFill.setAttribute('data-pct', displayVal);
                } else {
                    rangeRow.style.display = 'none';
                }
                panel.style.maxWidth = 'none';
                panel.classList.add('visible');
                requestAnimationFrame(() => {
                    const natural = panel.scrollWidth;
                    const limit = Math.min(natural + 4, window.innerWidth * 0.45);
                    panel.style.maxWidth = Math.max(limit, 360) + 'px';
                });
            });

            el.addEventListener('mouseleave', () => {
                guideActive = false;
                panel.classList.remove('visible');
                // 恢复 tips 循环
                if (toggle.checked) {
                    tipPhase = 'idle';
                    setTimeout(() => {
                        if (!guideActive && toggle.checked) {
                            showTip();
                            tipPhase = 'showing';
                            startTipCycle();
                        }
                    }, 2000);
                }
            });
        });
    }

    bindTargets();
    // 动态内容加载后重新绑定
    const observer = new MutationObserver(() => bindTargets());
    observer.observe(document.getElementById('main-content'), { childList: true, subtree: true });

    // ── Tips 空闲循环 ──
    const IDLE_TIPS = [
        '左侧拉开面板里有策略原理的动画演示，可以点进去看看。',
        '左侧面板可以拖动滑块调整动量窗口和均线参数，刷新回测结果。',
        '目前有三个模型可以切换——Adagio 稳健、Presto 灵敏、Rubato 自定义参数。',
        '鼠标悬停在卡片上，会弹出对应指标的含义说明。',
        '左侧面板可以输入邮箱订阅每日交易信号，开盘前推送到邮箱。',
        '策略信号仅供参考，不构成投资建议。实际操作请结合自己的判断。',
        '第五页可以看到每一笔历史交易的明细，包括买卖时点和盈亏。',
        '深色模式可以在左侧面板里开启，长时间浏览更护眼。',
        '这个策略赚钱的核心不是"买得准"，而是"该跑的时候跑得快"。',
        '所有回测都扣除了手续费，尽量贴近真实交易条件。',
    ];
    let tipIdx = 0;
    let tipCycle = null;   // 整个循环 interval
    let tipDelay = null;   // 5秒延迟 timeout
    let tipPhase = 'idle'; // idle → showing → gap
    let guideActive = false; // 当前是否有指标解读显示

    function showTip() {
        if (guideActive) return; // 指标解读显示中，不覆盖
        titleEl.textContent = 'Tips';
        titleEl.style.color = '#3D5A80';
        descEl.textContent = IDLE_TIPS[tipIdx];
        descEl.style.color = '#3D5A80';
        rangeRow.style.display = 'none';
        panel.style.maxWidth = 'none';
        panel.classList.add('visible');
        requestAnimationFrame(() => {
            const natural = panel.scrollWidth;
            const limit = Math.min(natural + 4, window.innerWidth * 0.45);
            panel.style.maxWidth = Math.max(limit, 360) + 'px';
        });
    }

    function hideTip() {
        panel.classList.remove('visible');
    }

    function tickTipCycle() {
        if (guideActive) return; // 指标解读中，不打断
        if (tipPhase === 'showing') {
            hideTip();
            tipPhase = 'gap';
            if (tipCycle) clearInterval(tipCycle);
            tipCycle = setTimeout(() => {
                if (guideActive) return; // 再次检查
                tipIdx = (tipIdx + 1) % IDLE_TIPS.length;
                showTip();
                tipPhase = 'showing';
                tipCycle = setInterval(tickTipCycle, 3000);
            }, 2000);
        }
    }

    function startTipCycle() {
        if (tipCycle) return;
        tipCycle = setInterval(tickTipCycle, 3000);
    }

    function stopTipCycle() {
        if (tipCycle) { clearInterval(tipCycle); clearTimeout(tipCycle); tipCycle = null; }
        tipPhase = 'idle';
    }

    // guideActive 状态现在由 bindTargets 里的 mouseenter/mouseleave 统一管理

    // 开关变化时启动/停止 tips
    toggle.addEventListener('change', () => {
        if (toggle.checked) {
            startTipCycle();
        } else {
            stopTipCycle();
            panel.classList.remove('visible');
        }
    });

    // 页面加载后，如果 guide 模式已开启则自动启动 tips 循环
    if (toggle.checked) {
        // 延迟 3 秒后开始第一条
        setTimeout(() => {
            if (toggle.checked) {
                showTip();
                tipPhase = 'showing';
                startTipCycle();
            }
        }, 3000);
    }
}


// ============================================================
// 打开侧边栏 → 展开"关于 DMR-ML"
// ============================================================
function openAboutDMR() {
    // 打开侧边栏
    if (!document.body.classList.contains('sidebar-open')) {
        toggleSidebar();
    }
    // 展开"关于 DMR-ML" details
    const details = document.querySelectorAll('.sidebar-details');
    details.forEach(d => {
        if (d.querySelector('summary') && d.querySelector('summary').textContent.includes('关于 DMR-ML')) {
            d.open = true;
            setTimeout(() => d.scrollIntoView({ behavior: 'smooth', block: 'start' }), 300);
        }
    });
}

// ============================================================
// 侧边栏模型切换（与标题切换联动）
// ============================================================
const SIDEBAR_MODEL_HINTS = {
    adagio: '稳健低回撤 · 预设最优参数',
    presto: '灵敏搏收益 · 预设最优参数',
    rubato: '自定义参数 · 调整下方滑杆后刷新',
};

function selectModelSidebar(modelId) {
    // 同步到标题切换器
    selectModel(modelId);
    // 更新侧边栏 tab 选中状态
    document.querySelectorAll('.sidebar-model-tab').forEach(btn => {
        btn.classList.toggle('selected', btn.dataset.model === modelId);
    });
    // 更新提示文字
    const hint = document.getElementById('sidebar-model-hint');
    if (hint) hint.textContent = SIDEBAR_MODEL_HINTS[modelId] || '';
}

// 同步标题切换器选中状态到侧边栏
function syncSidebarModelTabs(modelId) {
    document.querySelectorAll('.sidebar-model-tab').forEach(btn => {
        btn.classList.toggle('selected', btn.dataset.model === modelId);
    });
    const hint = document.getElementById('sidebar-model-hint');
    if (hint) hint.textContent = SIDEBAR_MODEL_HINTS[modelId] || '';
}

// ============================================================
// 模型切换器
// ============================================================
function toggleModelMenu() {
    document.getElementById('model-switcher').classList.toggle('open');
}

// 点击外部关闭
document.addEventListener('click', (e) => {
    const switcher = document.getElementById('model-switcher');
    if (switcher && !switcher.contains(e.target)) {
        switcher.classList.remove('open');
    }
});

async function selectModel(modelId) {
    if (modelId === currentModel && modelId !== 'rubato') {
        document.getElementById('model-switcher').classList.remove('open');
        return;
    }

    const isRubato = modelId === 'rubato';
    currentModel = modelId;

    if (isRubato) {
        // Rubato: 只更新标题，不触发 loader，让用户去左侧调参后点刷新
        document.getElementById('model-current-name').textContent = RUBATO_NAME;
        document.querySelectorAll('.model-option').forEach(el => el.classList.remove('selected'));
        document.querySelector('.model-option[data-model="rubato"]')?.classList.add('selected');
        document.getElementById('model-switcher').classList.remove('open');
        syncSidebarModelTabs('rubato');
        return;
    }

    const preset = MODEL_PRESETS[modelId];
    document.getElementById('model-current-name').textContent = preset.name;
    document.querySelectorAll('.model-option').forEach(el => {
        el.classList.toggle('selected', el.dataset.model === modelId);
    });

    // 同步 sidebar sliders 到新参数
    const momSlider = document.getElementById('momentum-window');
    const maSlider = document.getElementById('ma-window');
    const trigSlider = document.getElementById('risk-trigger');
    const relSlider = document.getElementById('risk-release');
    momSlider.value = preset.momentum_window;
    maSlider.value = preset.ma_window;
    trigSlider.value = Math.round(preset.risk_trigger * 100);
    relSlider.value = Math.round(preset.risk_release * 100);
    document.getElementById('momentum-value').textContent = preset.momentum_window;
    document.getElementById('ma-value').textContent = preset.ma_window;
    document.getElementById('trigger-value').textContent = Math.round(preset.risk_trigger * 100) + '%';
    document.getElementById('release-value').textContent = Math.round(preset.risk_release * 100) + '%';
    [momSlider, maSlider, trigSlider, relSlider].forEach(updateSliderFill);
    document.getElementById('model-switcher').classList.remove('open');
    syncSidebarModelTabs(modelId);

    // 重置数字动画标记
    document.querySelectorAll('.metric-value[data-animated]').forEach(el => {
        delete el.dataset.animated;
    });

    // 显示 loading 动画
    if (window.DMRLoader) DMRLoader.show('切换策略中 · ' + preset.name);

    // 后台重新加载数据
    try {
        await api(`/api/init?model=${modelId}`);
        Object.keys(chartLoaded).forEach(k => delete chartLoaded[k]);
        await reloadAll();
    } catch (e) {
        console.error('模型切换失败:', e);
    }

    // 通知 loader 数据就绪
    if (window.DMRLoader) DMRLoader.dataReady();
}


// ============================================================
// 深色模式
// ============================================================
function _plotlyTheme(isDark) {
    const fg = isDark ? '#e0ddd8' : '#2D2A26';
    const muted = isDark ? '#908d88' : '#8B8680';
    const grid = isDark ? '#2a2a2e' : '#E8E4DE';
    const legendBg = isDark ? 'rgba(38,38,42,0.85)' : 'rgba(250,250,247,0.95)';
    const hoverBg = isDark ? '#2a2a2e' : '#fff';
    const hoverBorder = isDark ? '#3a3a3e' : '#ccc';
    const t = {
        'paper_bgcolor': isDark ? 'rgba(0,0,0,0)' : '#FAFAF7',
        'plot_bgcolor': isDark ? 'rgba(0,0,0,0)' : '#FAFAF7',
        'font.color': fg,
        'title.font.color': fg,
        'legend.font.color': fg,
        'legend.bgcolor': legendBg,
        'legend.bordercolor': grid,
        'hoverlabel.bgcolor': hoverBg,
        'hoverlabel.font.color': fg,
        'hoverlabel.bordercolor': hoverBorder,
    };
    ['xaxis','yaxis','xaxis2','yaxis2','xaxis3','yaxis3','xaxis4','yaxis4'].forEach(ax => {
        t[ax + '.gridcolor'] = grid;
        t[ax + '.linecolor'] = grid;
        t[ax + '.zerolinecolor'] = grid;
        t[ax + '.tickfont.color'] = muted;
        t[ax + '.title.font.color'] = muted;
    });
    return t;
}

function _applyThemeToEl(el, isDark) {
    if (!el || !el.data) return;
    const fg = isDark ? '#e0ddd8' : '#2D2A26';
    const muted = isDark ? '#908d88' : '#8B8680';
    const annotBg = isDark ? 'rgba(38,38,42,0.9)' : 'rgba(250,250,247,0.9)';
    const annotBorder = isDark ? '#3a3a3e' : '#E8E4DE';
    const layout = _plotlyTheme(isDark);
    // 处理 annotations 的字体颜色 + 背景色
    if (el.layout && el.layout.annotations) {
        const annots = el.layout.annotations.map(a => {
            const copy = Object.assign({}, a);
            if (copy.font) copy.font = Object.assign({}, copy.font, { color: muted });
            else copy.font = { color: muted };
            if (copy.bgcolor) copy.bgcolor = annotBg;
            if (copy.bordercolor) copy.bordercolor = annotBorder;
            return copy;
        });
        layout.annotations = annots;
    }
    // 处理 colorbar
    if (el.data) {
        el.data.forEach((trace, i) => {
            if (trace.colorbar) {
                layout['coloraxis.colorbar.tickfont.color'] = muted;
                layout['coloraxis.colorbar.title.font.color'] = muted;
            }
        });
    }
    Plotly.relayout(el, layout);
}

function applyDarkModeToCharts(isDark) {
    document.querySelectorAll('.chart-box').forEach(el => {
        _applyThemeToEl(el, isDark);
    });
}

function initDarkMode() {
    const toggle = document.getElementById('dark-mode-toggle');
    const saved = localStorage.getItem('dmr-dark-mode');
    if (saved === 'true') {
        document.body.classList.add('dark-mode');
        toggle.checked = true;
    }
    toggle.addEventListener('change', () => {
        const isDark = toggle.checked;
        document.body.classList.toggle('dark-mode', isDark);
        localStorage.setItem('dmr-dark-mode', isDark);
        applyDarkModeToCharts(isDark);
    });
}


// ============================================================
// 初始化
// ============================================================
async function init() {
    // 启动加载动画
    if (window.DMRLoader) DMRLoader.show();

    initTabs();
    initSliders();
    initParamListeners();
    initDotNav();
    initScrollHint();
    initLoopScroll();
    initNumberRolling();
    initParticles();
    initTypingCursor();
    initGuideMode();
    initDarkMode();

    try {
        await api(`/api/init?model=${currentModel}`);
        await reloadAll();
    } catch (e) {
        console.error('初始化失败:', e);
        return;
    }

    // 图表加载完成后，如果处于深色模式则更新图表配色
    if (document.body.classList.contains('dark-mode')) {
        applyDarkModeToCharts(true);
    }

    // 数据就绪，通知 loader（动画播完后自动消失）
    if (window.DMRLoader) DMRLoader.dataReady();

}

document.addEventListener('DOMContentLoaded', init);

// ── 首次访问侧边栏引导气泡（仅在 loader 消失后出现）──
(function() {
    if (localStorage.getItem('dmr-sidebar-hint-shown')) return;

    function showHintBubble() {
        const btn = document.getElementById('sidebar-toggle');
        if (!btn) return;
        const bubble = document.createElement('div');
        bubble.id = 'sidebar-hint-bubble';
        bubble.textContent = '模型切换、参数调整、显示设置，以及策略说明在此处';
        document.body.appendChild(bubble);
        const r = btn.getBoundingClientRect();
        bubble.style.top  = (r.bottom + 10) + 'px';
        bubble.style.left = r.left + 'px';
        requestAnimationFrame(() => bubble.classList.add('visible'));
        setTimeout(function() {
            bubble.classList.remove('visible');
            setTimeout(() => bubble.remove(), 400);
        }, 4000);
        localStorage.setItem('dmr-sidebar-hint-shown', '1');
    }

    // 监听 loader 隐藏：检测 #dmr-loader 获得 hidden 类
    const loaderEl = document.getElementById('dmr-loader');
    if (!loaderEl) return;
    const obs = new MutationObserver(function(mutations) {
        mutations.forEach(function(m) {
            if (m.type === 'attributes' && loaderEl.classList.contains('hidden')) {
                obs.disconnect();
                setTimeout(showHintBubble, 600); // loader 淡出后再出现
            }
        });
    });
    obs.observe(loaderEl, { attributes: true, attributeFilter: ['class'] });
})();
