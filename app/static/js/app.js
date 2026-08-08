const API_BASE = '';

let currentPage = 'dashboard';
let selectedKbName = null;
let importTaskFiles = [];

const API_KEY = 'kb-mcp-secret-key-2024';

const api = {
    async get(path, headers = null) {
        const res = await fetch(`${API_BASE}${path}`, { headers: headers || {} });
        const data = await res.json();
        if (data.code !== undefined && data.code !== 200) {
            throw new Error(data.message || '请求失败');
        }
        return data.data !== undefined ? data.data : data;
    },
    async post(path, body, isJson = true, headers = null) {
        const finalHeaders = isJson ? { 'Content-Type': 'application/json' } : {};
        if (headers) {
            Object.assign(finalHeaders, headers);
        }
        const res = await fetch(`${API_BASE}${path}`, {
            method: 'POST',
            headers: finalHeaders,
            body: isJson ? JSON.stringify(body) : body,
        });
        const data = await res.json();
        if (data.code !== undefined && data.code !== 200) {
            throw new Error(data.message || '请求失败');
        }
        return data.data !== undefined ? data.data : data;
    },
    async delete(path, headers = null) {
        const res = await fetch(`${API_BASE}${path}`, { method: 'DELETE', headers: headers || {} });
        const data = await res.json();
        if (data.code !== undefined && data.code !== 200) {
            throw new Error(data.message || '请求失败');
        }
        return data.data !== undefined ? data.data : data;
    },
    async put(path, body, headers = null) {
        const finalHeaders = { 'Content-Type': 'application/json' };
        if (headers) Object.assign(finalHeaders, headers);
        const res = await fetch(`${API_BASE}${path}`, {
            method: 'PUT',
            headers: finalHeaders,
            body: JSON.stringify(body),
        });
        const data = await res.json();
        if (data.code !== undefined && data.code !== 200) {
            throw new Error(data.message || '请求失败');
        }
        return data.data !== undefined ? data.data : data;
    },
    async upload(path, formData, headers = null) {
        const res = await fetch(`${API_BASE}${path}`, {
            method: 'POST',
            headers: headers || {},
            body: formData,
        });
        const data = await res.json();
        if (data.code !== undefined && data.code !== 200) {
            throw new Error(data.message || '请求失败');
        }
        return data.data !== undefined ? data.data : data;
    }
};

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const icons = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };
    toast.innerHTML = `<span>${icons[type] || 'ℹ'}</span><span>${message}</span>`;
    container.appendChild(toast);
    const duration = type === 'error' ? 6000 : 3500;
    setTimeout(() => {
        toast.style.transition = 'all 0.3s';
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

function setBtnLoading(btn, loading, originalText = null) {
    if (!btn) return;
    if (loading) {
        btn._origText = btn._origText || btn.innerHTML;
        btn.disabled = true;
        btn.style.opacity = '0.7';
        btn.style.pointerEvents = 'none';
        btn.innerHTML = '⏳ 处理中...';
    } else {
        btn.innerHTML = btn._origText || originalText || btn.innerHTML;
        btn.disabled = false;
        btn.style.opacity = '';
        btn.style.pointerEvents = '';
        delete btn._origText;
    }
}

function showModal(title, bodyHtml, onConfirm, options = {}) {
    document.getElementById('modalTitle').textContent = title;
    document.getElementById('modalBody').innerHTML = bodyHtml;
    document.getElementById('modalOverlay').classList.add('show');
    const confirmBtn = document.getElementById('modalConfirm');
    confirmBtn.style.display = options.hideConfirm ? 'none' : '';
    confirmBtn.style.visibility = '';
    const newBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newBtn, confirmBtn);
    newBtn.addEventListener('click', async () => {
        if (!onConfirm) { closeModal(); return; }
        setBtnLoading(newBtn, true);
        try {
            const r = onConfirm();
            if (r && r.then) await r;
            if (newBtn.parentNode) closeModal();
        } finally {
            setBtnLoading(newBtn, false);
        }
    });
}

function closeModal() {
    document.getElementById('modalOverlay').classList.remove('show');
}

function makeRefreshBtn(title, onClick) {
    const btn = document.createElement('button');
    btn.className = 'btn btn-sm btn-secondary';
    btn.innerHTML = '🔄 刷新';
    btn.title = title || '刷新';
    btn.addEventListener('click', () => {
        setBtnLoading(btn, true);
        const r = onClick();
        const done = () => setBtnLoading(btn, false);
        if (r && r.then) r.then(done).catch(done);
        else done();
    });
    return btn;
}

function renderErrorState(message, onRetry) {
    const retryBtn = onRetry ?
        `<button class="btn btn-primary" style="margin-top:12px;">🔁 重试</button>` : '';
    const html = `<div class="empty-state">
        <div class="empty-state-icon">❌</div>
        <div style="max-width:500px;">${message}</div>
        ${retryBtn}
    </div>`;
    const wrap = document.createElement('div');
    wrap.innerHTML = html;
    if (onRetry && wrap.querySelector('button')) {
        wrap.querySelector('button').addEventListener('click', onRetry);
    }
    return wrap.innerHTML;
}

function setPage(page) {
    currentPage = page;
    document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.toggle('active', el.dataset.page === page);
    });
    const titles = {
        dashboard: '系统概览',
        knowledge: '知识库管理',
        import: '文件导入',
        search: '知识检索',
        monitor: '系统监控',
        ocr: 'OCR状态',
        logs: '日志管理',
        mcp: 'MCP服务',
    };
    document.getElementById('pageTitle').textContent = titles[page] || page;
    loadPage(page);
}

async function checkConnection() {
    try {
        const data = await api.get('/api/health');
        const status = document.getElementById('sidebarStatus');
        status.querySelector('.status-text').textContent = '服务在线';
        status.querySelector('.status-dot').className = 'status-dot online';
    } catch (e) {
        const status = document.getElementById('sidebarStatus');
        status.querySelector('.status-text').textContent = '服务离线';
        status.querySelector('.status-dot').className = 'status-dot offline';
    }
}

async function loadPage(page) {
    const content = document.getElementById('contentArea');
    content.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-secondary);">⏳ 加载中...</div>';

    try {
        switch (page) {
            case 'dashboard':
                content.innerHTML = await renderDashboard();
                break;
            case 'knowledge':
                content.innerHTML = await renderKnowledge();
                break;
            case 'import':
                content.innerHTML = await renderImport();
                break;
            case 'search':
                content.innerHTML = renderSearch();
                break;
            case 'monitor':
                content.innerHTML = await renderMonitor();
                break;
            case 'ocr':
                content.innerHTML = await renderOCRPanel();
                break;
            case 'logs':
                content.innerHTML = await renderLogs();
                break;
            case 'mcp':
                content.innerHTML = renderMCP();
                break;
        }
        bindPageEvents(page);
    } catch (e) {
        content.innerHTML = renderErrorState('页面加载失败: ' + e.message, () => loadPage(page));
    }
}

async function renderDashboard() {
    try {
        const [status, resource, tasks] = await Promise.all([
            api.get('/api/monitor/status'),
            api.get('/api/monitor/resource'),
            api.get('/api/import/tasks').then(t => Array.isArray(t) ? t.slice(0, 5) : []).catch(() => []),
        ]);

        const recentRows = tasks.length > 0 ? `
            <table>
                <thead>
                    <tr><th>任务</th><th>知识库</th><th>总数</th><th>成功</th><th>失败</th><th>状态</th><th>创建时间</th><th>操作</th></tr>
                </thead>
                <tbody>
                    ${tasks.map(t => `
                        <tr>
                            <td>#${t.id} <small style="color:var(--text-light);">${t.task_type}</small></td>
                            <td>${t.kb_name}</td>
                            <td>${t.total_files}</td>
                            <td style="color:var(--success-color)">${t.success_count}</td>
                            <td style="color:var(--danger-color)">${t.fail_count}</td>
                            <td><span class="badge ${t.status === 'completed' ? 'badge-success' : t.status === 'running' ? 'badge-warning' : 'badge-secondary'}">${t.status}</span></td>
                            <td>${t.created_at}</td>
                            <td><button class="btn btn-sm btn-primary" onclick="viewTask(${t.id})">详情</button></td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        ` : `<div class="empty-state"><div class="empty-state-icon">📋</div><div>暂无导入任务</div></div>`;

        return `
            <div class="stats-grid">
                <div class="stat-card info">
                    <div class="stat-icon">📚</div>
                    <div class="stat-value">${status.total_kbs}</div>
                    <div class="stat-label">知识库总数</div>
                </div>
                <div class="stat-card success">
                    <div class="stat-icon">📄</div>
                    <div class="stat-value">${status.total_files}</div>
                    <div class="stat-label">文档总数</div>
                </div>
                <div class="stat-card warning">
                    <div class="stat-icon">🔢</div>
                    <div class="stat-value">${status.total_vectors.toLocaleString()}</div>
                    <div class="stat-label">向量总数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">📥</div>
                    <div class="stat-value">${status.today_imports}</div>
                    <div class="stat-label">今日导入</div>
                </div>
            </div>

            <div class="grid-2">
                <div class="card">
                    <div class="card-header"><div class="card-title">系统状态</div></div>
                    <table>
                        <tr><td>应用状态</td><td><span class="badge badge-success">${status.app_status}</span></td></tr>
                        <tr><td>Qdrant状态</td><td><span class="badge ${status.qdrant_status === 'connected' ? 'badge-success' : 'badge-danger'}">${status.qdrant_status}</span></td></tr>
                        <tr><td>运行时长</td><td>${Math.floor(status.uptime_seconds / 3600)}小时${Math.floor((status.uptime_seconds % 3600) / 60)}分</td></tr>
                        <tr><td>版本</td><td>${status.app_version}</td></tr>
                    </table>
                </div>
                <div class="card">
                    <div class="card-header"><div class="card-title">资源监控</div></div>
                    <table>
                        <tr><td>磁盘占用</td><td>${resource.disk_used_gb} / ${resource.disk_total_gb} GB (${resource.disk_usage_percent}%)</td></tr>
                        <tr><td>内存使用</td><td>${resource.memory_usage_percent}%</td></tr>
                        <tr><td>向量存储</td><td>${resource.vector_storage_mb} MB</td></tr>
                    </table>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <div class="card-title">最近导入任务</div>
                    <button class="btn btn-sm btn-secondary" onclick="loadPage('import')">查看全部 →</button>
                </div>
                ${recentRows}
            </div>
        `;
    } catch (e) {
        return renderErrorState('加载失败: ' + e.message, () => loadPage('dashboard'));
    }
}

async function renderKnowledge() {
    try {
        const kbs = await api.get('/api/kb');
        if (!kbs || kbs.length === 0) {
            return `
                <div class="card">
                    <div class="card-header">
                        <div class="card-title">知识库列表</div>
                        <button class="btn btn-primary" onclick="showCreateKb()">+ 新建知识库</button>
                    </div>
                    <div class="empty-state">
                        <div class="empty-state-icon">📚</div>
                        <div>暂无知识库，点击右上角新建</div>
                    </div>
                </div>
            `;
        }
        return `
            <div class="card">
                <div class="card-header">
                    <div class="card-title">知识库列表</div>
                    <button class="btn btn-primary" onclick="showCreateKb()">+ 新建知识库</button>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>知识库名称</th>
                            <th>文档数</th>
                            <th>向量数</th>
                            <th>创建时间</th>
                            <th>状态</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${kbs.map(kb => `
                            <tr>
                                <td><strong>${kb.name}</strong></td>
                                <td>${kb.doc_count}</td>
                                <td>${kb.vector_count.toLocaleString()}</td>
                                <td>${kb.created_at}</td>
                                <td><span class="badge badge-success">${kb.status}</span></td>
                                <td>
                                    <button class="btn btn-sm btn-primary" onclick="viewKb('${kb.name}')">查看</button>
                                    <button class="btn btn-sm btn-danger" onclick="deleteKb('${kb.name}')">删除</button>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    } catch (e) {
        return renderErrorState('知识库列表加载失败: ' + e.message, () => loadPage('knowledge'));
    }
}

async function renderImport() {
    try {
        const kbs = await api.get('/api/kb');
        const tasks = await api.get('/api/import/tasks');
        const savedKb = localStorage.getItem('kb:lastImport') || '';
        const savedChunkSize = localStorage.getItem('kb:chunkSize') || '500';
        const savedOverlap = localStorage.getItem('kb:chunkOverlap') || '50';
        const savedSeparator = localStorage.getItem('kb:chunkSeparator') || '';
        const autoSelectedKb = savedKb || (kbs && kbs.length === 1 ? kbs[0].name : '');

        const kbOptions = (kbs || []).map(kb =>
            `<option value="${kb.name}" ${kb.name === autoSelectedKb ? 'selected' : ''}>${kb.name}</option>`
        ).join('');

        if (!kbs || kbs.length === 0) {
            return `
                <div class="card">
                    <div class="card-header"><div class="card-title">文件导入</div></div>
                    <div class="empty-state">
                        <div class="empty-state-icon">⚠️</div>
                        <div>暂无知识库，请先到「知识库管理」新建一个知识库</div>
                        <button class="btn btn-primary" style="margin-top:12px;" onclick="setPage('knowledge')">去新建知识库</button>
                    </div>
                </div>
            `;
        }

        const tasksTable = `
            <table>
                <thead>
                    <tr>
                        <th>任务ID</th><th>知识库</th><th>类型</th><th>总数</th>
                        <th>成功</th><th>失败</th><th>状态</th><th>创建时间</th><th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    ${tasks && tasks.length > 0 ? tasks.map(t => `
                        <tr>
                            <td>#${t.id}</td><td>${t.kb_name}</td><td>${t.task_type}</td>
                            <td>${t.total_files}</td>
                            <td style="color:var(--success-color)">${t.success_count}</td>
                            <td style="color:var(--danger-color)">${t.fail_count}</td>
                            <td><span class="badge ${t.status === 'completed' ? 'badge-success' : t.status === 'running' ? 'badge-warning' : 'badge-secondary'}">${t.status}</span></td>
                            <td>${t.created_at}</td>
                            <td><button class="btn btn-sm btn-primary" onclick="viewTask(${t.id})">详情</button></td>
                        </tr>
                    `).join('') : '<tr><td colspan="9" style="text-align:center;color:var(--text-light);padding:40px;">暂无导入任务</td></tr>'}
                </tbody>
            </table>
        `;

        return `
            <div class="card">
                <div class="card-header"><div class="card-title">文件导入</div></div>
                <div class="form-group">
                    <label class="form-label">选择知识库</label>
                    <select class="form-control" id="importKb">
                        <option value="">请选择知识库</option>
                        ${kbOptions}
                    </select>
                </div>
                <div class="form-group" style="display:flex;gap:16px;align-items:flex-end;flex-wrap:wrap;">
                    <div style="flex:1;min-width:120px;">
                        <label class="form-label">切片长度 (字符)</label>
                        <input type="number" class="form-control" id="chunkSize" value="${savedChunkSize}" min="100" max="5000" step="50">
                        <small style="color:var(--text-secondary);">每个文本切片的最大字符数</small>
                    </div>
                    <div style="flex:1;min-width:100px;">
                        <label class="form-label">重叠长度 (字符)</label>
                        <input type="number" class="form-control" id="chunkOverlap" value="${savedOverlap}" min="0" max="1000" step="10">
                        <small style="color:var(--text-secondary);">相邻切片重叠的字符数</small>
                    </div>
                    <div style="flex:1.5;min-width:160px;">
                        <label class="form-label">自定义分隔符 (可选)</label>
                        <input type="text" class="form-control" id="chunkSeparator" value="${savedSeparator}" placeholder="留空=固定长度切片, 如: --- 或 ##">
                        <small style="color:var(--text-secondary);">按此符号先分割文本，再按切片长度切片。支持多字符分隔符</small>
                    </div>
                </div>
                <div class="tabs">
                    <div class="tab active" data-import-tab="single">单文件导入</div>
                    <div class="tab" data-import-tab="batch">批量导入</div>
                    <div class="tab" data-import-tab="folder">文件夹导入</div>
                    <div class="tab" data-import-tab="zip">压缩包导入</div>
                </div>
                <div id="importSingle">
                    <div class="file-upload" id="singleDrop">
                        <div class="file-upload-icon">📄</div>
                        <div class="file-upload-text" id="singleText">点击或拖拽文件到此处上传</div>
                        <div class="file-upload-hint">支持 PDF、Word(.doc/.docx)、TXT、Markdown、OFD、图片 格式，最大100MB</div>
                    </div>
                    <input type="file" id="singleFile" style="display:none" accept=".pdf,.doc,.docx,.txt,.md,.ofd,.png,.jpg,.jpeg,.bmp,.tiff,.tif,.gif">
                </div>
                <div id="importBatch" style="display:none">
                    <div class="file-upload" id="batchDrop">
                        <div class="file-upload-icon">📁</div>
                        <div class="file-upload-text" id="batchText">点击或拖拽多个文件到此处</div>
                        <div class="file-upload-hint">支持多文件批量上传</div>
                    </div>
                    <input type="file" id="batchFiles" multiple style="display:none" accept=".pdf,.doc,.docx,.txt,.md,.ofd,.png,.jpg,.jpeg,.bmp,.tiff,.tif,.gif">
                </div>
                <div id="importFolder" style="display:none">
                    <div class="file-upload" id="folderDrop">
                        <div class="file-upload-icon">📂</div>
                        <div class="file-upload-text" id="folderText">点击选择文件夹</div>
                        <div class="file-upload-hint">自动遍历文件夹及所有子文件夹中的文件并批量导入</div>
                    </div>
                    <input type="file" id="folderFiles" multiple style="display:none" webkitdirectory directory>
                </div>
                <div id="importZip" style="display:none">
                    <div class="file-upload" id="zipDrop">
                        <div class="file-upload-icon">🗜️</div>
                        <div class="file-upload-text" id="zipText">上传压缩包</div>
                        <div class="file-upload-hint">支持 ZIP、TAR、TAR.GZ、RAR、7Z 等压缩格式</div>
                    </div>
                    <input type="file" id="zipFile" style="display:none" accept=".zip,.rar,.7z,.tar,.tgz,.gz,.bz2,.xz">
                </div>
                <div id="importProgress" style="display:none;margin-top:20px;">
                    <div style="font-weight:600;margin-bottom:8px;">导入进度</div>
                    <div class="progress-bar"><div class="progress-bar-fill" id="progressFill" style="width:0%"></div></div>
                    <div id="importResult"></div>
                </div>
            </div>

            <div class="card">
                <div class="card-header"><div class="card-title">导入任务历史</div></div>
                ${tasksTable}
            </div>
        `;
    } catch (e) {
        return renderErrorState('页面加载失败: ' + e.message, () => loadPage('import'));
    }
}

function renderSearch() {
    const savedKb = localStorage.getItem('kb:lastSearchKb') || '';
    const savedTopK = localStorage.getItem('kb:lastTopK') || '5';
    const savedThreshold = localStorage.getItem('kb:lastThreshold') || '0.0';
    const savedReranker = localStorage.getItem('kb:lastUseReranker') || 'true';
    const savedRecallTopK = localStorage.getItem('kb:lastRecallTopK') || '10';
    const rerankerEnabled = savedReranker === 'true';
    return `
        <div class="card">
            <div class="card-header"><div class="card-title">知识检索</div></div>
            <div class="form-group">
                <label class="form-label">输入搜索问题</label>
                <textarea class="form-control" id="searchQuery" rows="3" placeholder="输入您的问题，按 Ctrl+Enter 或点「搜索」开始，例如：公司的考勤制度是什么？"></textarea>
            </div>
            <div class="grid-3">
                <div class="form-group">
                    <label class="form-label">知识库（可选）</label>
                    <select class="form-control" id="searchKb" data-saved="${savedKb}">
                        <option value="">全部知识库</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">返回数量</label>
                    <input type="number" class="form-control" id="searchTopK" value="${savedTopK}" min="1" max="50">
                </div>
                <div class="form-group">
                    <label class="form-label">相似度阈值 (0-1)</label>
                    <input type="number" class="form-control" id="searchThreshold" value="${savedThreshold}" min="0" max="1" step="0.05">
                </div>
            </div>
            <div class="form-group" style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">
                <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:14px;font-weight:500;">
                    <input type="checkbox" id="useReranker" ${rerankerEnabled ? 'checked' : ''} style="width:18px;height:18px;cursor:pointer;" onchange="toggleRecallTopK()">
                    <span>启用 Reranker 重排序</span>
                </label>
                <span style="color:var(--text-light);font-size:12px;">先召回指定数量 → 精排返回Top-K条</span>
            </div>
            <div id="recallTopKGroup" class="form-group" style="display:${rerankerEnabled ? 'flex' : 'none'};align-items:center;gap:12px;margin-bottom:12px;padding:10px 14px;background:#f8f9fa;border-radius:8px;border:1px solid var(--border-color);">
                <label style="font-size:13px;color:var(--text-secondary);white-space:nowrap;">第一阶段召回数量：</label>
                <input type="number" class="form-control" id="recallTopK" value="${savedRecallTopK}" min="1" max="200" style="width:100px;padding:4px 8px;">
                <span style="font-size:12px;color:var(--text-light);">默认10，需≥返回数量</span>
            </div>
            <button class="btn btn-primary" id="searchBtn" onclick="doSearch()">🔍 搜索</button>
            <small style="color:var(--text-secondary);margin-left:12px;">提示: 在输入框中按 Ctrl + Enter 快捷搜索</small>
        </div>
        <div id="searchResults"></div>
    `;
}

async function renderMonitor() {
    try {
        const status = await api.get('/api/monitor/status');
        const resource = await api.get('/api/monitor/resource');

        return `
            <div class="stats-grid">
                <div class="stat-card info">
                    <div class="stat-value">${Math.floor(status.uptime_seconds / 3600)}h</div>
                    <div class="stat-label">运行时长</div>
                </div>
                <div class="stat-card success">
                    <div class="stat-value">${status.total_vectors.toLocaleString()}</div>
                    <div class="stat-label">向量总数</div>
                </div>
                <div class="stat-card warning">
                    <div class="stat-value">${resource.disk_usage_percent}%</div>
                    <div class="stat-label">磁盘占用</div>
                </div>
                <div class="stat-card danger">
                    <div class="stat-value">${resource.memory_usage_percent}%</div>
                    <div class="stat-label">内存使用</div>
                </div>
            </div>

            <div class="card">
                <div class="card-header"><div class="card-title">系统信息</div></div>
                <table>
                    <tr><td>应用版本</td><td>${status.app_version}</td></tr>
                    <tr><td>应用状态</td><td><span class="badge badge-success">${status.app_status}</span></td></tr>
                    <tr><td>Qdrant状态</td><td><span class="badge ${status.qdrant_status === 'connected' ? 'badge-success' : 'badge-danger'}">${status.qdrant_status}</span></td></tr>
                    <tr><td>知识库数量</td><td>${status.total_kbs}</td></tr>
                    <tr><td>文档总数</td><td>${status.total_files}</td></tr>
                    <tr><td>今日导入</td><td>${status.today_imports} 个文件</td></tr>
                </table>
            </div>

            <div class="card">
                <div class="card-header"><div class="card-title">Qdrant集合列表</div></div>
                <table>
                    <thead>
                        <tr><th>集合名称</th><th>向量数</th><th>状态</th></tr>
                    </thead>
                    <tbody>
                        ${status.qdrant_collections && status.qdrant_collections.length > 0 ?
                            status.qdrant_collections.map(c => `<tr><td>${c}</td><td>-</td><td><span class="badge badge-success">active</span></td></tr>`).join('') :
                            '<tr><td colspan="3" style="text-align:center;color:var(--text-light)">暂无集合</td></tr>'
                        }
                    </tbody>
                </table>
            </div>
        `;
    } catch (e) {
        return renderErrorState('监控数据加载失败: ' + e.message, () => loadPage('monitor'));
    }
}

async function renderLogs() {
    try {
        const [errors, logs] = await Promise.all([
            api.get('/api/monitor/errors?limit=20'),
            api.get('/api/monitor/logs?limit=20'),
        ]);

        return `
            <div class="tabs">
                <div class="tab active" data-log-tab="errors">异常日志</div>
                <div class="tab" data-log-tab="system">系统日志</div>
            </div>
            <div id="errorLogs">
                <div class="card">
                    ${errors && errors.length > 0 ? `
                        <table>
                            <thead>
                                <tr><th>时间</th><th>类型</th><th>模块</th><th>文件</th><th>内容</th></tr>
                            </thead>
                            <tbody>
                                ${errors.map(e => `
                                    <tr>
                                        <td>${e.created_at}</td>
                                        <td><span class="badge badge-danger">${e.error_type}</span></td>
                                        <td>${e.module || '-'}</td>
                                        <td>${e.file_name || '-'}</td>
                                        <td>${e.content}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    ` : '<div class="empty-state"><div class="empty-state-icon">✓</div><div>暂无异常日志</div></div>'}
                </div>
            </div>
            <div id="systemLogs" style="display:none">
                <div class="card">
                    ${logs && logs.length > 0 ? `
                        <table>
                            <thead>
                                <tr><th>时间</th><th>级别</th><th>模块</th><th>消息</th></tr>
                            </thead>
                            <tbody>
                                ${logs.map(l => `
                                    <tr>
                                        <td>${l.created_at}</td>
                                        <td><span class="badge ${l.level === 'ERROR' ? 'badge-danger' : l.level === 'WARNING' ? 'badge-warning' : 'badge-info'}">${l.level}</span></td>
                                        <td>${l.module || '-'}</td>
                                        <td>${l.message}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    ` : '<div class="empty-state"><div class="empty-state-icon">📋</div><div>暂无系统日志</div></div>'}
                </div>
            </div>
        `;
    } catch (e) {
        return renderErrorState('日志加载失败: ' + e.message, () => loadPage('logs'));
    }
}

function renderMCP() {
    return `
        <div class="card">
            <div class="card-header"><div class="card-title">MCP协议服务</div></div>
            <div style="margin-bottom:16px;">
                <label class="form-label">MCP服务地址</label>
                <input type="text" class="form-control" value="http://localhost:8000/api/mcp" readonly>
            </div>
            <div style="margin-bottom:16px;">
                <label class="form-label">API鉴权密钥</label>
                <div class="api-key-display" id="mcpApiKey">加载中...</div>
            </div>
            <div style="margin-bottom:16px;">
                <label class="form-label">支持的MCP工具</label>
                <div id="mcpTools"></div>
            </div>
            <div class="form-group">
                <label class="form-label">MCP接口调用测试</label>
                <div class="code-block" id="mcpTestArea">等待输入...</div>
            </div>
            <div class="grid-2">
                <button class="btn btn-primary" onclick="testMCPHealth()">检测服务状态</button>
                <button class="btn btn-secondary" onclick="testMCPSearch()">测试搜索接口</button>
            </div>
        </div>

        <div class="card">
            <div class="card-header"><div class="card-title">MCP接口文档</div></div>
            <div class="code-block">
POST /api/mcp/search
Headers: Authorization: Bearer {api_key}
Body: {
    "query": "搜索问题",
    "kb_name": "知识库名称",
    "top_k": 5,
    "score_threshold": 0.3
}

POST /api/mcp/knowledge-bases
Headers: Authorization: Bearer {api_key}

GET /api/mcp/health

POST /api/mcp/tools
Headers: Authorization: Bearer {api_key}
Body: {
    "tool_name": "knowledge_search",
    "arguments": { "query": "问题" }
}
            </div>
        </div>
    `;
}

function showCreateKb() {
    showModal('新建知识库', `
        <div class="form-group">
            <label class="form-label">知识库名称</label>
            <input type="text" class="form-control" id="newKbName" placeholder="请输入知识库名称（字母/数字/下划线）">
        </div>
        <div class="form-group">
            <label class="form-label">描述（可选）</label>
            <textarea class="form-control" id="newKbDesc" rows="2" placeholder="知识库描述"></textarea>
        </div>
    `, async () => {
        const name = document.getElementById('newKbName').value.trim();
        const desc = document.getElementById('newKbDesc').value.trim();
        const btn = document.getElementById('modalConfirm');
        if (!name) {
            showToast('请输入知识库名称', 'warning');
            return;
        }
        if (!/^[a-zA-Z0-9_\u4e00-\u9fa5-]+$/.test(name)) {
            showToast('知识库名称只能包含字母/数字/中文/下划线/横杠', 'warning');
            return;
        }
        setBtnLoading(btn, true);
        try {
            await api.post('/api/kb', { name, description: desc });
            localStorage.setItem('kb:lastImport', name);
            showToast('知识库创建成功', 'success');
            closeModal();
            const cur = document.querySelector('.nav-item.active')?.dataset.page;
            if (cur === 'dashboard' || cur === 'knowledge' || cur === 'import' || cur === 'search') {
                loadPage(cur);
            } else {
                loadPage('knowledge');
            }
        } catch (e) {
            showToast(e.message, 'error');
            setBtnLoading(btn, false);
        }
    });
}

async function viewKb(kbName) {
    try {
        const content = document.getElementById('contentArea');
        document.getElementById('pageTitle').textContent = `知识库: ${kbName}`;
        content.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-secondary);">⏳ 加载中...</div>';
        const data = await api.get(`/api/kb/${encodeURIComponent(kbName)}`);
        selectedKbName = kbName;

        const totalChunks = (data.files || []).reduce((s, f) => s + (f.chunk_count || 0), 0);
        const totalVectors = (data.files || []).reduce((s, f) => s + (f.vector_count || 0), 0);

        const rows = (data.files && data.files.length > 0) ? data.files.map(f => `
            <tr>
                <td>${escapeHtml(f.file_name)}</td>
                <td>${(f.file_size / 1024).toFixed(1)}KB</td>
                <td>${f.file_format}</td>
                <td>${f.chunk_count}</td>
                <td>${f.vector_count}</td>
                <td><span class="badge ${f.import_status === 'success' ? 'badge-success' : 'badge-secondary'}">${f.import_status}</span></td>
                <td>${f.uploaded_at}</td>
                <td>
                    <button class="btn btn-sm btn-primary" onclick="viewFileChunks('${kbName.replace(/'/g, "\\'")}', ${f.id})">预览</button>
                    <button class="btn btn-sm btn-danger" onclick="deleteFile('${kbName.replace(/'/g, "\\'")}', ${f.id})">删除</button>
                </td>
            </tr>
        `).join('') : '<tr><td colspan="8" style="text-align:center;color:var(--text-light);padding:40px;">暂无文件，请到「文件导入」添加文档</td></tr>';

        content.innerHTML = `
            <div class="detail-nav">
                <button class="btn btn-sm btn-secondary" onclick="loadPage('knowledge')">← 返回知识库列表</button>
                <h2>知识库详情</h2>
            </div>

            <div class="stats-grid">
                <div class="stat-card info">
                    <div class="stat-value">${escapeHtml(kbName)}</div>
                    <div class="stat-label">知识库名称</div>
                </div>
                <div class="stat-card success">
                    <div class="stat-value">${(data.files || []).length}</div>
                    <div class="stat-label">文件数量</div>
                </div>
                <div class="stat-card warning">
                    <div class="stat-value">${totalChunks}</div>
                    <div class="stat-label">切片总数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${totalVectors.toLocaleString()}</div>
                    <div class="stat-label">向量总数</div>
                </div>
            </div>

            <div class="card" style="margin-top:16px;">
                <div class="card-header">
                    <div class="card-title">基本信息</div>
                </div>
                <div style="padding:16px;">
                    <table style="width:100%;">
                        <tr><td style="width:120px;color:var(--text-secondary);">知识库名称</td><td><strong>${escapeHtml(kbName)}</strong></td></tr>
                        <tr><td style="color:var(--text-secondary);">描述</td><td>${escapeHtml(data.info.description || '无描述')}</td></tr>
                        <tr><td style="color:var(--text-secondary);">创建时间</td><td>${data.info.created_at || '-'}</td></tr>
                        <tr><td style="color:var(--text-secondary);">状态</td><td><span class="badge badge-success">${data.info.status || 'active'}</span></td></tr>
                    </table>
                </div>
            </div>

            <div class="card" style="margin-top:16px;">
                <div class="card-header">
                    <div class="card-title">文件列表 (${(data.files || []).length}个文件)</div>
                    <div style="display:flex;gap:8px;">
                        <button class="btn btn-sm btn-primary" onclick="showImportForKb('${kbName.replace(/'/g, "\\'")}')">📥 导入文件</button>
                        ${(data.files || []).length > 0 ? `<button class="btn btn-sm btn-danger" onclick="deleteKb('${kbName.replace(/'/g, "\\'")}')">🗑 删除知识库</button>` : ''}
                    </div>
                </div>
                <div style="overflow-x:auto;">
                    <table>
                        <thead>
                            <tr><th>文件名</th><th>大小</th><th>格式</th><th>切片数</th><th>向量数</th><th>状态</th><th>上传时间</th><th>操作</th></tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            </div>
        `;
    } catch (e) {
        showToast(e.message, 'error');
        loadPage('knowledge');
    }
}

let _viewFileChunksKbName = null;
let _viewFileChunksFileId = null;

async function viewFileChunks(kbName, fileId) {
    _viewFileChunksKbName = kbName;
    _viewFileChunksFileId = fileId;
    const content = document.getElementById('contentArea');
    document.getElementById('pageTitle').textContent = `文件切片: #${fileId}`;
    content.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-secondary);">⏳ 加载中...</div>';
    try {
        const data = await api.get(`/api/mcp/knowledge-bases/${encodeURIComponent(kbName)}/documents/file_${fileId}`, { 'Authorization': `Bearer ${API_KEY}` });
        let chunks = [];
        if (data && data.chunks && data.chunks.length > 0) {
            chunks = data.chunks;
        } else if (data && data.id) {
            chunks = [data];
        }

        let chunksHtml = '<div class="empty-state">暂无切片数据</div>';
        if (chunks.length > 0) {
            chunksHtml = chunks.map((c, i) => {
                const cid = c.id || c.payload?.chunk_id || '';
                const text = escapeHtml(c.payload?.text || '无文本内容');
                const idx = c.payload?.index ?? i;
                return `
                    <div class="chunk-item" id="chunk_${i}">
                        <div class="chunk-meta">
                            <span>#${idx}</span>
                            <span style="color:var(--text-light);font-size:11px;">${cid.substring(0, 12)}...</span>
                            <span style="margin-left:auto;display:flex;gap:6px;">
                                <button class="btn btn-xs btn-primary" style="font-size:12px;padding:2px 10px;"
                                        onclick="editChunk(${i}, '${cid}')">✏ 编辑</button>
                                <button class="btn btn-xs btn-danger" style="font-size:12px;padding:2px 10px;"
                                        onclick="deleteChunk('${encodeURIComponent(kbName)}', '${cid}', ${i})">🗑 删除</button>
                            </span>
                        </div>
                        <div class="chunk-text" id="chunk_text_${i}">${text}</div>
                    </div>
                `;
            }).join('');
        }

        content.innerHTML = `
            <div class="detail-nav">
                <button class="btn btn-sm btn-secondary" onclick="viewKb('${kbName.replace(/'/g, "\\'")}')">← 返回知识库详情</button>
                <h2>文件切片预览 #${fileId} (${chunks.length}个切片)</h2>
            </div>

            <div class="card">
                <div class="card-header">
                    <div class="card-title">切片列表</div>
                    <div style="color:var(--text-secondary);font-size:13px;">共 ${chunks.length} 个切片</div>
                </div>
                <div style="padding:4px 0;">
                    ${chunksHtml}
                </div>
            </div>
        `;
    } catch (e) {
        showToast(e.message, 'error');
        viewKb(kbName);
    }
}

function editChunk(index, chunkId) {
    const textEl = document.getElementById(`chunk_text_${index}`);
    if (!textEl) return;
    const currentText = textEl.textContent || '';

    const textarea = document.createElement('textarea');
    textarea.className = 'form-control';
    textarea.style.cssText = 'width:100%;min-height:120px;font-size:14px;';
    textarea.value = currentText;

    const btnContainer = document.createElement('div');
    btnContainer.style.cssText = 'margin-top:8px;display:flex;gap:8px;';
    const saveBtn = document.createElement('button');
    saveBtn.className = 'btn btn-sm btn-primary';
    saveBtn.textContent = '💾 保存';
    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'btn btn-sm btn-secondary';
    cancelBtn.textContent = '取消';

    btnContainer.appendChild(saveBtn);
    btnContainer.appendChild(cancelBtn);

    const originalHTML = textEl.innerHTML;
    textEl.innerHTML = '';
    textEl.appendChild(textarea);
    textEl.appendChild(btnContainer);

    cancelBtn.addEventListener('click', () => {
        textEl.innerHTML = originalHTML;
    });

    saveBtn.addEventListener('click', async () => {
        const newText = textarea.value.trim();
        if (!newText) {
            showToast('切片内容不能为空', 'warning');
            return;
        }
        if (newText === currentText.trim()) {
            showToast('内容未修改', 'info');
            textEl.innerHTML = originalHTML;
            return;
        }
        saveBtn.disabled = true;
        saveBtn.textContent = '⏳ 保存中...';
        try {
            await api.put(`/api/kb/${encodeURIComponent(_viewFileChunksKbName)}/chunks/${chunkId}`, { text: newText });
            showToast('切片编辑成功', 'success');
            textEl.textContent = newText;
        } catch (e) {
            showToast(e.message, 'error');
            saveBtn.disabled = false;
            saveBtn.textContent = '💾 保存';
        }
    });
}

async function deleteChunk(kbNameEncoded, chunkId, index) {
    const chunkEl = document.getElementById(`chunk_${index}`);
    showModal('确认删除切片', `确定要删除切片 <strong style="color:var(--danger-color)">${chunkId.substring(0, 16)}...</strong> 吗？<br>此操作不可恢复。`, async () => {
        const btn = document.getElementById('modalConfirm');
        setBtnLoading(btn, true);
        try {
            await api.delete(`/api/kb/${kbNameEncoded}/chunks/${chunkId}`);
            showToast('切片已删除', 'success');
            closeModal();
            if (chunkEl) {
                chunkEl.style.transition = 'opacity 0.3s';
                chunkEl.style.opacity = '0';
                setTimeout(() => chunkEl.remove(), 300);
            }
        } catch (e) {
            showToast(e.message, 'error');
            setBtnLoading(btn, false);
        }
    });
}

async function deleteKb(kbName) {
    showModal('确认删除', `确定要删除知识库 <strong style="color:var(--danger-color)">${escapeHtml(kbName)}</strong> 吗？<br>此操作将删除所有相关文件和向量，<strong style="color:var(--danger-color)">不可恢复</strong>。`, async () => {
        const btn = document.getElementById('modalConfirm');
        setBtnLoading(btn, true);
        try {
            await api.delete(`/api/kb/${encodeURIComponent(kbName)}`);
            showToast('知识库已删除', 'success');
            closeModal();
            if (localStorage.getItem('kb:lastImport') === kbName) localStorage.removeItem('kb:lastImport');
            if (localStorage.getItem('kb:lastSearchKb') === kbName) localStorage.removeItem('kb:lastSearchKb');
            const cur = document.querySelector('.nav-item.active')?.dataset.page;
            loadPage(cur === 'dashboard' ? 'dashboard' : 'knowledge');
        } catch (e) {
            showToast(e.message, 'error');
            setBtnLoading(btn, false);
        }
    });
}

async function deleteFile(kbName, fileId) {
    showModal('确认删除', '确定要删除该文件吗？相关切片和向量将一并被移除。', async () => {
        const btn = document.getElementById('modalConfirm');
        setBtnLoading(btn, true);
        try {
            await api.delete(`/api/kb/${encodeURIComponent(kbName)}/files/${fileId}`);
            showToast('文件已删除', 'success');
            closeModal();
            setTimeout(() => { viewKb(kbName); }, 200);
        } catch (e) {
            showToast(e.message, 'error');
            setBtnLoading(btn, false);
        }
    });
}

async function viewTask(taskId) {
    try {
        const data = await api.get(`/api/import/tasks/${taskId}`);
        const rows = (data.files && data.files.length > 0) ? data.files.map(f => `
            <tr>
                <td>${escapeHtml(f.file_name)}</td>
                <td>${f.file_format}</td>
                <td>${(f.file_size / 1024).toFixed(1)}KB</td>
                <td><span class="badge ${f.status === 'success' ? 'badge-success' : f.status === 'skipped' ? 'badge-warning' : 'badge-danger'}">${f.status}</span></td>
                <td style="color:${f.error_reason ? 'var(--danger-color)' : 'inherit'}">${escapeHtml(f.error_reason || '-')}</td>
                <td>${f.processed_at || '-'}</td>
            </tr>
        `).join('') : '<tr><td colspan="6" style="text-align:center;color:var(--text-light);padding:40px;">暂无文件记录</td></tr>';

        const filesHtml = `
            <table>
                <thead>
                    <tr><th>文件名</th><th>格式</th><th>大小</th><th>状态</th><th>原因</th><th>处理时间</th></tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        `;

        showModal(`任务 #${taskId} 详情`, `
            <div style="margin-bottom:12px;">
                <span>总计: ${data.task.total_files}</span> | 
                <span style="color:var(--success-color)">成功: ${data.task.success_count}</span> | 
                <span style="color:var(--danger-color)">失败: ${data.task.fail_count}</span> | 
                <span style="color:var(--warning-color)">跳过: ${data.task.skip_count}</span>
            </div>
            ${filesHtml}
        `, () => {});
        document.getElementById('modalConfirm').style.display = 'none';
    } catch (e) {
        showToast(e.message, 'error');
    }
}

function showImportForKb(kbName) {
    localStorage.setItem('kb:lastImport', kbName);
    loadPage('import');
}

function bindPageEvents(page) {
    if (page === 'import') {
        bindImportEvents();
    } else if (page === 'search') {
        bindSearchEvents();
    } else if (page === 'logs') {
        bindLogEvents();
    } else if (page === 'mcp') {
        bindMCPEvents();
    }
}

function bindImportEvents() {
    document.querySelectorAll('[data-import-tab]').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('[data-import-tab]').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const tabName = tab.dataset.importTab;
            document.getElementById('importSingle').style.display = tabName === 'single' ? 'block' : 'none';
            document.getElementById('importBatch').style.display = tabName === 'batch' ? 'block' : 'none';
            document.getElementById('importFolder').style.display = tabName === 'folder' ? 'block' : 'none';
            document.getElementById('importZip').style.display = tabName === 'zip' ? 'block' : 'none';
        });
    });

    ['importKb', 'chunkSize', 'chunkOverlap', 'chunkSeparator'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        el.addEventListener('change', () => {
            localStorage.setItem('kb:lastImport', document.getElementById('importKb').value || '');
            localStorage.setItem('kb:chunkSize', document.getElementById('chunkSize').value || '500');
            localStorage.setItem('kb:chunkOverlap', document.getElementById('chunkOverlap').value || '50');
            localStorage.setItem('kb:chunkSeparator', document.getElementById('chunkSeparator').value || '');
        });
    });

    setupUpload('singleDrop', 'singleFile', handleSingleUpload, false, 'singleText');
    setupUpload('batchDrop', 'batchFiles', handleBatchUpload, true, 'batchText');
    setupUpload('folderDrop', 'folderFiles', handleFolderUpload, true, 'folderText');
    setupUpload('zipDrop', 'zipFile', handleZipUpload, false, 'zipText');
}

function formatFileList(files) {
    if (!files || files.length === 0) return null;
    if (files.length === 1) {
        const f = files[0];
        const kb = (f.size / 1024).toFixed(1);
        return `<div style="color:var(--success-color);margin-top:6px;">📎 已选择: <strong>${f.name}</strong> (${kb}KB)</div>`;
    }
    const total = Array.from(files).reduce((s, f) => s + f.size, 0);
    // 检查是否有文件夹路径信息
    const folderSet = new Set();
    Array.from(files).forEach(f => {
        const relPath = f.webkitRelativePath || '';
        if (relPath.includes('/')) {
            folderSet.add(relPath.split('/')[0]);
        }
    });
    const folderInfo = folderSet.size > 0 ? `，来自 ${folderSet.size} 个子文件夹` : '';
    return `<div style="color:var(--success-color);margin-top:6px;">📎 已选择 <strong>${files.length}</strong> 个文件${folderInfo}，共 ${(total / 1024).toFixed(1)}KB</div>`;
}

function setupUpload(dropId, inputId, handler, multiple = false, textId = null) {
    const drop = document.getElementById(dropId);
    const input = document.getElementById(inputId);
    const textEl = textId ? document.getElementById(textId) : null;
    if (!drop) return;

    drop.addEventListener('click', () => input.click());
    input.addEventListener('change', (e) => {
        const files = multiple ? e.target.files : [e.target.files[0]];
        if (textEl) {
            const info = formatFileList(files);
            if (info) {
                const existing = document.getElementById('selectedFileInfo_' + dropId);
                if (existing) existing.remove();
                const div = document.createElement('div');
                div.id = 'selectedFileInfo_' + dropId;
                div.innerHTML = info;
                textEl.after(div);
            }
        }
        handler(files);
    });

    drop.addEventListener('dragover', (e) => {
        e.preventDefault();
        drop.classList.add('dragging');
    });
    drop.addEventListener('dragleave', () => drop.classList.remove('dragging'));
    drop.addEventListener('drop', (e) => {
        e.preventDefault();
        drop.classList.remove('dragging');
        const files = multiple ? e.dataTransfer.files : [e.dataTransfer.files[0]];
        if (files.length > 0) {
            input.files = e.dataTransfer.files;
            const info = formatFileList(files);
            if (info && textEl) {
                const existing = document.getElementById('selectedFileInfo_' + dropId);
                if (existing) existing.remove();
                const div = document.createElement('div');
                div.id = 'selectedFileInfo_' + dropId;
                div.innerHTML = info;
                textEl.after(div);
            }
        }
        handler(files);
    });
}

async function handleSingleUpload(files) {
    const kbName = document.getElementById('importKb').value;
    if (!kbName) {
        showToast('请先选择知识库', 'warning');
        return;
    }
    if (!files || !files[0]) return;

    const file = files[0];
    const progressEl = document.getElementById('importProgress');
    const fillEl = document.getElementById('progressFill');
    const resultEl = document.getElementById('importResult');
    progressEl.style.display = 'block';
    fillEl.style.width = '20%';
    fillEl.className = 'progress-bar-fill';
    resultEl.innerHTML = `正在导入 <strong>${file.name}</strong>...`;
    localStorage.setItem('kb:lastImport', kbName);

    const formData = new FormData();
    formData.append('kb_name', kbName);
    formData.append('file', file);
    formData.append('chunk_size', document.getElementById('chunkSize').value);
    formData.append('chunk_overlap', document.getElementById('chunkOverlap').value);
    const sepSingle = document.getElementById('chunkSeparator').value.trim();
    if (sepSingle) formData.append('chunk_separator', sepSingle);

    try {
        const result = await api.upload('/api/import/single', formData);
        fillEl.style.width = '100%';
        fillEl.className = 'progress-bar-fill success';
        resultEl.innerHTML = result.status === 'success'
            ? `✅ 导入完成: ${result.message || file.name} (任务 #${result.task_id || '-'})`
            : `⚠️ 部分失败: ${result.message || ''} (任务 #${result.task_id || '-'})`;
        showToast(`文件导入完成: ${result.status}`, result.status === 'success' ? 'success' : 'warning');
        setTimeout(() => loadPage('import'), 2000);
    } catch (e) {
        fillEl.style.width = '100%';
        fillEl.className = 'progress-bar-fill danger';
        resultEl.innerHTML = '❌ 导入失败: ' + e.message;
        showToast(e.message, 'error');
    }
}

async function handleBatchUpload(files) {
    const kbName = document.getElementById('importKb').value;
    if (!kbName) {
        showToast('请先选择知识库', 'warning');
        return;
    }
    if (!files || files.length === 0) return;

    const formData = new FormData();
    formData.append('kb_name', kbName);
    formData.append('chunk_size', document.getElementById('chunkSize').value);
    formData.append('chunk_overlap', document.getElementById('chunkOverlap').value);
    for (const file of files) {
        formData.append('files', file);
    }
    const sepBatch = document.getElementById('chunkSeparator').value.trim();
    if (sepBatch) formData.append('chunk_separator', sepBatch);
    localStorage.setItem('kb:lastImport', kbName);

    try {
        const progressEl = document.getElementById('importProgress');
        const fillEl = document.getElementById('progressFill');
        const resultEl = document.getElementById('importResult');
        progressEl.style.display = 'block';
        fillEl.style.width = '30%';
        fillEl.className = 'progress-bar-fill';
        resultEl.innerHTML = `正在上传和处理 ${files.length} 个文件...`;

        const result = await api.upload('/api/import/batch', formData);
        fillEl.style.width = '100%';
        fillEl.className = result.failed > 0 ? 'progress-bar-fill' : 'progress-bar-fill success';
        const taskLink = result.task_id
            ? `<div style="margin-top:8px;"><button class="btn btn-sm btn-primary" onclick="viewTask(${result.task_id})">查看任务详情 #${result.task_id}</button></div>`
            : '';
        resultEl.innerHTML = `
            <div>
                <div>✅ 成功: ${result.success}</div>
                <div>⚠️ 跳过: ${result.skipped}</div>
                <div>❌ 失败: ${result.failed}</div>
                ${taskLink}
            </div>
        `;
        showToast(`批量导入完成: 成功${result.success}, 失败${result.failed}`, result.failed > 0 ? 'warning' : 'success');
        setTimeout(() => loadPage('import'), 5000);
    } catch (e) {
        const progressEl = document.getElementById('importProgress');
        const fillEl = document.getElementById('progressFill');
        const resultEl = document.getElementById('importResult');
        fillEl.style.width = '100%';
        fillEl.className = 'progress-bar-fill danger';
        resultEl.innerHTML = '❌ 导入失败: ' + e.message;
        showToast(e.message, 'error');
    }
}

async function handleFolderUpload(files) {
    const kbName = document.getElementById('importKb').value;
    if (!kbName) {
        showToast('请先选择知识库', 'warning');
        return;
    }
    if (!files || files.length === 0) return;

    // 支持的文件扩展名
    const supportedExts = ['pdf', 'doc', 'docx', 'txt', 'md', 'ofd', 'png', 'jpg', 'jpeg', 'bmp', 'tiff', 'tif', 'gif'];

    // 过滤出支持的文件 (webkitdirectory 会返回所有文件包括子目录中的)
    const importableFiles = Array.from(files).filter(f => {
        const ext = f.name.split('.').pop().toLowerCase();
        return supportedExts.includes(ext);
    });

    // 统计子文件夹信息
    const folderSet = new Set();
    Array.from(files).forEach(f => {
        // webkitRelativePath 包含文件夹路径
        const relPath = f.webkitRelativePath || f.name;
        const parts = relPath.split('/');
        if (parts.length > 1) {
            folderSet.add(parts[0]);
        }
    });

    if (importableFiles.length === 0) {
        showToast('文件夹中没有可导入的文件', 'warning');
        return;
    }

    const progressEl = document.getElementById('importProgress');
    const fillEl = document.getElementById('progressFill');
    const resultEl = document.getElementById('importResult');
    progressEl.style.display = 'block';
    fillEl.style.width = '10%';
    fillEl.className = 'progress-bar-fill';

    const folderInfo = folderSet.size > 0 ? ` (来自 ${folderSet.size} 个子文件夹)` : '';
    resultEl.innerHTML = `正在导入 <strong>${importableFiles.length}</strong> 个文件${folderInfo}...`;
    localStorage.setItem('kb:lastImport', kbName);

    const formData = new FormData();
    formData.append('kb_name', kbName);
    formData.append('chunk_size', document.getElementById('chunkSize').value);
    formData.append('chunk_overlap', document.getElementById('chunkOverlap').value);
    const sepFolder = document.getElementById('chunkSeparator').value.trim();
    if (sepFolder) formData.append('chunk_separator', sepFolder);

    for (const file of importableFiles) {
        formData.append('files', file);
    }

    fillEl.style.width = '30%';

    try {
        const result = await api.upload('/api/import/batch', formData);
        fillEl.style.width = '100%';
        fillEl.className = result.failed > 0 ? 'progress-bar-fill' : 'progress-bar-fill success';
        const taskLink = result.task_id
            ? `<div style="margin-top:8px;"><button class="btn btn-sm btn-primary" onclick="viewTask(${result.task_id})">查看任务详情 #${result.task_id}</button></div>`
            : '';
        resultEl.innerHTML = `
            <div>
                ✅ 文件夹导入完成: 共 ${importableFiles.length} 个文件, 成功 ${result.success}, 跳过 ${result.skipped || 0}, 失败 ${result.failed || 0}
                ${taskLink}
            </div>
        `;
        showToast(`文件夹导入完成: 成功${result.success}`, result.failed > 0 ? 'warning' : 'success');
        setTimeout(() => loadPage('import'), 5000);
    } catch (e) {
        fillEl.style.width = '100%';
        fillEl.className = 'progress-bar-fill danger';
        resultEl.innerHTML = '❌ 导入失败: ' + e.message;
        showToast(e.message, 'error');
    }
}

async function handleZipUpload(files) {
    const kbName = document.getElementById('importKb').value;
    if (!kbName) {
        showToast('请先选择知识库', 'warning');
        return;
    }
    if (!files || !files[0]) return;

    const file = files[0];
    const progressEl = document.getElementById('importProgress');
    const fillEl = document.getElementById('progressFill');
    const resultEl = document.getElementById('importResult');
    progressEl.style.display = 'block';
    fillEl.style.width = '20%';
    fillEl.className = 'progress-bar-fill';
    resultEl.innerHTML = `正在解压并导入 <strong>${file.name}</strong>...`;
    localStorage.setItem('kb:lastImport', kbName);

    const formData = new FormData();
    formData.append('kb_name', kbName);
    formData.append('file', file);
    formData.append('chunk_size', document.getElementById('chunkSize').value);
    formData.append('chunk_overlap', document.getElementById('chunkOverlap').value);
    const sepZip = document.getElementById('chunkSeparator').value.trim();
    if (sepZip) formData.append('chunk_separator', sepZip);

    try {
        const result = await api.upload('/api/import/archive', formData);
        fillEl.style.width = '100%';
        fillEl.className = 'progress-bar-fill success';
        const taskLink = result.task_id
            ? `<div style="margin-top:8px;"><button class="btn btn-sm btn-primary" onclick="viewTask(${result.task_id})">查看任务详情 #${result.task_id}</button></div>`
            : '';
        resultEl.innerHTML = `
            <div>
                ✅ 压缩包导入完成: 成功 ${result.success}, 跳过 ${result.skipped || 0}, 失败 ${result.failed || 0}
                ${taskLink}
            </div>
        `;
        showToast(`导入完成: 成功${result.success}`, result.failed > 0 ? 'warning' : 'success');
        setTimeout(() => loadPage('import'), 4000);
    } catch (e) {
        fillEl.style.width = '100%';
        fillEl.className = 'progress-bar-fill danger';
        resultEl.innerHTML = '❌ 导入失败: ' + e.message;
        showToast(e.message, 'error');
    }
}

function bindSearchEvents() {
    const sel = document.getElementById('searchKb');
    const savedKb = sel ? sel.dataset.saved : '';
    api.get('/api/kb').then(kbs => {
        if (sel && kbs) {
            kbs.forEach(kb => {
                const opt = document.createElement('option');
                opt.value = kb.name;
                opt.textContent = kb.name;
                if (kb.name === savedKb) opt.selected = true;
                sel.appendChild(opt);
            });
        }
    }).catch(() => {});

    const queryEl = document.getElementById('searchQuery');
    if (queryEl) {
        queryEl.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                doSearch();
            }
        });
    }
    ['searchKb', 'searchTopK', 'searchThreshold'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('change', () => {
                localStorage.setItem('kb:lastSearchKb', document.getElementById('searchKb').value || '');
                localStorage.setItem('kb:lastTopK', document.getElementById('searchTopK').value || '5');
                localStorage.setItem('kb:lastThreshold', document.getElementById('searchThreshold').value || '0.0');
            });
        }
    });

    const rerankerEl = document.getElementById('useReranker');
    if (rerankerEl) {
        rerankerEl.addEventListener('change', () => {
            localStorage.setItem('kb:lastUseReranker', String(rerankerEl.checked));
            toggleRecallTopK();
        });
    }

    const recallEl = document.getElementById('recallTopK');
    if (recallEl) {
        recallEl.addEventListener('change', () => {
            localStorage.setItem('kb:lastRecallTopK', recallEl.value || '10');
        });
    }
}

function toggleRecallTopK() {
    const checkbox = document.getElementById('useReranker');
    const group = document.getElementById('recallTopKGroup');
    if (!checkbox || !group) return;
    group.style.display = checkbox.checked ? 'flex' : 'none';
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

async function copyText(text, btn) {
    try {
        await navigator.clipboard.writeText(text || '');
        const orig = btn.innerHTML;
        btn.innerHTML = '✓ 已复制';
        setTimeout(() => { btn.innerHTML = orig; }, 1500);
    } catch (e) {
        showToast('复制失败，请手动选择', 'warning');
    }
}

let searchSeq = 0;

async function doSearch() {
    const query = document.getElementById('searchQuery').value.trim();
    if (!query) {
        showToast('请输入搜索问题', 'warning');
        return;
    }
    const kbName = document.getElementById('searchKb').value || null;
    const topK = parseInt(document.getElementById('searchTopK').value) || 5;
    const threshold = parseFloat(document.getElementById('searchThreshold').value) || 0.0;
    const useReranker = document.getElementById('useReranker')?.checked ?? true;
    const recallTopKInput = document.getElementById('recallTopK');
    const recallTopK = useReranker && recallTopKInput ? parseInt(recallTopKInput.value) || 10 : 10;
    const btn = document.getElementById('searchBtn');
    setBtnLoading(btn, true);

    localStorage.setItem('kb:lastSearchKb', kbName || '');
    localStorage.setItem('kb:lastTopK', String(topK));
    localStorage.setItem('kb:lastThreshold', String(threshold));
    localStorage.setItem('kb:lastUseReranker', String(useReranker));
    localStorage.setItem('kb:lastRecallTopK', String(recallTopK));

    const mySeq = ++searchSeq;
    const container = document.getElementById('searchResults');
    const prevHtml = container.innerHTML;
    container.innerHTML = '<div style="padding:20px;color:var(--text-secondary);">🔍 检索中...</div>';

    try {
        const results = await api.post('/api/mcp/search', {
            query,
            kb_name: kbName,
            top_k: topK,
            score_threshold: threshold,
            use_reranker: useReranker,
            reranker_recall_top_k: useReranker ? recallTopK : null,
        }, true, { 'Authorization': `Bearer ${API_KEY}` });

        if (mySeq !== searchSeq) return;

        const info = results.retrieval_info || {};
        const INFO_COLLAPSE_LIMIT = 200;
        const hasReranker = info.use_reranker && info.reranker_model;

        const flowSteps = [];
        flowSteps.push(`
            <div class="flow-step">
                <div class="flow-icon">1</div>
                <div class="flow-content">
                    <div class="flow-label">查询向量化</div>
                    <div class="flow-detail">
                        模型: <strong>${info.model_name}</strong><br>
                        维度: <strong>${info.vector_dim}</strong> 维<br>
                        ${info.demo_mode ? '<span style="color:var(--warning-color)">演示模式 - 使用Mock向量</span>' : `向量预览: [${(info.query_vector_preview || []).join(', ')}${info.query_vector_full_dim > 8 ? ', ...' : ''}]`}
                    </div>
                </div>
            </div>
        `);

        flowSteps.push(`
            <div class="flow-step">
                <div class="flow-icon">2</div>
                <div class="flow-content">
                    <div class="flow-label">向量召回</div>
                    <div class="flow-detail">
                        数据库: <strong>${info.vector_db}</strong><br>
                        距离度量: <strong>${info.distance_metric}</strong><br>
                        检索集合: <strong>${(info.collections_searched || []).join(', ') || '无'}</strong> (${info.collections_count}个)<br>
                        召回数: ${info.recall_top_k || info.top_k} | 阈值: ${info.score_threshold}
                    </div>
                </div>
            </div>
        `);

        if (hasReranker) {
            flowSteps.push(`
                <div class="flow-step">
                    <div class="flow-icon" style="background-color:var(--warning-color);">3</div>
                    <div class="flow-content">
                        <div class="flow-label">Reranker 精排</div>
                        <div class="flow-detail">
                            模型: <strong>${info.reranker_model}</strong><br>
                            模式: ${info.reranker_demo_mode ? '<span style="color:var(--warning-color)">演示模式</span>' : 'CrossEncoder 精排'}<br>
                            输入: ${info.recall_top_k || 10} 条 → 输出: <strong>${info.top_k}</strong> 条
                        </div>
                    </div>
                </div>
            `);
        }

        flowSteps.push(`
            <div class="flow-step">
                <div class="flow-icon" style="background-color:var(--success-color);">${hasReranker ? '4' : '3'}</div>
                <div class="flow-content">
                    <div class="flow-label">结果返回</div>
                    <div class="flow-detail">
                        返回数量: <strong>${results.total}</strong> 条<br>
                        最高相似度: <strong>${(info.max_score * 100).toFixed(1)}%</strong><br>
                        平均相似度: <strong>${(info.avg_score * 100).toFixed(1)}%</strong>
                    </div>
                </div>
            </div>
        `);

        const arrows = Array(flowSteps.length - 1).fill('<div class="flow-arrow">→</div>');

        const infoHtml = info.model_name ? `
            <div class="card" style="margin-bottom:12px;border-left:3px solid ${hasReranker ? 'var(--warning-color)' : 'var(--info-color)'};">
                <div class="card-header">
                    <div class="card-title">
                        检索过程
                        ${hasReranker ? '<span class="badge badge-warning" style="margin-left:8px;">Reranker 精排</span>' : ''}
                    </div>
                    <span class="badge ${info.demo_mode ? 'badge-warning' : 'badge-success'}">${info.method}</span>
                </div>
                <div style="padding:16px;">
                    <div class="retrieval-flow">
                        ${flowSteps.map((s, i) => s + (i < flowSteps.length - 1 ? arrows[i] : '')).join('')}
                    </div>
                    <div class="retrieval-stats">
                        <span class="stat-tag">向量化: ${info.embed_time_ms}ms</span>
                        <span class="stat-tag">向量检索: ${info.search_time_ms}ms</span>
                        ${info.rerank_time_ms ? `<span class="stat-tag" style="background:#fff3e0;color:#e65100;">Reranker: ${info.rerank_time_ms}ms</span>` : ''}
                        <span class="stat-tag">总计: ${info.total_time_ms}ms</span>
                    </div>
                </div>
            </div>
        ` : '';

        if (!results.results || results.results.length === 0) {
            container.innerHTML = infoHtml + '<div class="empty-state"><div class="empty-state-icon">🔍</div><div>未找到相关内容</div></div>';
            return;
        }

        const resultsHtml = results.results.map((r, i) => {
            const text = escapeHtml(r.text || '无文本');
            const needCollapse = text.length > INFO_COLLAPSE_LIMIT;
            const shortText = needCollapse ? text.slice(0, INFO_COLLAPSE_LIMIT) + '...' : text;
            const id = 'sr_' + i + '_' + Date.now();
            return `
                <div class="chunk-item">
                    <div class="chunk-meta">
                        <span>#${i + 1}</span>
                        <span>来源: ${escapeHtml(r.metadata?.file_name || '-')}</span>
                        <span>知识库: ${escapeHtml(r.metadata?.kb_name || r.metadata?.collection || '-')}</span>
                        <span class="chunk-score">相似度: ${(r.score * 100).toFixed(1)}%</span>
                        <button class="btn btn-xs" style="margin-left:auto;padding:2px 8px;font-size:12px;"
                                onclick="copyText(decodeURIComponent(\`${encodeURIComponent(r.text || '')}\`), this)">📋 复制</button>
                    </div>
                    <div class="chunk-text" id="${id}_text">
                        ${needCollapse ? shortText : text}
                    </div>
                    ${needCollapse ? `<div style="margin-top:4px;">
                        <button class="btn btn-xs btn-secondary" style="font-size:12px;" onclick="(function(){
                            const el = document.getElementById('${id}_text');
                            const btn = event.currentTarget;
                            if (btn.textContent.includes('展开')) { el.innerHTML = \`${text.replace(/`/g, '\\`')}\`; btn.textContent = '收起'; }
                            else { el.innerHTML = \`${shortText.replace(/`/g, '\\`')}\`; btn.textContent = '展开全部'; }
                        })()">展开全部</button>
                    </div>` : ''}
                </div>
            `;
        }).join('');

        container.innerHTML = infoHtml + `<div class="card"><div class="card-header"><div class="card-title">搜索结果 (${results.total}条)</div></div>${resultsHtml}</div>`;
    } catch (e) {
        if (mySeq === searchSeq) {
            container.innerHTML = prevHtml + renderErrorState('检索失败: ' + e.message, () => doSearch());
        }
        showToast(e.message, 'error');
    } finally {
        setBtnLoading(btn, false);
    }
}

function bindLogEvents() {
    document.querySelectorAll('[data-log-tab]').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('[data-log-tab]').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const tabName = tab.dataset.logTab;
            document.getElementById('errorLogs').style.display = tabName === 'errors' ? 'block' : 'none';
            document.getElementById('systemLogs').style.display = tabName === 'system' ? 'block' : 'none';
        });
    });
}

function bindMCPEvents() {
    document.getElementById('mcpApiKey').textContent = API_KEY;
    api.get('/api/mcp/tools', { 'Authorization': `Bearer ${API_KEY}` }).then(data => {
        const tools = data || [];
        document.getElementById('mcpTools').innerHTML = `
            <div class="grid-2">
                ${tools.map(t => `
                    <div class="chunk-item" style="border-left-color:var(--info-color)">
                        <div class="chunk-meta"><strong>${t.name}</strong></div>
                        <div style="font-size:13px;color:var(--text-secondary);">${t.description}</div>
                    </div>
                `).join('')}
            </div>
        `;
    }).catch(() => {
        document.getElementById('mcpTools').innerHTML = '<div class="empty-state">无法加载工具列表</div>';
    });
}

async function testMCPHealth() {
    try {
        const data = await api.get('/api/mcp/health');
        document.getElementById('mcpTestArea').textContent = JSON.stringify(data, null, 2);
        showToast('服务正常', 'success');
    } catch (e) {
        document.getElementById('mcpTestArea').textContent = '请求失败: ' + e.message;
        showToast(e.message, 'error');
    }
}

async function testMCPSearch() {
    const query = prompt('请输入测试搜索问题:');
    if (!query) return;
    try {
        const data = await api.post('/api/mcp/search', {
            query,
            top_k: 3,
            score_threshold: 0.0,
        }, true, { 'Authorization': `Bearer ${API_KEY}` });
        document.getElementById('mcpTestArea').textContent = JSON.stringify(data, null, 2);
        showToast('搜索完成', 'success');
    } catch (e) {
        document.getElementById('mcpTestArea').textContent = '请求失败: ' + e.message;
        showToast(e.message, 'error');
    }
}

document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        setPage(item.dataset.page);
    });
});

document.getElementById('refreshBtn').addEventListener('click', async () => {
    const btn = document.getElementById('refreshBtn');
    btn.style.opacity = '0.5';
    btn.style.pointerEvents = 'none';
    try {
        await loadPage(currentPage);
        showToast('已刷新', 'info');
    } finally {
        btn.style.opacity = '';
        btn.style.pointerEvents = '';
    }
});

document.getElementById('modalOverlay').addEventListener('click', (e) => {
    if (e.target.id === 'modalOverlay') closeModal();
});

setPage('dashboard');
checkConnection();
setInterval(checkConnection, 30000);