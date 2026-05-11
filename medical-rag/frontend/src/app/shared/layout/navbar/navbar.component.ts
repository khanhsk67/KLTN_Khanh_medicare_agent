import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { Router } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { MenubarModule } from 'primeng/menubar';
import { AuthService } from '../../../core/services/auth.service';
import { WalletWidgetComponent } from '../../components/wallet-widget.component';

@Component({
  selector: 'app-navbar',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, ButtonModule, MenubarModule, WalletWidgetComponent],
  templateUrl: './navbar.component.html',
  styleUrl: './navbar.component.scss'
})
export class NavbarComponent {
  readonly authService = inject(AuthService);
  private readonly router = inject(Router);

  logout(): void {
    // Dù API thành công hay fail (token đã revoke, server down...) đều phải clear local
    const goLogin = () => {
      this.authService.clearSession();
      this.router.navigate(['/auth/login']);
    };
    this.authService.logout().subscribe({ next: goLogin, error: goLogin });
  }
}
