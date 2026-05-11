import { inject } from '@angular/core';
import {
  HttpInterceptorFn,
  HttpErrorResponse,
  HttpRequest,
  HttpHandlerFn,
} from '@angular/common/http';
import { Router } from '@angular/router';
import { BehaviorSubject, catchError, filter, switchMap, take, throwError } from 'rxjs';
import { AuthService } from '../services/auth.service';

// Trạng thái refresh dùng chung giữa các request concurrent
let isRefreshing = false;
const refreshedToken$ = new BehaviorSubject<string | null>(null);

// Các endpoint không cần Authorization và KHÔNG nên trigger auto-refresh
const SKIP_URLS = ['/api/auth/login', '/api/auth/register', '/api/auth/refresh'];

function addAuthHeader(req: HttpRequest<unknown>, token: string) {
  return req.clone({
    headers: req.headers.set('Authorization', `Bearer ${token}`),
  });
}

export const jwtInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (SKIP_URLS.some(url => req.url.includes(url))) {
    return next(req);
  }

  const token = auth.getAccessToken();
  const authReq = token ? addAuthHeader(req, token) : req;

  return next(authReq).pipe(
    catchError((err: HttpErrorResponse) => {
      if (err.status !== 401 || !auth.getRefreshToken()) {
        return throwError(() => err);
      }
      return handle401(authReq, next, auth, router);
    }),
  );
};

function handle401(
  req: HttpRequest<unknown>,
  next: HttpHandlerFn,
  auth: AuthService,
  router: Router,
) {
  // Đang có request khác refresh — đợi token mới rồi retry request này
  if (isRefreshing) {
    return refreshedToken$.pipe(
      filter((t): t is string => t !== null),
      take(1),
      switchMap(newToken => next(addAuthHeader(req, newToken))),
    );
  }

  isRefreshing = true;
  refreshedToken$.next(null);

  return auth.refresh().pipe(
    switchMap(res => {
      // Caller (interceptor) tự lưu token mới
      auth.setSession(res);
      isRefreshing = false;
      refreshedToken$.next(res.access_token);
      return next(addAuthHeader(req, res.access_token));
    }),
    catchError(err => {
      // Refresh fail → caller tự clear & điều hướng
      isRefreshing = false;
      auth.clearSession();
      router.navigate(['/auth/login']);
      return throwError(() => err);
    }),
  );
}
