import { Component, inject, signal, computed, effect } from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { MenuModule } from 'primeng/menu';
import { MenuItem } from 'primeng/api';
import { AuthService } from '../../../core/services/auth.service';
import { WalletWidgetComponent } from '../../components/wallet-widget.component';

@Component({
  selector: 'app-navbar',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, ButtonModule, MenuModule, WalletWidgetComponent],
  templateUrl: './navbar.component.html',
  styleUrl: './navbar.component.scss'
})
export class NavbarComponent {
  readonly authService = inject(AuthService);
  private readonly router = inject(Router);
  private readonly document = inject(DOCUMENT);

  readonly user = signal<{ full_name?: string; email?: string; nickname?: string } | null>(
    (() => {
      try { return JSON.parse(localStorage.getItem('user') || 'null'); } catch { return null; }
    })()
  );

  readonly userInitials = computed(() => {
    const u = this.user();
    if (!u) return '?';
    const name = (u.full_name || u.nickname || u.email || '').trim();
    if (!name) return '?';
    const parts = name.split(/\s+/);
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    return name.substring(0, 2).toUpperCase();
  });

  readonly themeMode = signal<'light' | 'dark'>(
    (typeof localStorage !== 'undefined' && localStorage.getItem('medicare-theme') === 'dark') ? 'dark' : 'light'
  );

  readonly userMenuItems: MenuItem[] = [
    {
      label: this.user()?.full_name || this.user()?.email || 'Tài khoản',
      icon: 'pi pi-user',
      disabled: true
    },
    { separator: true },
    {
      label: 'Đăng xuất',
      icon: 'pi pi-sign-out',
      command: () => this.logout()
    }
  ];

  constructor() {
    effect(() => {
      const mode = this.themeMode();
      const body = this.document.body;
      if (mode === 'dark') body.classList.add('dark-mode');
      else body.classList.remove('dark-mode');
      try { localStorage.setItem('medicare-theme', mode); } catch {}
    });
  }

  toggleTheme(): void { this.themeMode.update(m => (m === 'light' ? 'dark' : 'light')); }

  logout(): void {
    const goLogin = () => {
      this.authService.clearSession();
      this.router.navigate(['/auth/login']);
    };
    this.authService.logout().subscribe({ next: goLogin, error: goLogin });
  }
}
