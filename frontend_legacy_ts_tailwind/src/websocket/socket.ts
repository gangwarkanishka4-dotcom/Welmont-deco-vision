import type { EventType, SocketConnectionStatus, SocketEvent } from '../types/events';

const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000';
const WS_PATH = '/ws/events';

type Listener = (evt: SocketEvent) => void;
type StatusListener = (status: SocketConnectionStatus) => void;

const MAX_BACKOFF_MS = 30_000;
const BASE_BACKOFF_MS = 1_000;

/**
 * Single shared WebSocket connection for the whole app. Components subscribe by event type
 * instead of each opening their own socket, so a busy TRACKED_STATE_UPDATE stream from one
 * camera doesn't multiply into N sockets across N mounted components.
 */
export class EventSocketClient {
  private ws: WebSocket | null = null;
  private status: SocketConnectionStatus = 'connecting';
  private listeners = new Map<EventType, Set<Listener>>();
  private statusListeners = new Set<StatusListener>();
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closedByUser = false;

  connect(): void {
    this.closedByUser = false;
    this.open();
  }

  disconnect(): void {
    this.closedByUser = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
  }

  private open(): void {
    this.setStatus(this.reconnectAttempt === 0 ? 'connecting' : 'reconnecting');
    const socket = new WebSocket(`${WS_BASE_URL}${WS_PATH}`);
    this.ws = socket;

    socket.onopen = () => {
      this.reconnectAttempt = 0;
      this.setStatus('open');
    };

    socket.onmessage = (evt) => {
      let parsed: SocketEvent;
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
  private scheduleReconnect(): void {
    const delay = Math.min(BASE_BACKOFF_MS * 2 ** this.reconnectAttempt, MAX_BACKOFF_MS);
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => this.open(), delay);
  }

  private setStatus(status: SocketConnectionStatus): void {
    this.status = status;
    this.statusListeners.forEach((fn) => fn(status));
  }

  getStatus(): SocketConnectionStatus {
    return this.status;
  }

  onStatusChange(fn: StatusListener): () => void {
    this.statusListeners.add(fn);
    return () => this.statusListeners.delete(fn);
  }

  subscribe(type: EventType, fn: Listener): () => void {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(fn);
    return () => this.listeners.get(type)?.delete(fn);
  }
}
