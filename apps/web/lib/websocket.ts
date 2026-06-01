/** WebSocket 实时通信客户端。

提供与后端 WebSocket/SSE 的连接管理，用于：
- Workflow 运行状态实时更新
- Session 消息实时推送
- 系统通知
 */

import { API_BASE_URL } from "./api";

type MessageHandler = (event: string, data: unknown) => void;

/** WebSocket 连接管理器 */
class WebSocketManager {
  private ws: WebSocket | null = null;
  private handlers: Map<string, Set<MessageHandler>> = new Map();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 3000;

  /** 连接 WebSocket */
  connect(path: string = "/ws/events"): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    const wsUrl = API_BASE_URL.replace(/^http/, "ws") + path;
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log("[WS] 已连接");
      this.reconnectAttempts = 0;
    };

    this.ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data as string) as {
          event: string;
          data: unknown;
        };
        this.dispatch(parsed.event, parsed.data);
      } catch {
        // 非 JSON 消息忽略
      }
    };

    this.ws.onclose = () => {
      console.log("[WS] 连接关闭");
      this.attemptReconnect(path);
    };

    this.ws.onerror = (err) => {
      console.error("[WS] 连接错误", err);
    };
  }

  /** 断开连接 */
  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  /** 注册事件处理器 */
  on(event: string, handler: MessageHandler): () => void {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, new Set());
    }
    this.handlers.get(event)!.add(handler);

    // 返回取消注册函数
    return () => {
      this.handlers.get(event)?.delete(handler);
    };
  }

  /** 发送消息 */
  send(event: string, data: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ event, data }));
    }
  }

  /** 分发事件 */
  private dispatch(event: string, data: unknown): void {
    const handlers = this.handlers.get(event);
    if (handlers) {
      handlers.forEach((handler) => handler(event, data));
    }
    // 通配符处理器
    const wildcardHandlers = this.handlers.get("*");
    if (wildcardHandlers) {
      wildcardHandlers.forEach((handler) => handler(event, data));
    }
  }

  /** 尝试重连 */
  private attemptReconnect(path: string): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log("[WS] 达到最大重连次数，停止重连");
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * this.reconnectAttempts;

    console.log(`[WS] ${delay}ms 后重连 (第 ${this.reconnectAttempts} 次)`);
    this.reconnectTimer = setTimeout(() => {
      this.connect(path);
    }, delay);
  }
}

/** 全局 WebSocket 管理器实例 */
export const wsManager = new WebSocketManager();

/** SSE (Server-Sent Events) 客户端 - 作为 WebSocket 的降级方案 */
export class SSEClient {
  private eventSource: EventSource | null = null;
  private handlers: Map<string, Set<MessageHandler>> = new Map();

  /** 连接 SSE */
  connect(path: string = "/sse/events"): void {
    const sseUrl = `${API_BASE_URL}${path}`;
    this.eventSource = new EventSource(sseUrl);

    this.eventSource.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data) as {
          event: string;
          data: unknown;
        };
        this.dispatch(parsed.event, parsed.data);
      } catch {
        // 非 JSON 消息忽略
      }
    };

    this.eventSource.onerror = () => {
      console.error("[SSE] 连接错误");
    };
  }

  /** 断开连接 */
  disconnect(): void {
    this.eventSource?.close();
    this.eventSource = null;
  }

  /** 注册事件处理器 */
  on(event: string, handler: MessageHandler): () => void {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, new Set());
    }
    this.handlers.get(event)!.add(handler);
    return () => {
      this.handlers.get(event)?.delete(handler);
    };
  }

  private dispatch(event: string, data: unknown): void {
    const handlers = this.handlers.get(event);
    if (handlers) {
      handlers.forEach((handler) => handler(event, data));
    }
  }
}

/** 全局 SSE 客户端实例 */
export const sseClient = new SSEClient();

// ── 预定义事件类型 ──

export type WorkflowRunEvent = {
  run_id: string;
  status: string;
  workflow_id: string;
};

export type SessionMessageEvent = {
  session_id: string;
  message_id: string;
  role: string;
  content: string;
};

export type SystemNotificationEvent = {
  type: "info" | "warning" | "error";
  title: string;
  message: string;
};
