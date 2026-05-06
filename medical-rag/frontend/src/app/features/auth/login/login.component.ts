// -*- coding: utf-8 -*-
import { Component, inject, signal } from '@angular/core';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { PasswordModule } from 'primeng/password';
import { MessageModule } from 'primeng/message';
import { ToastModule } from 'primeng/toast';
import { FluidModule } from 'primeng/fluid';
import { AuthService } from '../../../core/services/auth.service';
import { CommonModule } from '@angular/common';

@Component({
  standalone: true,
  selector: 'app-login',
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
  imports: [
    ReactiveFormsModule, 
    RouterLink,
    ButtonModule, 
    InputTextModule, 
    PasswordModule,
    MessageModule, 
    ToastModule, 
    FluidModule,
    CommonModule,
  ],
  providers: [MessageService],
})
export class LoginComponent {

  constructor(
    private messageService: MessageService,
    private authService: AuthService,
    private router: Router,
    private fb: FormBuilder,
  ) {}

  isLoading = false;
  errorMessage = '';

  form = this.fb.group({
    email:    ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(6)]],
  });

  onSubmit(): void {
    if (this.form.invalid) { 
      this.form.markAllAsTouched(); 
      return; 
    }
    this.isLoading = true;
    this.errorMessage = '';

    const payload = this.form.value as { email: string; password: string };
    // const { email, password } = this.form.value as { email: string; password: string };
    // AuthService.login() gọi POST /api/auth/login, lưu token vào localStorage
    // và cập nhật _token signal — cần thiết để authGuard hoạt động đúng
    
    this.authService.login(payload).subscribe({
      next: (res) => {
        // console.log("nè", payload);
        
        
        localStorage.setItem('access_token', res.access_token);
        this.authService.getProfile().subscribe({
          next:(profile) => {
            localStorage.setItem('user', JSON.stringify(profile));
            this.router.navigate(['/analysis']);
          },
        });
      },
      error: (err) => {
        this.errorMessage = (
          err.status === 401
            ? 'Email hoặc mật khẩu không đúng'
            : 'Đăng nhập thất bại, thử lại sau'
        );
        this.isLoading = false;
      },
      complete: () => this.isLoading = false,
    });
  }

  isInvalid(field: string): boolean {
    const check = this.form.get(field);
    // console.log(check);
    
    return !!(check?.invalid && check?.touched);
  }
}
