import { Injectable, signal, computed, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { Observable, tap } from 'rxjs';
import {
  LoginRequest,
  RegisterRequest,
  TokenResponse,
  UserProfile
} from '../models';

@Injectable({ providedIn: 'root' })
export class AuthService {
   constructor(private http: HttpClient) {}

  login(data: LoginRequest): Observable<TokenResponse> {
    return this.http.post<TokenResponse>('/api/auth/login', data);
  }

  register(data: any): Observable<UserProfile> {
    return this.http.post<UserProfile>('/api/auth/register', data);
  }

  getProfile(): Observable<UserProfile> {
    return this.http.get<UserProfile>('/api/auth/me');
  }

  logout() {
    return this.http.post(`/api/auth/logout`, {});
  }

  getAccessToken(): string | null {
    return localStorage.getItem('access_token');
  }

  getToken(): string | null {
    return localStorage.getItem('access_token');
  }

  isAuthenticated(): boolean {
    return !!localStorage.getItem('access_token');
  }
}
