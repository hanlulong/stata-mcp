(function () {
    let vscodeApi = null;
    let currentVersion = 0;

    try {
        if (typeof acquireVsCodeApi === 'function') {
            vscodeApi = acquireVsCodeApi();
        }
    } catch (error) {
        console.error('[GraphViewer] Failed to acquire VS Code API', error);
    }

    function postMessage(payload) {
        if (vscodeApi) {
            vscodeApi.postMessage(payload);
        }
    }

    function setStoredState(snapshot) {
        if (vscodeApi) {
            vscodeApi.setState({ snapshot });
        }
    }

    function getStoredState() {
        if (!vscodeApi) {
            return null;
        }

        const state = vscodeApi.getState();
        return state && state.snapshot ? state.snapshot : null;
    }

    function createImageErrorNode(graph) {
        const errorNode = document.createElement('div');
        errorNode.className = 'error';
        errorNode.hidden = true;
        errorNode.textContent = graph.errorText || `Failed to load graph: ${graph.name || 'unknown'}`;
        return errorNode;
    }

    function createGraphNode(graph) {
        const container = document.createElement('div');
        container.className = 'graph-container';
        container.dataset.graphName = graph.name || '';
        container.dataset.entryId = graph.entryId || '';

        const title = document.createElement('h3');
        title.textContent = graph.displayName || graph.name || 'Graph';
        container.appendChild(title);

        if (graph.src) {
            const image = document.createElement('img');
            image.className = 'graph-image';
            image.src = graph.src;
            image.alt = graph.alt || graph.name || 'graph';
            image.loading = graph.loading || 'lazy';

            const errorNode = createImageErrorNode(graph);
            image.addEventListener('error', () => {
                image.style.display = 'none';
                errorNode.hidden = false;
                postMessage({
                    command: 'graphImageError',
                    version: currentVersion,
                    name: graph.name || 'unknown',
                    src: image.currentSrc || image.getAttribute('src') || ''
                });
            }, { once: true });

            container.appendChild(image);
            container.appendChild(errorNode);
        } else {
            const errorNode = createImageErrorNode(graph);
            errorNode.hidden = false;
            container.appendChild(errorNode);
        }

        return container;
    }

    function renderEmptyState() {
        const container = document.getElementById('graphs-container');
        if (!container) {
            return;
        }

        const empty = document.createElement('div');
        empty.className = 'no-graphs';
        empty.textContent = 'No graphs to display';
        container.replaceChildren(empty);
    }

    function updateHeader(snapshot) {
        const graphCount = document.getElementById('graph-count');
        if (graphCount) {
            const count = Number.isInteger(snapshot.graphCount) ? snapshot.graphCount : 0;
            graphCount.textContent = `${count} graph(s) displayed`;
        }
    }

    function applySnapshot(snapshot, options) {
        const shouldPersist = !options || options.persist !== false;
        if (!snapshot || typeof snapshot.version !== 'number') {
            return;
        }

        if (snapshot.version < currentVersion) {
            return;
        }

        currentVersion = snapshot.version;
        updateHeader(snapshot);

        const container = document.getElementById('graphs-container');
        if (!container) {
            return;
        }

        const graphs = Array.isArray(snapshot.graphs) ? snapshot.graphs : [];
        if (graphs.length === 0) {
            renderEmptyState();
        } else {
            const nodes = graphs.map(createGraphNode);
            container.replaceChildren(...nodes);
        }

        if (shouldPersist) {
            setStoredState(snapshot);
        }

    }

    function restoreSnapshot() {
        const snapshot = getStoredState();
        if (snapshot) {
            applySnapshot(snapshot, { persist: false });
        } else {
            renderEmptyState();
        }
    }

    function initialize() {
        const clearButton = document.getElementById('clear-graphs-button');
        if (clearButton) {
            clearButton.addEventListener('click', () => {
                postMessage({ command: 'clearGraphs' });
            });
        }

        restoreSnapshot();

        window.addEventListener('message', event => {
            const message = event.data;
            if (!message || message.command !== 'hydrateGraphs') {
                return;
            }
            applySnapshot(message.snapshot || null, { persist: true });
        });

        postMessage({
            command: 'graphViewerReady',
            version: currentVersion
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialize, { once: true });
    } else {
        initialize();
    }

    window.addEventListener('error', event => {
        postMessage({
            command: 'graphViewerClientError',
            version: currentVersion,
            message: event.message || 'Unknown error',
            filename: event.filename || '',
            lineno: event.lineno,
            colno: event.colno
        });
    });

    window.addEventListener('unhandledrejection', event => {
        postMessage({
            command: 'graphViewerClientError',
            version: currentVersion,
            message: event.reason ? String(event.reason) : 'Unhandled promise rejection',
            filename: '',
            lineno: -1,
            colno: -1
        });
    });
})();
