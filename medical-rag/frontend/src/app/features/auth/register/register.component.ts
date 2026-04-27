// -*- coding: utf-8 -*-
import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
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

@Component({
  standalone: true,
  selector: 'app-register',
  templateUrl: './register.component.html',
  styleUrl: './register.component.scss',
  imports: [
    CommonModule, 
    ReactiveFormsModule, 
    RouterLink,
    ButtonModule, 
    InputTextModule, 
    PasswordModule,
    MessageModule, 
    ToastModule, 
    FluidModule,
  ],
  providers: [MessageService],
})
export class RegisterComponent {
  constructor(private router: Router,
    private messageService: MessageService,
    private authService: AuthService,
    private fb: FormBuilder,
  ) {}

  isLoading : boolean = false;
  errorMessage = '';

  form = this.fb.group({
    fullName:  ['', [Validators.required, Validators.minLength(2)]],
    email:     ['', [Validators.required, Validators.email]],
    nickname:  [''],
    password:  ['', [Validators.required, Validators.minLength(8)]],
  });

  onSubmit(): void {
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    this.isLoading = true;
    this.errorMessage = '';
    const { fullName, email, nickname, password } = this.form.value;
    const payload = { full_name: fullName!, email: email!, password: password!, nickname: nickname || null };
    this.authService.register(payload).subscribe({
      next: () => {
        this.messageService.add({
          severity: 'success',
          summary: 'Thành công',
          detail: 'Tài khoản đã được tạo!',
        });
        setTimeout(() => this.router.navigate(['/auth/login']), 1200);
      },
      error: (err) => {
        this.errorMessage = (
          err.status === 409 ? 'Email đã được sử dụng'
          : 'Đăng ký thất bại, thử lại sau'
        );
        this.isLoading = false;
      },
      complete: () => this.isLoading = false,
    });
  }

  isInvalid(field: string): boolean {
    const checkField = this.form.get(field);
    return !!(checkField?.invalid && checkField?.touched);
  }
}
