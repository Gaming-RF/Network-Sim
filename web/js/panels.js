/* ============================================================
   PanelManager — UI Panel & Control Management
   ============================================================ */

;(function () {
  'use strict';

  class PanelManager {
    constructor() {
      // DOM refs
      this._logList      = document.getElementById('packetLogList');
      this._logCount     = document.getElementById('logCount');
      this._clearBtn     = document.getElementById('btnClearLog');
      this._sidebar      = document.getElementById('nodeSidebar');
      this._sidebarTitle = document.getElementById('sidebarTitle');
      this._sidebarBody  = document.getElementById('sidebarBody');
      this._closeBtn     = document.getElementById('btnCloseSidebar');
      this._cmdInput     = document.getElementById('commandInput');
      this._scenarioSel  = document.getElementById('scenarioSelect');
      this._toast        = document.getElementById('toast');
      this._demoBanner   = document.getElementById('demoBanner');

      // Stats
      this._statThroughput = document.getElementById('statThroughput');
      this._statPackets    = document.getElementById('statPackets');
      this._statLatency    = document.getElementById('statLatency');
      this._statNodes      = document.getElementById('statNodes');

      // State
      this._logEntries = 0;
      this._maxLogEntries = 500;
      this._commandHistory = [];
      this._historyIndex = -1;
      this._toastTimer = null;

      // Bind built-in handlers
      if (this._clearBtn) {
        this._clearBtn.addEventListener('click', () => this.clearLog());
      }
      if (this._closeBtn) {
        this._closeBtn.addEventListener('click', () => this.hideNodeDetail());
      }
    }

    /* ══════════════════════════════════════════════════════
       Packet Log Panel
       ══════════════════════════════════════════════════════ */

    /**
     * Add a color-coded log entry.
     * @param {object} event  { type, message, timestamp, packet_type, from, to, ... }
     */
    addLogEntry(event) {
      if (!this._logList) return;

      const entry = document.createElement('div');
      const pktType = this._resolvePacketType(event);
      const typeClass = pktType.toLowerCase();

      entry.className = `log-entry log-entry--${typeClass}`;

      const time = this._formatTime(event.timestamp || event.time);
      const msg  = event.message || event.msg || this._buildMessage(event);

      entry.innerHTML = `
        <span class="log-entry__time">${time}</span>
        <span class="log-entry__badge badge--${typeClass}">${pktType}</span>
        <span class="log-entry__msg">${this._escapeHtml(msg)}</span>
      `;

      this._logList.appendChild(entry);
      this._logEntries++;

      // Trim excess entries
      while (this._logList.children.length > this._maxLogEntries) {
        this._logList.removeChild(this._logList.firstChild);
        this._logEntries--;
      }

      // Update count
      if (this._logCount) {
        this._logCount.textContent = this._logEntries;
      }

      // Auto-scroll to bottom
      this._logList.scrollTop = this._logList.scrollHeight;
    }

    /**
     * Clear all log entries.
     */
    clearLog() {
      if (this._logList) {
        this._logList.innerHTML = '';
        this._logEntries = 0;
        if (this._logCount) this._logCount.textContent = '0';
      }
    }

    /* ══════════════════════════════════════════════════════
       Stats Panel
       ══════════════════════════════════════════════════════ */

    /**
     * Update statistics display with animated transitions.
     * @param {object} stats  { throughput, packets, latency, nodes }
     */
    updateStats(stats) {
      if (stats.throughput !== undefined && this._statThroughput) {
        this._animateValue(this._statThroughput, stats.throughput, 'pkt/s');
      }
      if (stats.packets !== undefined && this._statPackets) {
        this._animateValue(this._statPackets, stats.packets);
      }
      if (stats.latency !== undefined && this._statLatency) {
        this._animateValue(this._statLatency, stats.latency, 'ms');
      }
      if (stats.nodes !== undefined && this._statNodes) {
        this._animateValue(this._statNodes, stats.nodes);
      }
    }

    /* ══════════════════════════════════════════════════════
       Node Detail Sidebar
       ══════════════════════════════════════════════════════ */

    /**
     * Show node detail sidebar.
     * @param {object} nodeData  { id, label, type, interfaces, arp_cache, routing_table, ... }
     */
    showNodeDetail(nodeData) {
      if (!this._sidebar || !this._sidebarBody) return;

      // Title
      const typeIcon = { host: '🖥', router: '🔀', switch: '🔲' }[nodeData.type] || '●';
      if (this._sidebarTitle) {
        this._sidebarTitle.innerHTML = `${typeIcon} ${this._escapeHtml(nodeData.label || nodeData.id)}`;
      }

      // Build body content
      let html = '';

      // Basic info
      html += `
        <div class="sidebar-section">
          <div class="sidebar-section__title">General</div>
          <div class="sidebar-field">
            <span class="sidebar-field__label">ID</span>
            <span class="sidebar-field__value">${this._escapeHtml(nodeData.id)}</span>
          </div>
          <div class="sidebar-field">
            <span class="sidebar-field__label">Type</span>
            <span class="sidebar-field__value">${this._escapeHtml(nodeData.type || '—')}</span>
          </div>
        </div>
      `;

      // Interfaces
      if (nodeData.interfaces && nodeData.interfaces.length > 0) {
        html += `<div class="sidebar-section"><div class="sidebar-section__title">Interfaces</div>`;
        nodeData.interfaces.forEach(iface => {
          html += `
            <div class="interface-item">
              <div class="interface-item__name">${this._escapeHtml(iface.name || iface.id)}</div>
              <div class="interface-item__detail">
                IP: ${this._escapeHtml(iface.ip || '—')}<br>
                MAC: ${this._escapeHtml(iface.mac || '—')}<br>
                Mask: ${this._escapeHtml(iface.mask || iface.subnet || '—')}
              </div>
            </div>
          `;
        });
        html += `</div>`;
      }

      // ARP Cache
      if (nodeData.arp_cache && Object.keys(nodeData.arp_cache).length > 0) {
        html += `
          <div class="sidebar-section">
            <div class="sidebar-section__title">ARP Cache</div>
            <table class="table-mini">
              <thead><tr><th>IP</th><th>MAC</th></tr></thead>
              <tbody>
        `;
        for (const [ip, mac] of Object.entries(nodeData.arp_cache)) {
          html += `<tr><td>${this._escapeHtml(ip)}</td><td>${this._escapeHtml(mac)}</td></tr>`;
        }
        html += `</tbody></table></div>`;
      }

      // Routing Table
      if (nodeData.routing_table && nodeData.routing_table.length > 0) {
        html += `
          <div class="sidebar-section">
            <div class="sidebar-section__title">Routing Table</div>
            <table class="table-mini">
              <thead><tr><th>Dest</th><th>Gateway</th><th>Iface</th></tr></thead>
              <tbody>
        `;
        nodeData.routing_table.forEach(route => {
          html += `
            <tr>
              <td>${this._escapeHtml(route.destination || route.dest || '—')}</td>
              <td>${this._escapeHtml(route.gateway || route.gw || '—')}</td>
              <td>${this._escapeHtml(route.interface || route.iface || '—')}</td>
            </tr>
          `;
        });
        html += `</tbody></table></div>`;
      }

      this._sidebarBody.innerHTML = html;
      this._sidebar.classList.add('open');
    }

    /**
     * Hide the node detail sidebar.
     */
    hideNodeDetail() {
      if (this._sidebar) {
        this._sidebar.classList.remove('open');
      }
    }

    /* ══════════════════════════════════════════════════════
       Command Input
       ══════════════════════════════════════════════════════ */

    /**
     * Set up command input with Enter to submit and up/down history.
     * @param {function} onSubmit  callback(commandString)
     */
    setupCommandInput(onSubmit) {
      if (!this._cmdInput) return;

      this._cmdInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          const cmd = this._cmdInput.value.trim();
          if (!cmd) return;

          // Add to history
          this._commandHistory.push(cmd);
          this._historyIndex = this._commandHistory.length;

          // Clear input
          this._cmdInput.value = '';

          // Log the command
          this.addLogEntry({
            type: 'command',
            packet_type: 'CMD',
            message: `> ${cmd}`,
            timestamp: Date.now(),
          });

          // Invoke callback
          if (onSubmit) onSubmit(cmd);

        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          if (this._historyIndex > 0) {
            this._historyIndex--;
            this._cmdInput.value = this._commandHistory[this._historyIndex] || '';
          }
        } else if (e.key === 'ArrowDown') {
          e.preventDefault();
          if (this._historyIndex < this._commandHistory.length - 1) {
            this._historyIndex++;
            this._cmdInput.value = this._commandHistory[this._historyIndex] || '';
          } else {
            this._historyIndex = this._commandHistory.length;
            this._cmdInput.value = '';
          }
        }
      });
    }

    /**
     * Add a response message to the log.
     */
    addCommandResponse(text) {
      this.addLogEntry({
        type: 'info',
        packet_type: 'INFO',
        message: text,
        timestamp: Date.now(),
      });
    }

    /* ══════════════════════════════════════════════════════
       Scenario Selector
       ══════════════════════════════════════════════════════ */

    /**
     * Populate the scenario dropdown.
     * @param {Array<{value: string, label: string}>} list
     */
    setScenarios(list) {
      if (!this._scenarioSel) return;

      // Keep the first "select" option
      this._scenarioSel.innerHTML = '<option value="">— Select Scenario —</option>';
      list.forEach(item => {
        const opt = document.createElement('option');
        opt.value = item.value || item.id;
        opt.textContent = item.label || item.name || item.value;
        this._scenarioSel.appendChild(opt);
      });
    }

    /**
     * Register a callback when scenario changes.
     * @param {function} callback  Receives the selected scenario value
     */
    onScenarioChange(callback) {
      if (!this._scenarioSel) return;
      this._scenarioSel.addEventListener('change', () => {
        const val = this._scenarioSel.value;
        if (val && callback) callback(val);
      });
    }

    /* ══════════════════════════════════════════════════════
       Control Buttons State
       ══════════════════════════════════════════════════════ */

    /**
     * Update the Play/Pause button visual state.
     * @param {string} state  'playing' | 'paused' | 'stopped'
     */
    setSimulationState(state) {
      const playBtn  = document.getElementById('btnPlay');
      const pauseBtn = document.getElementById('btnPause');

      if (playBtn) playBtn.classList.toggle('active', state === 'playing');
      if (pauseBtn) pauseBtn.classList.toggle('active', state === 'paused');
    }

    /* ══════════════════════════════════════════════════════
       Demo Mode Banner
       ══════════════════════════════════════════════════════ */

    showDemoBanner() {
      if (this._demoBanner) this._demoBanner.classList.add('active');
    }

    hideDemoBanner() {
      if (this._demoBanner) this._demoBanner.classList.remove('active');
    }

    /* ══════════════════════════════════════════════════════
       Toast Notifications
       ══════════════════════════════════════════════════════ */

    showToast(message, duration = 3000) {
      if (!this._toast) return;
      clearTimeout(this._toastTimer);
      this._toast.textContent = message;
      this._toast.classList.add('show');
      this._toastTimer = setTimeout(() => {
        this._toast.classList.remove('show');
      }, duration);
    }

    /* ══════════════════════════════════════════════════════
       Internal Helpers
       ══════════════════════════════════════════════════════ */

    _resolvePacketType(event) {
      if (event.packet_type || event.packetType) {
        return (event.packet_type || event.packetType).toUpperCase();
      }
      const t = (event.type || event.event_type || '').toLowerCase();
      if (t.includes('arp'))  return 'ARP';
      if (t.includes('icmp')) return 'ICMP';
      if (t.includes('drop')) return 'DROP';
      if (t.includes('info') || t.includes('command')) return 'INFO';
      return 'IP';
    }

    _buildMessage(event) {
      const parts = [];
      const type = event.type || event.event_type || '';
      parts.push(type);
      if (event.from || event.source) parts.push(`from ${event.from || event.source}`);
      if (event.to || event.target)   parts.push(`→ ${event.to || event.target}`);
      if (event.details)              parts.push(`(${event.details})`);
      return parts.join(' ');
    }

    _formatTime(ts) {
      if (!ts) return '—';
      const d = typeof ts === 'number' ? new Date(ts) : new Date();
      const h = String(d.getHours()).padStart(2, '0');
      const m = String(d.getMinutes()).padStart(2, '0');
      const s = String(d.getSeconds()).padStart(2, '0');
      const ms = String(d.getMilliseconds()).padStart(3, '0');
      return `${h}:${m}:${s}.${ms}`;
    }

    _escapeHtml(str) {
      if (typeof str !== 'string') return String(str || '');
      return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    _animateValue(el, value, unit) {
      if (!el) return;
      const text = unit
        ? `${value} <span class="stat-item__unit">${unit}</span>`
        : String(value);

      // Brief scale animation
      el.style.transform = 'scale(1.1)';
      el.style.color = 'var(--cyan)';
      el.innerHTML = text;

      setTimeout(() => {
        el.style.transform = 'scale(1)';
        el.style.color = '';
      }, 200);
    }
  }

  // Export
  window.PanelManager = PanelManager;

})();
