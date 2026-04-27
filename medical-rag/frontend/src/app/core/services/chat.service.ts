import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { ChatSession, ChatMessage } from '../models';
import { AuthService } from './auth.service';

@Injectable({ providedIn: 'root' })
export class ChatService {
  private readonly http = inject(HttpClient);
  private readonly authService = inject(AuthService);

  // API trả về PaginatedSessions { items, total, page... } — lấy .items
  getSessions(): Observable<ChatSession[]> {
    return this.http.get<{ items: ChatSession[] }>('/api/history/sessions').pipe(
      map(r => r.items ?? [])
    );
  }

  // API trả về SessionWithMessages { session, messages[] } — lấy .messages
  getMessages(sessionId: string): Observable<ChatMessage[]> {
    return this.http.get<{ messages: ChatMessage[] }>(`/api/history/sessions/${sessionId}`).pipe(
      map(r => r.messages ?? [])
    );
  }

  deleteSession(sessionId: string): Observable<void> {
    return this.http.delete<void>(`/api/history/sessions/${sessionId}`);
  }

  /**
   * SSE streaming via fetch + ReadableStream.
   * NEVER use EventSource — use this async generator instead.
   */
  async *streamChat(
    sessionId: string | undefined,
    message: string,
    imageBase64?: string
  ): AsyncGenerator<string> {
    const token = this.authService.getToken();
    const body: Record<string, unknown> = { message };
    if (sessionId) body['session_id'] = sessionId;
    if (imageBase64) body['image_base64'] = imageBase64;

    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(body)
    });

    if (!response.ok || !response.body) {
      throw new Error(`Chat stream error: HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        for (const line of chunk.split('\n')) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim();
            if (data === '[DONE]') return;
            if (data) yield data;
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  }
}
