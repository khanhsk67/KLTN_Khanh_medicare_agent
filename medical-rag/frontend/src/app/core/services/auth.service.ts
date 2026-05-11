import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  LoginRequest,
  RegisterRequest,
  TokenResponse,
  UserProfile,
} from '../models';

const ACCESS_KEY = 'access_token';
const REFRESH_KEY = 'refresh_token';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);

  // ───────────── API calls (không xử lý logic, caller tự quyết định) ─────────────

  login(data: LoginRequest): Observable<TokenResponse> {
    return this.http.post<TokenResponse>('/api/auth/login', data);
  }

  register(data: RegisterRequest): Observable<UserProfile> {
    return this.http.post<UserProfile>('/api/auth/register', data);
  }

  getProfile(): Observable<UserProfile> {
    return this.http.get<UserProfile>('/api/auth/me');
  }

  refresh(): Observable<TokenResponse> {
    const refresh_token = this.getRefreshToken();
    return this.http.post<TokenResponse>('/api/auth/refresh', { refresh_token });
  }

  logout(): Observable<unknown> {
    const refresh_token = this.getRefreshToken();
    return this.http.post('/api/auth/logout', { refresh_token });
  }

  // ───────────── Storage helpers (caller dùng để lưu/đọc/xoá token) ─────────────

  setSession(tokens: TokenResponse): void {
    localStorage.setItem(ACCESS_KEY, tokens.access_token);
    localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  }

  clearSession(): void {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem('user');
  }

  getAccessToken(): string | null { return localStorage.getItem(ACCESS_KEY); }
  getRefreshToken(): string | null { return localStorage.getItem(REFRESH_KEY); }
  getToken(): string | null { return this.getAccessToken(); }
  isAuthenticated(): boolean { return !!this.getAccessToken(); }
}
