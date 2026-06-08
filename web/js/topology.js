/* ============================================================
   TopologyRenderer — vis-network Graph Visualization
   ============================================================ */

;(function () {
  'use strict';

  /** Color map for node types */
  const NODE_STYLES = {
    host: {
      shape: 'dot',
      size: 22,
      color: {
        background: 'rgba(0, 212, 255, 0.10)',
        border: '#00d4ff',
        highlight: { background: 'rgba(0, 212, 255, 0.25)', border: '#00d4ff' },
        hover:      { background: 'rgba(0, 212, 255, 0.18)', border: '#00d4ff' },
      },
      borderWidth: 2,
      borderWidthSelected: 3,
      font: { color: 'rgba(255,255,255,0.85)', size: 12, face: 'Inter, sans-serif' },
    },
    router: {
      shape: 'diamond',
      size: 26,
      color: {
        background: 'rgba(255, 0, 110, 0.10)',
        border: '#ff006e',
        highlight: { background: 'rgba(255, 0, 110, 0.25)', border: '#ff006e' },
        hover:      { background: 'rgba(255, 0, 110, 0.18)', border: '#ff006e' },
      },
      borderWidth: 2,
      borderWidthSelected: 3,
      font: { color: 'rgba(255,255,255,0.85)', size: 12, face: 'Inter, sans-serif' },
    },
    switch: {
      shape: 'square',
      size: 20,
      color: {
        background: 'rgba(0, 255, 136, 0.10)',
        border: '#00ff88',
        highlight: { background: 'rgba(0, 255, 136, 0.25)', border: '#00ff88' },
        hover:      { background: 'rgba(0, 255, 136, 0.18)', border: '#00ff88' },
      },
      borderWidth: 2,
      borderWidthSelected: 3,
      font: { color: 'rgba(255,255,255,0.85)', size: 12, face: 'Inter, sans-serif' },
    },
  };

  const PACKET_COLORS = {
    ARP:  '#ffb800',
    ICMP: '#00d4ff',
    IP:   '#ff006e',
    DROP: '#ff3333',
    DEFAULT: '#ffffff',
  };

  class TopologyRenderer {
    /**
     * @param {string} containerId  DOM id of the canvas container
     */
    constructor(containerId) {
      this._containerId = containerId;
      this._container = document.getElementById(containerId);
      this._network = null;
      this._nodes = null;       // vis.DataSet
      this._edges = null;       // vis.DataSet
      this._nodeDataMap = {};   // id -> original node data
      this._edgeDataMap = {};   // id -> original edge data
      this._onNodeSelected = null;  // callback
      this._animationElements = []; // currently animating DOM elements
    }

    /* ── Public ────────────────────────────────────────── */

    /**
     * Load topology data and render the graph.
     * @param {{ nodes: Array, links: Array }} data
     */
    loadTopology(data) {
      this.clear();

      // Build vis DataSets
      const visNodes = (data.nodes || []).map(n => this._buildNode(n));
      const visEdges = (data.links || []).map(l => this._buildEdge(l));

      this._nodes = new vis.DataSet(visNodes);
      this._edges = new vis.DataSet(visEdges);

      // Store original data
      (data.nodes || []).forEach(n => { this._nodeDataMap[n.id] = n; });
      (data.links || []).forEach(l => { this._edgeDataMap[l.id] = l; });

      const options = {
        autoResize: true,
        physics: {
          enabled: true,
          solver: 'forceAtlas2Based',
          forceAtlas2Based: {
            gravitationalConstant: -40,
            centralGravity: 0.005,
            springLength: 140,
            springConstant: 0.06,
            damping: 0.4,
          },
          stabilization: { iterations: 150, fit: true },
        },
        interaction: {
          hover: true,
          tooltipDelay: 200,
          zoomView: true,
          dragView: true,
          navigationButtons: false,
        },
        edges: {
          smooth: { type: 'continuous', roundness: 0.2 },
          width: 1.5,
          color: {
            color: 'rgba(255,255,255,0.12)',
            highlight: 'rgba(255,255,255,0.3)',
            hover: 'rgba(255,255,255,0.2)',
          },
          font: {
            color: 'rgba(255,255,255,0.35)',
            size: 10,
            face: 'JetBrains Mono, monospace',
            strokeWidth: 0,
            align: 'middle',
          },
        },
        nodes: {
          shadow: {
            enabled: true,
            color: 'rgba(0,0,0,0.3)',
            size: 8,
            x: 0, y: 2,
          },
        },
      };

      this._network = new vis.Network(this._container, {
        nodes: this._nodes,
        edges: this._edges,
      }, options);

      // Events
      this._network.on('click', (params) => {
        if (params.nodes.length > 0) {
          const nodeId = params.nodes[0];
          const nodeData = this._nodeDataMap[nodeId];
          if (nodeData && this._onNodeSelected) {
            this._onNodeSelected(nodeData);
          }
        }
      });

      this._network.on('hoverNode', (params) => {
        this._container.style.cursor = 'pointer';
      });

      this._network.on('blurNode', () => {
        this._container.style.cursor = 'default';
      });

      // Build tooltip on hover
      this._network.on('showPopup', () => {});
    }

    /**
     * Set the callback for node selection.
     * @param {function} callback  Receives the node data object
     */
    onNodeSelected(callback) {
      this._onNodeSelected = callback;
    }

    /**
     * Animate a packet traveling along an edge.
     * @param {string} linkId
     * @param {string} fromNodeId
     * @param {string} toNodeId
     * @param {string} packetType  e.g. "ARP", "ICMP", "IP", "DROP"
     * @param {number} duration    ms
     */
    animatePacket(linkId, fromNodeId, toNodeId, packetType, duration = 800) {
      if (!this._network) return;

      const fromPos = this._network.getPositions([fromNodeId])[fromNodeId];
      const toPos   = this._network.getPositions([toNodeId])[toNodeId];
      if (!fromPos || !toPos) return;

      // Convert canvas coords to DOM coords
      const fromDOM = this._network.canvasToDOM(fromPos);
      const toDOM   = this._network.canvasToDOM(toPos);

      const color = PACKET_COLORS[packetType] || PACKET_COLORS.DEFAULT;

      // Create animated dot
      const dot = document.createElement('div');
      dot.style.cssText = `
        position: absolute;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: ${color};
        box-shadow: 0 0 10px ${color}, 0 0 20px ${color}40;
        pointer-events: none;
        z-index: 50;
        left: ${fromDOM.x}px;
        top: ${fromDOM.y}px;
        transform: translate(-50%, -50%);
        transition: none;
      `;
      this._container.appendChild(dot);
      this._animationElements.push(dot);

      // Animate with requestAnimationFrame for smoothness
      const startTime = performance.now();
      const animate = (now) => {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        // Ease in-out
        const ease = progress < 0.5
          ? 2 * progress * progress
          : -1 + (4 - 2 * progress) * progress;

        // Recalculate positions (in case of zoom/pan)
        const fp = this._network.canvasToDOM(this._network.getPositions([fromNodeId])[fromNodeId] || fromPos);
        const tp = this._network.canvasToDOM(this._network.getPositions([toNodeId])[toNodeId] || toPos);

        const x = fp.x + (tp.x - fp.x) * ease;
        const y = fp.y + (tp.y - fp.y) * ease;

        dot.style.left = `${x}px`;
        dot.style.top  = `${y}px`;

        if (progress < 1) {
          requestAnimationFrame(animate);
        } else {
          // Fade out
          dot.style.transition = 'opacity 0.2s';
          dot.style.opacity = '0';
          setTimeout(() => {
            dot.remove();
            const idx = this._animationElements.indexOf(dot);
            if (idx !== -1) this._animationElements.splice(idx, 1);
          }, 200);
        }
      };

      requestAnimationFrame(animate);
    }

    /**
     * Briefly highlight a node with a color.
     */
    highlightNode(nodeId, color = '#00d4ff', duration = 600) {
      if (!this._nodes) return;

      const node = this._nodes.get(nodeId);
      if (!node) return;

      const origColor = { ...node.color };

      this._nodes.update({
        id: nodeId,
        color: {
          background: color + '40',
          border: color,
        },
        borderWidth: 4,
      });

      setTimeout(() => {
        const style = this._getNodeStyle(this._nodeDataMap[nodeId]?.type || 'host');
        this._nodes.update({
          id: nodeId,
          color: style.color,
          borderWidth: style.borderWidth,
        });
      }, duration);
    }

    /**
     * Update node data (e.g. ARP cache, routing table).
     */
    updateNodeState(nodeId, state) {
      if (this._nodeDataMap[nodeId]) {
        Object.assign(this._nodeDataMap[nodeId], state);
      }
    }

    /**
     * Clear the graph.
     */
    clear() {
      // Remove any animated elements
      this._animationElements.forEach(el => el.remove());
      this._animationElements = [];

      if (this._network) {
        this._network.destroy();
        this._network = null;
      }
      this._nodes = null;
      this._edges = null;
      this._nodeDataMap = {};
      this._edgeDataMap = {};
    }

    /**
     * Fit the view to show all nodes.
     */
    fitView() {
      if (this._network) {
        this._network.fit({ animation: { duration: 500, easingFunction: 'easeInOutQuad' } });
      }
    }

    /**
     * Get the positions of a node in DOM coordinates.
     */
    getNodeDOMPosition(nodeId) {
      if (!this._network) return null;
      const pos = this._network.getPositions([nodeId])[nodeId];
      if (!pos) return null;
      return this._network.canvasToDOM(pos);
    }

    /* ── Internal ──────────────────────────────────────── */

    _buildNode(n) {
      const style = this._getNodeStyle(n.type);
      const title = this._buildTooltip(n);

      return {
        id: n.id,
        label: n.label || n.id,
        title: title,
        ...style,
      };
    }

    _getNodeStyle(type) {
      return NODE_STYLES[type] || NODE_STYLES.host;
    }

    _buildTooltip(n) {
      const lines = [`<b>${n.label || n.id}</b>`, `Type: ${n.type || 'unknown'}`];
      if (n.interfaces) {
        n.interfaces.forEach(iface => {
          lines.push(`${iface.name}: ${iface.ip || '—'} / ${iface.mac || '—'}`);
        });
      }
      return lines.join('<br>');
    }

    _buildEdge(l) {
      return {
        id: l.id,
        from: l.from || l.source,
        to: l.to || l.target,
        label: l.bandwidth ? `${l.bandwidth}` : undefined,
        title: l.bandwidth ? `Bandwidth: ${l.bandwidth}` : undefined,
      };
    }
  }

  // Export
  window.TopologyRenderer = TopologyRenderer;

})();
