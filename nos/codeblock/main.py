"""NOS Visual CodeBlock Editor Server."""

import os
import sys
import json
import socket
import webbrowser
import http.server
from pathlib import Path
from nos.compiler.pipeline import CompilerPipeline as Pipeline

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NOS Visual CodeBlock Editor</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;600;800&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #081220;
            --bg-card: #0f2038;
            --bg-input: #172a45;
            --accent-cyan: #00f0ff;
            --accent-blue: #007acc;
            --accent-green: #39e58e;
            --accent-red: #ff3e3e;
            --text-main: #f1f5f9;
            --text-muted: #94a3b8;
            --border-glow: rgba(0, 240, 255, 0.15);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-dark);
            color: var(--text-main);
            height: 100vh;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }

        header {
            background-color: var(--bg-card);
            border-bottom: 1px solid var(--border-glow);
            padding: 10px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
            z-index: 10;
        }

        .logo-container {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .logo-text {
            font-family: 'Outfit', sans-serif;
            font-size: 24px;
            font-weight: 800;
            background: linear-gradient(135deg, #00f0ff, #007acc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: 1px;
        }

        .editor-title {
            font-size: 14px;
            background: rgba(0, 240, 255, 0.1);
            color: var(--accent-cyan);
            padding: 4px 12px;
            border-radius: 20px;
            border: 1px solid rgba(0, 240, 255, 0.2);
            font-weight: 500;
        }

        .header-actions {
            display: flex;
            gap: 12px;
        }

        button {
            padding: 8px 16px;
            border-radius: 6px;
            border: none;
            cursor: pointer;
            font-weight: 600;
            font-size: 13px;
            transition: all 0.3s ease;
            font-family: 'Inter', sans-serif;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .btn-primary {
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue));
            color: #040d21;
        }

        .btn-primary:hover {
            box-shadow: 0 0 15px var(--accent-cyan);
            transform: translateY(-1px);
        }

        .btn-secondary {
            background: var(--bg-input);
            color: var(--text-main);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .btn-secondary:hover {
            background: #233c5e;
            border-color: var(--accent-cyan);
        }

        .main-container {
            display: flex;
            flex: 1;
            overflow: hidden;
        }

        /* Sidebar */
        .sidebar {
            width: 320px;
            background-color: var(--bg-card);
            border-right: 1px solid var(--border-glow);
            display: flex;
            flex-direction: column;
            overflow-y: auto;
        }

        .category-select-container {
            padding: 16px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        .category-select-label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-muted);
            margin-bottom: 8px;
            font-weight: 700;
        }

        select {
            width: 100%;
            padding: 10px;
            background-color: var(--bg-input);
            color: var(--text-main);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 6px;
            font-size: 14px;
            font-family: 'Inter', sans-serif;
            cursor: pointer;
            outline: none;
            transition: border-color 0.3s;
        }

        select:focus {
            border-color: var(--accent-cyan);
        }

        .block-list {
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .draggable-block {
            background-color: var(--bg-input);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            padding: 12px;
            cursor: pointer;
            transition: all 0.2s ease;
            user-select: none;
        }

        .draggable-block:hover {
            border-color: var(--accent-cyan);
            box-shadow: 0 0 10px rgba(0, 240, 255, 0.1);
            transform: scale(1.02);
        }

        .block-name {
            font-weight: 600;
            font-size: 13px;
            color: var(--accent-cyan);
            margin-bottom: 4px;
        }

        .block-desc {
            font-size: 11px;
            color: var(--text-muted);
        }

        /* Workspace */
        .workspace {
            flex: 1;
            background-color: var(--bg-dark);
            padding: 24px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .workspace-empty-state {
            margin: auto;
            text-align: center;
            color: var(--text-muted);
            max-width: 300px;
        }

        .workspace-empty-state svg {
            width: 64px;
            height: 64px;
            margin-bottom: 16px;
            color: var(--accent-cyan);
            opacity: 0.3;
        }

        /* Active Blocks */
        .active-block {
            background-color: var(--bg-card);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
            transition: border-color 0.3s;
        }

        .active-block:hover {
            border-color: rgba(0, 240, 255, 0.3);
        }

        .active-block-header {
            padding: 10px 16px;
            background-color: rgba(255, 255, 255, 0.02);
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .active-block-title {
            font-weight: 700;
            font-size: 13px;
            color: var(--accent-cyan);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .active-block-controls {
            display: flex;
            gap: 8px;
        }

        .control-btn {
            background: none;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
            padding: 4px;
            border-radius: 4px;
            transition: all 0.2s;
        }

        .control-btn:hover {
            color: var(--text-main);
            background: rgba(255, 255, 255, 0.05);
        }

        .control-btn.delete:hover {
            color: var(--accent-red);
            background: rgba(255, 62, 62, 0.1);
        }

        .active-block-body {
            padding: 16px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
        }

        .input-group {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .input-group.full-width {
            grid-column: 1 / -1;
        }

        label {
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
        }

        input[type="text"], textarea {
            width: 100%;
            padding: 8px 12px;
            background-color: var(--bg-input);
            color: var(--text-main);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 6px;
            font-size: 13px;
            font-family: 'Inter', sans-serif;
            outline: none;
            transition: all 0.3s;
        }

        input[type="text"]:focus, textarea:focus {
            border-color: var(--accent-cyan);
            box-shadow: 0 0 8px rgba(0, 240, 255, 0.1);
        }

        textarea {
            resize: vertical;
            min-height: 100px;
            font-family: 'Fira Code', monospace;
            font-size: 12px;
            line-height: 1.5;
        }

        /* Preview Panel */
        .preview-panel {
            width: 450px;
            background-color: #040d1a;
            border-left: 1px solid var(--border-glow);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .preview-header {
            padding: 12px 16px;
            background-color: var(--bg-card);
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .preview-title {
            font-size: 13px;
            font-weight: 700;
            color: var(--text-muted);
        }

        .preview-body {
            flex: 1;
            padding: 16px;
            overflow-y: auto;
            position: relative;
        }

        pre {
            font-family: 'Fira Code', monospace;
            font-size: 12px;
            line-height: 1.6;
            color: var(--accent-cyan);
            white-space: pre-wrap;
        }

        .export-config-panel {
            padding: 16px;
            background-color: var(--bg-card);
            border-top: 1px solid rgba(255, 255, 255, 0.05);
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        /* Status Toast */
        .toast {
            position: fixed;
            bottom: 24px;
            right: 24px;
            padding: 12px 24px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 13px;
            z-index: 100;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.5);
            transform: translateY(100px);
            opacity: 0;
            transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }

        .toast.show {
            transform: translateY(0);
            opacity: 1;
        }

        .toast.success {
            background-color: var(--accent-green);
            color: #081220;
        }

        .toast.error {
            background-color: var(--accent-red);
            color: #ffffff;
        }
    </style>
</head>
<body>

    <!-- Header -->
    <header>
        <div class="logo-container">
            <span class="logo-text">NOS CODEBLOCK</span>
            <span class="editor-title">Prototype Editor</span>
        </div>
        <div class="header-actions">
            <button class="btn-secondary" onclick="exportNOSFile()">💾 Save .nos</button>
            <button class="btn-primary" onclick="compilePackage()">⚡ Compile & Build</button>
        </div>
    </header>

    <!-- Main Container -->
    <div class="main-container">
        
        <!-- Sidebar -->
        <div class="sidebar">
            <div class="category-select-container">
                <div class="category-select-label">Block Category</div>
                <select id="category-selector" onchange="loadCategoryBlocks()">
                    <option value="general">📦 General & Nodes</option>
                    <option value="communications">📡 Communications</option>
                    <option value="callbacks">⚙️ Callbacks & Behavior</option>
                </select>
            </div>
            <div class="block-list" id="block-toolbox">
                <!-- Toolbox blocks dynamically loaded here -->
            </div>
        </div>

        <!-- Workspace -->
        <div class="workspace" id="workspace-canvas">
            <div class="workspace-empty-state" id="empty-state">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                    <line x1="9" y1="3" x2="9" y2="21"></line>
                </svg>
                <p>Click on toolbox blocks in the sidebar to add them to your package workspace.</p>
            </div>
        </div>

        <!-- Code Preview -->
        <div class="preview-panel">
            <div class="preview-header">
                <span class="preview-title">Generated DSL Code (.nos)</span>
                <button class="btn-secondary" style="padding: 4px 8px; font-size: 11px;" onclick="copyCodeToClipboard()">📋 Copy</button>
            </div>
            <div class="preview-body">
                <pre><code id="code-output"></code></pre>
            </div>
            <div class="export-config-panel">
                <div class="input-group">
                    <label>Output Directory</label>
                    <input type="text" id="output-dir-input" value="./src">
                </div>
            </div>
        </div>

    </div>

    <!-- Toast notification -->
    <div class="toast" id="toast-notification"></div>

    <script>
        // List of all toolbox template blocks
        const toolboxBlocks = {
            general: [
                {
                    type: 'package',
                    name: 'Package block',
                    desc: 'Define package name, version, and dependencies.',
                    fields: [
                        { name: 'name', label: 'Package Name', type: 'text', default: 'estimating_example' },
                        { name: 'version', label: 'Version', type: 'text', default: '0.1.0' },
                        { name: 'depends', label: 'Dependencies (comma-separated)', type: 'text', default: 'std_msgs, std_srvs' }
                    ]
                },
                {
                    type: 'node',
                    name: 'Node block',
                    desc: 'Create a new ROS2 node scope.',
                    fields: [
                        { name: 'name', label: 'Node Class Name', type: 'text', default: 'Sensor' }
                    ]
                }
            ],
            communications: [
                {
                    type: 'publisher',
                    name: 'Publisher endpoint',
                    desc: 'Declare a publisher to send messages on a topic.',
                    fields: [
                        { name: 'name', label: 'Publisher Identifier', type: 'text', default: 'reading' },
                        { name: 'msg_type', label: 'Message Type', type: 'text', default: 'std_msgs::Float64' },
                        { name: 'topic', label: 'Topic Name', type: 'text', default: 'reading' },
                        { name: 'qos', label: 'QoS (Optional)', type: 'text', default: '@qos(reliable)' }
                    ]
                },
                {
                    type: 'subscriber',
                    name: 'Subscriber endpoint',
                    desc: 'Subscribe to a topic and execute callback on message.',
                    fields: [
                        { name: 'name', label: 'Subscriber Identifier', type: 'text', default: 'reading_sub' },
                        { name: 'msg_type', label: 'Message Type', type: 'text', default: 'std_msgs::Float64' },
                        { name: 'topic', label: 'Topic Name', type: 'text', default: 'reading' },
                        { name: 'qos', label: 'QoS (Optional)', type: 'text', default: '' }
                    ]
                },
                {
                    type: 'service_server',
                    name: 'Service Server',
                    desc: 'A server responding to service requests.',
                    fields: [
                        { name: 'name', label: 'Service Identifier', type: 'text', default: 'reset' },
                        { name: 'srv_type', label: 'Service Type', type: 'text', default: 'std_srvs::Trigger' },
                        { name: 'service_name', label: 'Service Name', type: 'text', default: 'reset' }
                    ]
                },
                {
                    type: 'service_client',
                    name: 'Service Client',
                    desc: 'An outgoing service request client.',
                    fields: [
                        { name: 'name', label: 'Client Identifier', type: 'text', default: 'add_client' },
                        { name: 'srv_type', label: 'Service Type', type: 'text', default: 'example_interfaces::AddTwoInts' },
                        { name: 'service_name', label: 'Service Name', type: 'text', default: 'add_two_ints' }
                    ]
                },
                {
                    type: 'action_server',
                    name: 'Action Server',
                    desc: 'A server executing long-running action goals.',
                    fields: [
                        { name: 'name', label: 'Action Identifier', type: 'text', default: 'navigate' },
                        { name: 'action_type', label: 'Action Type', type: 'text', default: 'nav2_msgs::NavigateToPose' }
                    ]
                },
                {
                    type: 'action_client',
                    name: 'Action Client',
                    desc: 'An outgoing action goal client.',
                    fields: [
                        { name: 'name', label: 'Client Identifier', type: 'text', default: 'nav_client' },
                        { name: 'action_type', label: 'Action Type', type: 'text', default: 'nav2_msgs::NavigateToPose' }
                    ]
                }
            ],
            callbacks: [
                {
                    type: 'timer',
                    name: 'Periodic Timer',
                    desc: 'Execute code periodically at a given rate.',
                    fields: [
                        { name: 'callback_name', label: 'Timer Callback Name', type: 'text', default: 'timer_callback' },
                        { name: 'period', label: 'Period (seconds)', type: 'text', default: '1.0' }
                    ]
                },
                {
                    type: 'callback',
                    name: 'Lifecycle Event / Custom Code',
                    desc: 'Inject Python code for events, timers, or validations.',
                    fields: [
                        { name: 'event', label: 'Event / Callback Selector (e.g. on_init, timer_callback, on_reading_received)', type: 'text', default: 'on_init' },
                        { name: 'body', label: 'Python Code Block', type: 'textarea', default: 'self.get_logger().info("Init complete")' }
                    ]
                }
            ]
        };

        // Current active blocks in the workspace
        let activeBlocks = [];
        let blockCounter = 0;

        function loadCategoryBlocks() {
            const cat = document.getElementById('category-selector').value;
            const toolbox = document.getElementById('block-toolbox');
            toolbox.innerHTML = '';

            toolboxBlocks[cat].forEach(block => {
                const el = document.createElement('div');
                el.className = 'draggable-block';
                el.innerHTML = `
                    <div class="block-name">${block.name}</div>
                    <div class="block-desc">${block.desc}</div>
                `;
                el.onclick = () => addBlockToWorkspace(block);
                toolbox.appendChild(el);
            });
        }

        function addBlockToWorkspace(template) {
            const blockId = 'block_' + (++blockCounter);
            
            // Deep copy fields
            const fields = template.fields.map(f => ({ ...f, value: f.default }));
            
            const block = {
                id: blockId,
                type: template.type,
                name: template.name,
                fields: fields
            };

            activeBlocks.push(block);
            renderWorkspace();
            generateCode();
        }

        function removeBlock(blockId) {
            activeBlocks = activeBlocks.filter(b => b.id !== blockId);
            renderWorkspace();
            generateCode();
        }

        function moveBlock(index, direction) {
            const targetIndex = index + direction;
            if (targetIndex < 0 || targetIndex >= activeBlocks.length) return;

            const temp = activeBlocks[index];
            activeBlocks[index] = activeBlocks[targetIndex];
            activeBlocks[targetIndex] = temp;

            renderWorkspace();
            generateCode();
        }

        function updateBlockField(blockId, fieldName, val) {
            const block = activeBlocks.find(b => b.id === blockId);
            if (block) {
                const field = block.fields.find(f => f.name === fieldName);
                if (field) {
                    field.value = val;
                }
            }
            generateCode();
        }

        function renderWorkspace() {
            const canvas = document.getElementById('workspace-canvas');
            const emptyState = document.getElementById('empty-state');

            // Remove all active blocks currently rendered (keep empty state if needed)
            const activeElements = canvas.querySelectorAll('.active-block');
            activeElements.forEach(el => el.remove());

            if (activeBlocks.length === 0) {
                emptyState.style.display = 'block';
                return;
            }

            emptyState.style.display = 'none';

            activeBlocks.forEach((block, idx) => {
                const card = document.createElement('div');
                card.className = 'active-block';
                card.id = block.id;

                // Header
                const header = document.createElement('div');
                header.className = 'active-block-header';
                
                const title = document.createElement('div');
                title.className = 'active-block-title';
                title.innerHTML = `<span>📦</span> ${block.name}`;
                
                const controls = document.createElement('div');
                controls.className = 'active-block-controls';
                
                controls.innerHTML = `
                    <button class="control-btn" onclick="moveBlock(${idx}, -1)" ${idx === 0 ? 'disabled' : ''}>▲</button>
                    <button class="control-btn" onclick="moveBlock(${idx}, 1)" ${idx === activeBlocks.length - 1 ? 'disabled' : ''}>▼</button>
                    <button class="control-btn delete" onclick="removeBlock('${block.id}')">🗑️</button>
                `;
                
                header.appendChild(title);
                header.appendChild(controls);
                card.appendChild(header);

                // Body (Input Fields)
                const body = document.createElement('div');
                body.className = 'active-block-body';

                block.fields.forEach(field => {
                    const group = document.createElement('div');
                    group.className = 'input-group';
                    if (field.type === 'textarea') {
                        group.className += ' full-width';
                    }

                    const label = document.createElement('label');
                    label.innerText = field.label;
                    group.appendChild(label);

                    if (field.type === 'text') {
                        const input = document.createElement('input');
                        input.type = 'text';
                        input.value = field.value;
                        input.oninput = (e) => updateBlockField(block.id, field.name, e.target.value);
                        group.appendChild(input);
                    } else if (field.type === 'textarea') {
                        const textarea = document.createElement('textarea');
                        textarea.value = field.value;
                        textarea.oninput = (e) => updateBlockField(block.id, field.name, e.target.value);
                        group.appendChild(textarea);
                    }

                    body.appendChild(group);
                });

                card.appendChild(body);
                canvas.appendChild(card);
            });
        }

        function generateCode() {
            let code = "";
            let pkgBlock = activeBlocks.find(b => b.type === 'package');
            
            // Generate Package
            if (pkgBlock) {
                const name = pkgBlock.fields.find(f => f.name === 'name').value;
                const ver = pkgBlock.fields.find(f => f.name === 'version').value;
                const depsRaw = pkgBlock.fields.find(f => f.name === 'depends').value;
                
                code += `package ${name}\n`;
                code += `version "${ver}"\n`;
                
                if (depsRaw.trim()) {
                    const deps = depsRaw.split(',').map(d => `"${d.trim()}"`).join(', ');
                    code += `depends: [${deps}]\n`;
                }
                code += `\n`;
            }

            // Group workspace items under nodes
            let currentNode = null;
            let publications = [];
            let subscriptions = [];
            let services = [];
            let actions = [];
            let callbacks = [];

            activeBlocks.forEach(block => {
                if (block.type === 'node') {
                    // Output previous node
                    if (currentNode) {
                        code += generateNodeDSL(currentNode, publications, subscriptions, services, actions, callbacks);
                    }
                    currentNode = block.fields.find(f => f.name === 'name').value;
                    publications = [];
                    subscriptions = [];
                    services = [];
                    actions = [];
                    callbacks = [];
                } else if (block.type === 'publisher') {
                    publications.push(block);
                } else if (block.type === 'subscriber') {
                    subscriptions.push(block);
                } else if (block.type === 'service_server' || block.type === 'service_client') {
                    services.push(block);
                } else if (block.type === 'action_server' || block.type === 'action_client') {
                    actions.push(block);
                } else if (block.type === 'timer' || block.type === 'callback') {
                    callbacks.push(block);
                }
            });

            // Output final node
            if (currentNode) {
                code += generateNodeDSL(currentNode, publications, subscriptions, services, actions, callbacks);
            }

            document.getElementById('code-output').innerText = code;
        }

        function generateNodeDSL(nodeName, pubs, subs, svcs, acts, cbs) {
            let out = `node ${nodeName} {\n`;
            
            // Subscriptions
            if (subs.length > 0) {
                out += `    subscriptions {\n`;
                subs.forEach(s => {
                    const name = s.fields.find(f => f.name === 'name').value;
                    const type = s.fields.find(f => f.name === 'msg_type').value;
                    const topic = s.fields.find(f => f.name === 'topic').value;
                    const qos = s.fields.find(f => f.name === 'qos').value;
                    out += `        ${name}: ${type} @topic("${topic}") ${qos}\n`;
                });
                out += `    }\n\n`;
            }

            // Publications
            if (pubs.length > 0) {
                out += `    publications {\n`;
                pubs.forEach(p => {
                    const name = p.fields.find(f => f.name === 'name').value;
                    const type = p.fields.find(f => f.name === 'msg_type').value;
                    const topic = p.fields.find(f => f.name === 'topic').value;
                    const qos = p.fields.find(f => f.name === 'qos').value;
                    out += `        ${name}: ${type} @topic("${topic}") ${qos}\n`;
                });
                out += `    }\n\n`;
            }

            // Services
            if (svcs.length > 0) {
                out += `    services {\n`;
                svcs.forEach(s => {
                    const name = s.fields.find(f => f.name === 'name').value;
                    const type = s.fields.find(f => f.name === 'srv_type').value;
                    const service_name = s.fields.find(f => f.name === 'service_name').value;
                    const isClient = s.type === 'service_client';
                    const clientAttr = isClient ? ' @client' : '';
                    out += `        ${name}: ${type} @service("${service_name}")${clientAttr}\n`;
                });
                out += `    }\n\n`;
            }

            // Actions
            if (acts.length > 0) {
                out += `    actions {\n`;
                acts.forEach(a => {
                    const name = a.fields.find(f => f.name === 'name').value;
                    const type = a.fields.find(f => f.name === 'action_type').value;
                    const isClient = a.type === 'action_client';
                    const clientAttr = isClient ? ' @client' : '';
                    out += `        ${name}: ${type}${clientAttr}\n`;
                });
                out += `    }\n\n`;
            }

            // Callbacks
            cbs.forEach(cb => {
                if (cb.type === 'timer') {
                    const name = cb.fields.find(f => f.name === 'callback_name').value;
                    const period = cb.fields.find(f => f.name === 'period').value;
                    out += `    # Timer running every ${period}s\n`;
                    // Handled as comment in structural block, logic added in code callbacks
                } else if (cb.type === 'callback') {
                    const event = cb.fields.find(f => f.name === 'event').value;
                    const body = cb.fields.find(f => f.name === 'body').value;
                    const lines = body.split('\n').map(l => `        ${l}`).join('\n');
                    
                    if (event === 'on_init' || event === 'on_shutdown') {
                        out += `    ${event} -> {\n${lines}\n    }\n\n`;
                    } else {
                        out += `    on ${event} -> {\n${lines}\n    }\n\n`;
                    }
                }
            });

            out += `}\n\n`;
            return out;
        }

        function copyCodeToClipboard() {
            const code = document.getElementById('code-output').innerText;
            navigator.clipboard.writeText(code).then(() => {
                showToast("Code copied to clipboard!", "success");
            });
        }

        function showToast(message, type) {
            const toast = document.getElementById('toast-notification');
            toast.innerText = message;
            toast.className = `toast show ${type}`;
            setTimeout(() => {
                toast.className = 'toast';
            }, 3000);
        }

        function exportNOSFile() {
            const code = document.getElementById('code-output').innerText;
            if (!code.trim()) {
                showToast("Workspace is empty!", "error");
                return;
            }
            
            let pkgBlock = activeBlocks.find(b => b.type === 'package');
            let filename = "estimating_example.nos";
            if (pkgBlock) {
                const name = pkgBlock.fields.find(f => f.name === 'name').value;
                filename = `${name}.nos`;
            }

            fetch('/api/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code, filename: filename })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showToast(`Successfully saved to ${data.path}`, "success");
                } else {
                    showToast("Save failed: " + data.error, "error");
                }
            })
            .catch(err => showToast("Network error during save", "error"));
        }

        function compilePackage() {
            const code = document.getElementById('code-output').innerText;
            const outputDir = document.getElementById('output-dir-input').value;

            if (!code.trim()) {
                showToast("Workspace is empty!", "error");
                return;
            }

            showToast("Compiling package...", "success");

            fetch('/api/compile', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code, output_dir: outputDir })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showToast(`Successfully compiled and exported to ${outputDir}!`, "success");
                } else {
                    const errStr = data.errors.join('\\n');
                    showToast("Compilation Failed:\\n" + errStr, "error");
                }
            })
            .catch(err => showToast("Network error during compilation", "error"));
        }

        // Initialize toolbox
        loadCategoryBlocks();
    </script>
</body>
</html>
"""

class CodeBlockHandler(http.server.BaseHTTPRequestHandler):
    """HTTP Request Handler for code block visual editor."""

    def log_message(self, format, *args):
        # Silence HTTP logging to clean stdout
        pass

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode("utf-8"))
        else:
            self.send_error(404, "File not found")

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            params = json.loads(post_data.decode("utf-8"))
        except Exception:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"success": false, "error": "Invalid JSON"}')
            return

        if self.path == "/api/save":
            code = params.get("code", "")
            filename = params.get("filename", "estimating_example.nos")
            
            try:
                filepath = Path(os.getcwd()) / filename
                filepath.write_text(code, encoding="utf-8")
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "success": True,
                    "path": str(filepath)
                }
                self.wfile.write(json.dumps(response).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"success": false, "error": str(e)}).encode("utf-8"))

        elif self.path == "/api/compile":
            code = params.get("code", "")
            output_dir = params.get("output_dir", "./src")
            
            try:
                # Compile string directly
                pipeline = Pipeline()
                result = pipeline.compile_string(code)
                
                if result.success:
                    # Write files to target output directory
                    out_path = Path(output_dir)
                    out_path.mkdir(parents=True, exist_ok=True)
                    
                    for filename, content in result.files.items():
                        file_path = out_path / filename
                        # Create package subdirs automatically
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        file_path.write_text(content, encoding="utf-8")

                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"success": true}')
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    response = {
                        "success": False,
                        "errors": result.errors
                    }
                    self.wfile.write(json.dumps(response).encode("utf-8"))

            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"success": false, "errors": [str(e)]}).encode("utf-8"))

def main():
    try:
        from nos.compiler.main import setup_vscode_extension
        setup_vscode_extension()
    except Exception:
        pass

    port = 8080
    
    # Locate a free port if 8080 is taken
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("", port))
    except OSError:
        # Port taken, select an ephemeral one
        s.bind(("", 0))
        port = s.getsockname()[1]
    finally:
        s.close()

    print(f"Starting NOS Visual CodeBlock editor on http://localhost:{port}/")
    
    # Auto-open browser
    webbrowser.open(f"http://localhost:{port}/")
    
    handler = CodeBlockHandler
    server = http.server.HTTPServer(("", port), handler)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\\nShutting down CodeBlock editor server.")
        server.server_close()

if __name__ == '__main__':
    main()
