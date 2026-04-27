import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { AuthService } from './auth.service';
import {
  ChatRequest,
  ChatResponse,
  SessionSummary,
  SessionWithMessages,
  PaginatedSessions,
  AnalysisResponse,
  TimelineEvent,
  DetailedStats,
  HealthDashboard,
  HealthTimelineItem,
  HealthRiskResponse
} from '../models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);


  chatStream(
    request: ChatRequest,
    onStart: (sessionId: string) => void,
    onToken: (token: string) => void,
    onDone: () => void,
    onError: (err: Error) => void
  ): void {
    const token = this.auth.getAccessToken();

    fetch('/api/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      },
      body: JSON.stringify(request)
    })
      .then(async (res) => {
        if (!res.ok || !res.body) {
          throw new Error(`HTTP ${res.status}`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let sessionIdEmitted = false;

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            for (const line of chunk.split('\n')) {
              if (!line.startsWith('data: ')) continue;
              const data = line.slice(6).trim();
              if (!data || data === '[DONE]') {
                onDone();
                return;
              }

              try {
                const event = JSON.parse(data) as {
                  type?: string;
                  data?: string;
                  session_id?: string;
                };
                if (event.session_id && !sessionIdEmitted) {
                  onStart(event.session_id);
                  sessionIdEmitted = true;
                }
                if (event.type === 'token' && event.data) {
                  onToken(event.data);
                } else if (event.type === 'done') {
                  onDone();
                  return;
                }
              } catch {
                onToken(data);
              }
            }
          }
          onDone();
        } finally {
          reader.releaseLock();
        }
      })
      .catch(onError);
  }


  getHistory(page = 1, size = 20): Observable<PaginatedSessions> {
    const params = new HttpParams()
      .set('page', page)
      .set('size', size);
    return this.http.get<PaginatedSessions>('/api/history/sessions', { params });
  }

  getSessionDetail(sessionId: string): Observable<SessionWithMessages> {
    return this.http.get<SessionWithMessages>(`/api/history/sessions/${sessionId}`);
  }

  deleteSession(sessionId: string): Observable<void> {
    return this.http.delete<void>(`/api/history/sessions/${sessionId}`);
  }

  searchHistory(query: string, page = 1, size = 20): Observable<PaginatedSessions> {
    const params = new HttpParams()
      .set('q', query)
      .set('page', page)
      .set('size', size);
    return this.http.get<PaginatedSessions>('/api/history/search', { params });
  }

  createNewSession(): Observable<SessionSummary> {
    return this.http.post<SessionSummary>('/api/chat/sessions', {});
  }


  getAnalysis(imageBase64: string): Observable<AnalysisResponse> {
    return this.http.post<AnalysisResponse>('/api/analysis/image', {
      image_base64: imageBase64
    });
  }

  getTimeline(sessionId: string): Observable<TimelineEvent[]> {
    return this.http.get<TimelineEvent[]>(`/api/analysis/timeline/${sessionId}`);
  }

  getStatistics(): Observable<DetailedStats> {
    return this.http.get<DetailedStats>('/api/analysis/statistics');
  }

  getDashboard(days: number): Observable<HealthDashboard> {
    const params = new HttpParams().set('days', days);
    return this.http.get<HealthDashboard>('/api/analysis/dashboard', { params });
  }

  getHealthTimeline(days: number): Observable<HealthTimelineItem[]> {
    const params = new HttpParams().set('days', days);
    return this.http.get<HealthTimelineItem[]>('/api/analysis/health-timeline', { params });
  }

  getWeatherRisk(): Observable<HealthRiskResponse> {
    return this.http.get<HealthRiskResponse>('/api/health-risk/hanoi');
  }
}
