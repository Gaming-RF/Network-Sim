/* ============================================================
   SimWebSocket — WebSocket Client for NetSim
   ============================================================ */

;(function () {
  'use strict';

  const State = Object.freeze({
    CONNECTING:   'CONNECTING',
    CONNECTED:    'CONNECTED',
    DISCONNECTED: 'DISCONNECTED',
  });

  class SimWebSocket {
    /**
     * @param {string} url  WebSocket server URL
     */
    constructor(url = 'ws://localhost:8765/ws') {
      this.url = url;
      this.state = State.DISCONNECTED;
      this._ws = null;
      this._listeners = {};          // { eventType: Set<callback> }
      this._reconnectDelay = 1000;   // ms — current backoff
      this._reconnectTimer = null;
      this._maxReconnectDelay = 30000;
      this._intentionalClose = false;
      this._connectPromiseResolve = null;
      this._connectPromiseReject = null;
    }

    /* ── Public API ────────────────────────────────────── */

    /**
     * Open the WebSocket connection.
     * Returns a promise that resolves on open or rejects on first failure.
     */
    connect() {
      return new Promise((resolve, reject) => {
        if (this.state === State.CONNECTED) {
          resolve();
          return;
        }

        this._intentionalClose = false;
        this._connectPromiseResolve = resolve;
        this._connectPromiseReject = reject;
        this._openSocket();
      });
    }

    /**
     * Gracefully close the connection (no auto-reconnect).
     */
    disconnect() {
      this._intentionalClose = true;
      clearTimeout(this._reconnectTimer);
      if (this._ws) {
        this._ws.close(1000, 'Client disconnect');
      }
      this._setState(State.DISCONNECTED);
    }

    /**
     * Send a command to the server.
     * @param {string} command   e.g. "ping", "load_scenario", "step"
     * @param {object} args      e.g. { from: "host-a", to: "192.168.1.20" }
     */
    send(command, args = {}) {
      if (this.state !== State.CONNECTED || !this._ws) {
        console.warn('[WS] Cannot send — not connected');
        this._emit('error', { message: 'Not connected to server' });
        return false;
      }
      const payload = JSON.stringify({ command, ...args });
      this._ws.send(payload);
      return true;
    }

    /**
     * Register an event handler.
     * Built-in events: 'open', 'close', 'error', 'state_change'
     * Server events: anything the server sends in the `type` field.
     */
    onEvent(type, callback) {
      if (!this._listeners[type]) this._listeners[type] = new Set();
      this._listeners[type].add(callback);
    }

    /**
     * Remove an event handler.
     */
    offEvent(type, callback) {
      if (this._listeners[type]) {
        this._listeners[type].delete(callback);
      }
    }

    /* ── Internal ──────────────────────────────────────── */

    _openSocket() {
      this._setState(State.CONNECTING);

      try {
        this._ws = new WebSocket(this.url);
      } catch (e) {
        this._onError(e);
        return;
      }

      this._ws.onopen = () => {
        this._reconnectDelay = 1000;          // reset backoff
        this._setState(State.CONNECTED);
        this._emit('open');
        if (this._connectPromiseResolve) {
          this._connectPromiseResolve();
          this._connectPromiseResolve = null;
          this._connectPromiseReject = null;
        }
      };

      this._ws.onclose = (ev) => {
        this._setState(State.DISCONNECTED);
        this._emit('close', { code: ev.code, reason: ev.reason });

        if (!this._intentionalClose) {
          this._scheduleReconnect();
        }
      };

      this._ws.onerror = (ev) => {
        this._onError(ev);
      };

      this._ws.onmessage = (ev) => {
        this._handleMessage(ev.data);
      };
    }

    _onError(ev) {
      console.warn('[WS] Error:', ev);
      this._emit('error', { message: 'Connection error' });

      // If this is the very first connect attempt, reject the promise
      if (this._connectPromiseReject) {
        this._connectPromiseReject(new Error('WebSocket connection failed'));
        this._connectPromiseResolve = null;
        this._connectPromiseReject = null;
      }
    }

    _handleMessage(raw) {
      let data;
      try {
        data = JSON.parse(raw);
      } catch {
        console.warn('[WS] Non-JSON message:', raw);
        return;
      }

      // Emit by the message's `type` field, plus a catch-all 'message'
      if (data.type) {
        this._emit(data.type, data);
      }
      this._emit('message', data);
    }

    _scheduleReconnect() {
      clearTimeout(this._reconnectTimer);
      const delay = this._reconnectDelay;
      console.log(`[WS] Reconnecting in ${delay}ms…`);
      this._reconnectTimer = setTimeout(() => {
        this._reconnectDelay = Math.min(this._reconnectDelay * 2, this._maxReconnectDelay);
        this._openSocket();
      }, delay);
    }

    _setState(newState) {
      if (this.state === newState) return;
      const prev = this.state;
      this.state = newState;
      this._updateUI();
      this._emit('state_change', { from: prev, to: newState });
    }

    _emit(type, data = {}) {
      const cbs = this._listeners[type];
      if (cbs) {
        for (const cb of cbs) {
          try { cb(data); } catch (e) { console.error(`[WS] Event handler error (${type}):`, e); }
        }
      }
    }

    /**
     * Update the connection indicator in the DOM.
     */
    _updateUI() {
      const dot   = document.getElementById('connectionDot');
      const label = document.getElementById('connectionLabel');
      if (!dot || !label) return;

      dot.classList.remove('connected', 'connecting');

      switch (this.state) {
        case State.CONNECTED:
          dot.classList.add('connected');
          label.textContent = 'Connected';
          break;
        case State.CONNECTING:
          dot.classList.add('connecting');
          label.textContent = 'Connecting…';
          break;
        default:
          label.textContent = 'Disconnected';
      }
    }
  }

  // Expose state enum
  SimWebSocket.State = State;

  // Export
  window.SimWebSocket = SimWebSocket;

})();
