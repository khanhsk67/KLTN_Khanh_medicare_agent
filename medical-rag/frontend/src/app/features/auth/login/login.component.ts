// -*- coding: utf-8 -*-
import { Component, inject, signal, effect } from '@angular/core';
import { CommonModule, DOCUMENT } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { PasswordModule } from 'primeng/password';
import { MessageModule } from 'primeng/message';
import { ToastModule } from 'primeng/toast';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  standalone: true,
  selector: 'app-login',
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
  imports: [
    CommonModule,
    ReactiveFormsModule,
    RouterLink,
    ButtonModule,
    InputTextModule,
    PasswordModule,
    MessageModule,
    ToastModule
  ],
  providers: [MessageService]
})
export class LoginComponent {
  private readonly document = inject(DOCUMENT);

  isLoading = false;
  errorMessage = '';

  readonly themeMode = signal<'light' | 'dark'>(
    (typeof localStorage !== 'undefined' && localStorage.getItem('medicare-theme') === 'dark') ? 'dark' : 'light'
  );

  form = this.fb.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(6)]]
  });

  constructor(
    private messageService: MessageService,
    private authService: AuthService,
    private router: Router,
    private fb: FormBuilder
  ) {
    effect(() => {
      const mode = this.themeMode();
      const body = this.document.body;
      if (mode === 'dark') body.classList.add('dark-mode');
      else body.classList.remove('dark-mode');
      try { localStorage.setItem('medicare-theme', mode); } catch {}
    });
  }

  toggleTheme(): void { this.themeMode.update(m => (m === 'light' ? 'dark' : 'light')); }

  onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.isLoading = true;
    this.errorMessage = '';

    const payload = this.form.value as { email: string; password: string };

    this.authService.login(payload).subscribe({
      next: (res) => {
        this.authService.setSession(res);
        this.authService.getProfile().subscribe({
          next: (profile) => {
            localStorage.setItem('user', JSON.stringify(profile));
            this.router.navigate(['/analysis']);
          }
        });
      },
      error: (err) => {
        this.errorMessage =
          err.status === 401
            ? 'Email hoặc mật khẩu không đúng'
            : 'Đăng nhập thất bại, thử lại sau';
        this.isLoading = false;
      },
      complete: () => (this.isLoading = false)
    });
  }

  isInvalid(field: string): boolean {
    const check = this.form.get(field);
    return !!(check?.invalid && check?.touched);
  }
}
