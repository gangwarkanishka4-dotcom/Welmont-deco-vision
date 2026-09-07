// Derive the WS URL from the single VITE_API_BASE env var (http->ws, https->wss) — there is
// no separate WS env var in this project's .env.
import { API_BASE_URL } from '../services/api.js';

const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');
const WS_PATH = '/ws/events';

const MAX_BACKOFF_MS = 30_000;
const BASE_BACKOFF_MS = 1_000;

/**
 * Single shared WebSocket connection for the whole app. Components subscribe by event type
 * instead of each opening their own socket, so a busy TRACKED_STATE_UPDATE stream from one
 * camera doesn't multiply into N sockets across N mounted components.
 */
export class EventSocketClient {
  ws = null;
  status = 'connecting';
  listeners = new Map();
  statusListeners = new Set();
  reconnectAttempt = 0;
  reconnectTimer = null;
  closedByUser = false;

  connect() {
    this.closedByUser = false;
    this.open();
  }

  disconnect() {
    this.closedByUser = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
  }

  open() {
    this.setStatus(this.reconnectAttempt === 0 ? 'connecting' : 'reconnecting');
    const socket = new WebSocket(`${WS_BASE_URL}${WS_PATH}`);
    this.ws = socket;

    socket.onopen = () => {
      this.reconnectAttempt = 0;
      this.setStatus('open');
    };

    socket.onmessage = (evt) => {
      let parsed;
      try {
        parsed = JSON.parse(evt.data);
      } catch {
        return; // ignore malformed frames
      }
      this.listeners.get(parsed.type)?.forEach((fn) => fn(parsed));
    };

    socket.onclose = () => {
      this.setStatus('closed');
      if (!this.closedByUser) this.scheduleReconnect();
    };

    socket.onerror = () => {
      socket.close();
    };
  }

  // Exponential backoff with a cap, so a dead backend doesn't spin the tab into a reconnect storm.
  scheduleReconnect() {
    const delay = Math.min(BASE_BACKOFF_MS * 2 ** this.reconnectAttempt, MAX_BACKOFF_MS);
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => this.open(), delay);
  }

  setStatus(status) {
    this.status = status;
    this.statusListeners.forEach((fn) => fn(status));
  }

  getStatus() {
    return this.status;
  }

  onStatusChange(fn) {
    this.statusListeners.add(fn);
    return () => this.statusListeners.delete(fn);
  }

  subscribe(type, fn) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(fn);
    return () => this.listeners.get(type)?.delete(fn);
  }
}
