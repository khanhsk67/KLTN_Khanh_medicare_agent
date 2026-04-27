import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  {
    path: '',
    redirectTo: '/auth/register',
    pathMatch: 'full'
  },
  {
    path: 'auth',
    loadChildren: () =>
      import('./features/auth/auth.routes').then(m => m.authRoutes)
  },
  {
    path: 'login',
    redirectTo: '/auth/login',
    pathMatch: 'full'
  },
  {
    path: 'register',
    redirectTo: '/auth/register',
    pathMatch: 'full'
  },
  {
    path: 'chat',
    loadComponent: () =>
      import('./features/chat/chat.component').then(m => m.ChatComponent),
    canActivate: [authGuard]
  },
  {
    path: 'history',
    loadComponent: () =>
      import('./features/history/history.component').then(m => m.HistoryComponent),
    canActivate: [authGuard]
  },
  {
    path: 'history/:id',
    loadComponent: () =>
      import('./features/history/components/session-detail.component')
        .then(m => m.SessionDetailComponent),
    canActivate: [authGuard]
  },
  {
    path: 'analysis',
    loadComponent: () =>
      import('./features/analysis/analysis.component').then(m => m.AnalysisComponent),
    canActivate: [authGuard]
  },
  {
    path: 'wallet',
    loadComponent: () =>
      import('./features/wallet/wallet.component').then(m => m.WalletComponent),
    canActivate: [authGuard],
  },
  {
    path: '**',
    redirectTo: '/auth/register'
  }
];
