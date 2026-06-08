/* ============================================================
   PacketAnimator — Simulation Event → Visual Animation
   ============================================================ */

;(function () {
  'use strict';

  const PACKET_COLORS = {
    ARP:  '#ffb800',
    ICMP: '#00d4ff',
    IP:   '#ff006e',
    DROP: '#ff3333',
  };

  class PacketAnimator {
    /**
     * @param {TopologyRenderer} topologyRenderer
     */
    constructor(topologyRenderer) {
      this._topo = topologyRenderer;
      this._queue = [];           // queued animations
      this._activeCount = 0;
      this._maxConcurrent = 12;   // max simultaneous animations
      this._speedMultiplier = 1;
      this._paused = false;
    }

    /* ── Public ────────────────────────────────────────── */

    /**
     * Set the speed multiplier (higher = faster animations).
     */
    setSpeed(multiplier) {
      this._speedMultiplier = multiplier;
    }

    /**
     * Pause/resume all animations.
     */
    setPaused(paused) {
      this._paused = paused;
    }

    /**
     * Process a simulation event and trigger appropriate animation.
     * @param {object} event  Server-sent event object
     */
    handleEvent(event) {
      if (this._paused) return;

      const type = event.type || event.event_type;
      if (!type) return;

      switch (type) {
        case 'PACKET_SENT':
        case 'packet_sent':
          this._queueAnimation(() => this._animateSend(event));
          break;

        case 'PACKET_RECEIVED':
        case 'packet_received':
          this._animateReceive(event);
          break;

        case 'PACKET_DROPPED':
        case 'packet_dropped':
          this._animateDrop(event);
          break;

        case 'ARP_REQUEST':
        case 'arp_request':
          this._queueAnimation(() => this._animateSend({
            ...event,
            packet_type: 'ARP',
          }));
          break;

        case 'ARP_REPLY':
        case 'arp_reply':
          this._queueAnimation(() => this._animateSend({
            ...event,
            packet_type: 'ARP',
          }));
          break;

        case 'ICMP_ECHO':
        case 'icmp_echo':
        case 'ICMP_REPLY':
        case 'icmp_reply':
          this._queueAnimation(() => this._animateSend({
            ...event,
            packet_type: 'ICMP',
          }));
          break;

        case 'NODE_UPDATE':
        case 'node_update':
          this._handleNodeUpdate(event);
          break;

        default:
          // Unknown event type — ignore gracefully
          break;
      }
    }

    /**
     * Clear all queued/pending animations.
     */
    clearQueue() {
      this._queue = [];
      this._activeCount = 0;
    }

    /* ── Internal ──────────────────────────────────────── */

    _queueAnimation(fn) {
      if (this._activeCount < this._maxConcurrent) {
        this._activeCount++;
        fn();
        // Auto-decrement after animation likely finishes
        setTimeout(() => {
          this._activeCount = Math.max(0, this._activeCount - 1);
          this._drainQueue();
        }, 1200 / this._speedMultiplier);
      } else {
        this._queue.push(fn);
      }
    }

    _drainQueue() {
      while (this._queue.length > 0 && this._activeCount < this._maxConcurrent) {
        const fn = this._queue.shift();
        this._activeCount++;
        fn();
        setTimeout(() => {
          this._activeCount = Math.max(0, this._activeCount - 1);
          this._drainQueue();
        }, 1200 / this._speedMultiplier);
      }
    }

    _animateSend(event) {
      const linkId   = event.link_id || event.linkId;
      const from     = event.from || event.from_node || event.source;
      const to       = event.to || event.to_node || event.target;
      const pktType  = (event.packet_type || event.packetType || 'IP').toUpperCase();
      const duration = (event.duration || 800) / this._speedMultiplier;

      if (from && to) {
        this._topo.animatePacket(linkId, from, to, pktType, duration);
      }
    }

    _animateReceive(event) {
      const nodeId  = event.node || event.to || event.to_node || event.target;
      const pktType = (event.packet_type || event.packetType || 'IP').toUpperCase();
      const color   = PACKET_COLORS[pktType] || '#00d4ff';

      if (nodeId) {
        this._topo.highlightNode(nodeId, color, 500);
      }
    }

    _animateDrop(event) {
      const nodeId = event.node || event.at_node || event.from || event.source;
      if (!nodeId) return;

      // Flash red
      this._topo.highlightNode(nodeId, '#ff3333', 800);

      // Show X marker at the node position
      const pos = this._topo.getNodeDOMPosition(nodeId);
      if (pos) {
        const container = document.getElementById('topologyCanvas');
        if (container) {
          const marker = document.createElement('div');
          marker.className = 'drop-marker';
          marker.textContent = '✕';
          marker.style.left = `${pos.x}px`;
          marker.style.top  = `${pos.y}px`;
          marker.style.transform = 'translate(-50%, -50%)';
          container.appendChild(marker);
          setTimeout(() => marker.remove(), 600);
        }
      }
    }

    _handleNodeUpdate(event) {
      const nodeId = event.node || event.node_id;
      if (!nodeId) return;

      const state = {};
      if (event.arp_cache !== undefined) state.arp_cache = event.arp_cache;
      if (event.routing_table !== undefined) state.routing_table = event.routing_table;
      if (event.interfaces !== undefined) state.interfaces = event.interfaces;

      this._topo.updateNodeState(nodeId, state);
    }
  }

  // Export
  window.PacketAnimator = PacketAnimator;

})();
