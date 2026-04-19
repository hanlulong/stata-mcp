class GraphStore {
    constructor() {
        this.clear();
    }

    clear() {
        this.currentBatch = null;
    }

    hasGraphs() {
        return !!(this.currentBatch && Array.isArray(this.currentBatch.graphs) && this.currentBatch.graphs.length > 0);
    }

    replaceBatch(batch) {
        if (!batch || !Array.isArray(batch.graphs) || batch.graphs.length === 0) {
            this.clear();
            return null;
        }

        const createdAt = batch.createdAt || Date.now();
        const executionId = batch.executionId || `exec-${createdAt}`;
        const batchId = batch.batchId || executionId;
        const source = batch.source || 'execution';

        this.currentBatch = {
            executionId,
            batchId,
            source,
            createdAt,
            graphs: batch.graphs.map((graph, index) => ({
                artifactId: graph.artifactId || `${batchId}-artifact-${index + 1}`,
                logicalName: graph.logicalName || graph.name,
                name: graph.name || graph.logicalName || `graph${index + 1}`,
                displayName: graph.displayName || graph.name || graph.logicalName || `graph${index + 1}`,
                path: graph.path,
                browserPath: graph.browserPath || '',
                format: graph.format || 'png',
                orderInBatch: Number.isInteger(graph.orderInBatch) ? graph.orderInBatch : index
            }))
        };

        return this.currentBatch;
    }

    getSnapshot(mapGraphToViewModel) {
        if (!this.currentBatch) {
            return {
                executionId: null,
                batchId: null,
                graphCount: 0,
                graphs: []
            };
        }

        const orderedGraphs = this.currentBatch.graphs
            .slice()
            .sort((left, right) => left.orderInBatch - right.orderInBatch);

        const visibleGraphs = [];
        if (orderedGraphs.length > 1) {
            const lastGraph = orderedGraphs[orderedGraphs.length - 1];
            visibleGraphs.push({
                ...lastGraph,
                entryId: `${this.currentBatch.batchId}:summary:${lastGraph.artifactId}`,
                displayName: 'Last Graph',
                isSummary: true
            });
        }

        for (const graph of orderedGraphs) {
            visibleGraphs.push({
                ...graph,
                entryId: `${this.currentBatch.batchId}:artifact:${graph.artifactId}`,
                isSummary: false
            });
        }

        return {
            executionId: this.currentBatch.executionId,
            batchId: this.currentBatch.batchId,
            graphCount: orderedGraphs.length,
            graphs: visibleGraphs.map((graph, index) => ({
                entryId: graph.entryId,
                artifactId: graph.artifactId,
                logicalName: graph.logicalName,
                name: graph.name,
                displayName: graph.displayName,
                path: graph.path,
                browserPath: graph.browserPath,
                format: graph.format,
                loading: index < 2 ? 'eager' : 'lazy',
                isSummary: graph.isSummary,
                ...mapGraphToViewModel(graph)
            }))
        };
    }
}

module.exports = {
    GraphStore
};
