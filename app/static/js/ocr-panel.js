/**
 * OCR 状态面板和导入进度管理
 */

// ============ OCR 状态面板 ============

async function renderOCRPanel() {
    try {
        const [status, modelInfo] = await Promise.all([
            api.get('/api/ocr/status').catch(() => null),
            api.get('/api/ocr/model-info').catch(() => null),
        ]);

        if (!status) {
            return `
                <div class="panel-header">
                    <div>
                        <h2>🔍 OCR 服务状态</h2>
                        <p class="panel-subtitle">文档识别引擎实时状态监控</p>
                    </div>
                    <button class="btn btn-sm btn-secondary" onclick="refreshOCRPanel()">🔄 刷新</button>
                </div>
                <div class="empty-state">
                    <div class="empty-state-icon">⚠️</div>
                    <div>OCR 服务未启动</div>
                    <p style="color:var(--text-secondary);margin-top:8px;">请检查 rapidocr-onnxruntime 是否已安装</p>
                </div>
            `;
        }

        const statusColors = {
            'running': 'var(--success-color)',
            'initializing': 'var(--warning-color)',
            'stopped': 'var(--danger-color)',
        };

        const statusText = {
            'running': '运行中',
            'initializing': '初始化中',
            'stopped': '已停止',
        };

        return `
            <div class="panel-header">
                <div>
                    <h2>🔍 OCR 服务状态</h2>
                    <p class="panel-subtitle">文档识别引擎实时状态监控</p>
                </div>
                <button class="btn btn-sm btn-secondary" onclick="refreshOCRPanel()">🔄 刷新</button>
            </div>

            <div class="ocr-status-grid">
                <!-- 引擎状态 -->
                <div class="ocr-card ${status.engine_ready ? 'ready' : 'not-ready'}">
                    <div class="ocr-card-header">
                        <span class="ocr-card-title">引擎状态</span>
                        <span class="ocr-status-badge" style="background:${statusColors[status.status] || 'var(--secondary-color)'}">
                            ${statusText[status.status] || status.status}
                        </span>
                    </div>
                    <div class="ocr-card-body">
                        <div class="ocr-status-row">
                            <span class="label">就绪状态</span>
                            <span class="value ${status.engine_ready ? 'success' : 'error'}">
                                ${status.engine_ready ? '✓ 已就绪' : '✗ 未就绪'}
                            </span>
                        </div>
                        <div class="ocr-status-row">
                            <span class="label">运行时间</span>
                            <span class="value">${status.uptime_display}</span>
                        </div>
                        <div class="ocr-status-row">
                            <span class="label">模型版本</span>
                            <span class="value">${status.model_info.model_version}</span>
                        </div>
                        <div class="ocr-status-row">
                            <span class="label">推理框架</span>
                            <span class="value">${status.model_info.framework}</span>
                        </div>
                    </div>
                </div>

                <!-- 资源使用 -->
                <div class="ocr-card">
                    <div class="ocr-card-header">
                        <span class="ocr-card-title">资源使用</span>
                    </div>
                    <div class="ocr-card-body">
                        <div class="ocr-status-row">
                            <span class="label">内存占用 (RSS)</span>
                            <span class="value">${status.memory.rss_mb || 'N/A'} MB</span>
                        </div>
                        <div class="ocr-status-row">
                            <span class="label">虚拟内存</span>
                            <span class="value">${status.memory.vms_mb || 'N/A'} MB</span>
                        </div>
                        <div class="ocr-status-row">
                            <span class="label">进程占比</span>
                            <span class="value">${status.memory.percent || 'N/A'}%</span>
                        </div>
                    </div>
                </div>

                <!-- 统计数据 -->
                <div class="ocr-card">
                    <div class="ocr-card-header">
                        <span class="ocr-card-title">统计数据</span>
                    </div>
                    <div class="ocr-card-body">
                        <div class="ocr-stat-grid">
                            <div class="ocr-stat-item">
                                <div class="ocr-stat-value">${status.stats.total_requests}</div>
                                <div class="ocr-stat-label">总请求数</div>
                            </div>
                            <div class="ocr-stat-item">
                                <div class="ocr-stat-value success">${status.stats.successful_requests}</div>
                                <div class="ocr-stat-label">成功</div>
                            </div>
                            <div class="ocr-stat-item">
                                <div class="ocr-stat-value error">${status.stats.failed_requests}</div>
                                <div class="ocr-stat-label">失败</div>
                            </div>
                            <div class="ocr-stat-item">
                                <div class="ocr-stat-value">${status.stats.success_rate}%</div>
                                <div class="ocr-stat-label">成功率</div>
                            </div>
                        </div>
                        <div class="ocr-status-row" style="margin-top:12px;">
                            <span class="label">平均处理时间</span>
                            <span class="value">${status.stats.avg_processing_time_ms} ms</span>
                        </div>
                        <div class="ocr-status-row">
                            <span class="label">处理总页数</span>
                            <span class="value">${status.stats.total_pages_processed}</span>
                        </div>
                    </div>
                </div>

                <!-- 模型文件 -->
                <div class="ocr-card">
                    <div class="ocr-card-header">
                        <span class="ocr-card-title">模型文件</span>
                        <span class="ocr-status-badge ${modelInfo?.model_files_ready ? '' : 'badge-warning'}">
                            ${modelInfo?.model_files_ready ? '✓ 完整' : '⚠ 缺失'}
                        </span>
                    </div>
                    <div class="ocr-card-body">
                        ${modelInfo?.model_files.map(f => `
                            <div class="ocr-model-row">
                                <span class="ocr-model-name">${f.name}</span>
                                <span class="ocr-model-size">${f.size_mb} MB</span>
                            </div>
                        `).join('') || '<div style="color:var(--text-secondary);">暂无模型文件</div>'}
                        <div class="ocr-status-row" style="margin-top:8px;border-top:1px solid var(--border-color);padding-top:8px;">
                            <span class="label">模型总大小</span>
                            <span class="value">${modelInfo?.total_model_size_mb || 'N/A'} MB</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 支持的功能 -->
            <div class="ocr-features-section">
                <h3 style="margin-bottom:12px;">📋 支持的功能</h3>
                <div class="ocr-features-grid">
                    <div class="ocr-feature-item">
                        <span class="feature-icon">🖼️</span>
                        <span class="feature-text">图片识别 (jpg/png/bmp/tiff)</span>
                    </div>
                    <div class="ocr-feature-item">
                        <span class="feature-icon">📄</span>
                        <span class="feature-text">扫描版 PDF 自动检测</span>
                    </div>
                    <div class="ocr-feature-item">
                        <span class="feature-icon">🔤</span>
                        <span class="feature-text">中文文字识别</span>
                    </div>
                    <div class="ocr-feature-item">
                        <span class="feature-icon">⚡</span>
                        <span class="feature-text">实时进度推送</span>
                    </div>
                </div>
            </div>
        `;
    } catch (e) {
        return `<div class="empty-state"><div class="empty-state-icon">❌</div><div>加载 OCR 状态失败: ${e.message}</div></div>`;
    }
}

async function refreshOCRPanel() {
    const panel = document.querySelector('.ocr-status-grid');
    if (panel) {
        panel.style.opacity = '0.5';
        const content = document.getElementById('contentArea');
        const newHtml = await renderOCRPanel();
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = newHtml;
        const newPanel = tempDiv.querySelector('.ocr-status-grid');
        if (newPanel) {
            panel.replaceWith(newPanel);
        }
        panel.style.opacity = '1';
    } else {
        // 整个面板
        const content = document.getElementById('contentArea');
        if (content.innerHTML.includes('OCR 服务状态')) {
            content.innerHTML = await renderOCRPanel();
        }
    }
}


// ============ 导入进度 WebSocket ============

let importProgressWs = null;
let importProgressCallbacks = [];

function connectImportProgressWS() {
    if (importProgressWs && importProgressWs.readyState === WebSocket.OPEN) {
        return importProgressWs;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname || 'localhost';
    importProgressWs = new WebSocket(`${protocol}//${host}:${window.location.port}/ws/import-progress`);

    importProgressWs.onopen = () => {
        console.log('导入进度 WebSocket 已连接');
        importProgressCallbacks.forEach(cb => cb.onOpen && cb.onOpen());
    };

    importProgressWs.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            importProgressCallbacks.forEach(cb => cb.onMessage && cb.onMessage(msg));
        } catch (e) {
            console.error('WebSocket 消息解析失败:', e);
        }
    };

    importProgressWs.onclose = () => {
        console.log('导入进度 WebSocket 已断开，3秒后重连...');
        importProgressCallbacks.forEach(cb => cb.onClose && cb.onClose());
        setTimeout(() => connectImportProgressWS(), 3000);
    };

    importProgressWs.onerror = (error) => {
        console.error('WebSocket 错误:', error);
    };

    return importProgressWs;
}

function onImportProgress(callback) {
    importProgressCallbacks.push(callback);
    return () => {
        importProgressCallbacks = importProgressCallbacks.filter(cb => cb !== callback);
    };
}

function renderImportProgressPanel() {
    // 连接 WebSocket
    connectImportProgressWS();

    const panel = document.createElement('div');
    panel.className = 'import-progress-panel';
    panel.innerHTML = `
        <div class="panel-header">
            <div>
                <h3>📊 导入进度</h3>
                <p class="panel-subtitle">实时显示文件解析进度</p>
            </div>
        </div>
        <div id="importProgressList" class="import-progress-list">
            <div class="empty-state">
                <div class="empty-state-icon">📥</div>
                <div>暂无进行中的导入任务</div>
            </div>
        </div>
    `;

    // 监听进度更新
    onImportProgress({
        onMessage: (msg) => {
            const list = document.getElementById('importProgressList');
            if (!list) return;

            if (msg.type === 'init' || msg.type === 'task_created' || msg.type === 'progress_update' || msg.type === 'task_completed' || msg.type === 'task_failed') {
                renderImportTasks(msg.tasks || (msg.data ? [msg.data] : []));
            }
        }
    });

    return panel.outerHTML;
}

function renderImportTasks(tasks) {
    const list = document.getElementById('importProgressList');
    if (!list) return;

    if (!tasks || tasks.length === 0) {
        list.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📥</div>
                <div>暂无进行中的导入任务</div>
            </div>
        `;
        return;
    }

    const activeTasks = tasks.filter(t => t.status === 'processing');
    const completedTasks = tasks.filter(t => t.status !== 'processing').slice(0, 5);

    let html = '';

    // 活跃任务
    if (activeTasks.length > 0) {
        html += '<div class="import-task-group"><h4>进行中</h4>';
        activeTasks.forEach(task => {
            html += renderTaskItem(task);
        });
        html += '</div>';
    }

    // 最近完成的任务
    if (completedTasks.length > 0) {
        html += '<div class="import-task-group"><h4>最近完成</h4>';
        completedTasks.forEach(task => {
            html += renderTaskItem(task);
        });
        html += '</div>';
    }

    list.innerHTML = html;
}

function renderTaskItem(task) {
    const statusClasses = {
        'processing': 'badge-warning',
        'completed': 'badge-success',
        'failed': 'badge-danger',
    };

    const statusText = {
        'processing': '进行中',
        'completed': '已完成',
        'failed': '失败',
    };

    const progress = task.progress || 0;
    const progressColor = task.status === 'failed' ? 'var(--danger-color)' :
                          task.status === 'completed' ? 'var(--success-color)' : 'var(--warning-color)';

    let filesHtml = '';
    if (task.files && task.files.length > 0) {
        filesHtml = '<div class="task-files">';
        task.files.forEach(file => {
            const fileStatusHtml = file.error ?
                `<span class="file-status error" title="${file.error}">⚠ 解析失败</span>` :
                file.needs_ocr ?
                `<span class="file-status ocr" title="使用 OCR 处理">🔍 OCR中</span>` :
                file.stage === 'complete' ?
                `<span class="file-status success">✓ 完成</span>` :
                `<span class="file-status">⏳ ${file.message || file.stage}</span>`;

            filesHtml += `
                <div class="task-file-item">
                    <span class="file-name" title="${file.file_name}">${escapeHtml(file.file_name)}</span>
                    ${fileStatusHtml}
                </div>
            `;
        });
        filesHtml += '</div>';
    }

    return `
        <div class="import-task-item">
            <div class="task-header">
                <div class="task-info">
                    <span class="task-id">#${task.task_id}</span>
                    <span class="task-kb">📚 ${escapeHtml(task.kb_name)}</span>
                    <span class="badge ${statusClasses[task.status]}">${statusText[task.status]}</span>
                </div>
                <div class="task-progress">
                    <div class="progress-bar">
                        <div class="progress-fill" style="width:${progress}%;background:${progressColor};"></div>
                    </div>
                    <span class="progress-text">${progress}%</span>
                </div>
            </div>
            <div class="task-stats">
                <span>📄 ${task.processed_files || 0}/${task.total_files || 0} 文件</span>
                <span>⏱ ${task.elapsed_seconds || 0}s</span>
            </div>
            ${filesHtml}
        </div>
    `;
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
