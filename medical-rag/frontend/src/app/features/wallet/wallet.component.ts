import { Component, inject, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { TagModule } from 'primeng/tag';
import { DividerModule } from 'primeng/divider';
import { SkeletonModule } from 'primeng/skeleton';
import { ToastModule } from 'primeng/toast';
import { MessageModule } from 'primeng/message';
import { MessageService } from 'primeng/api';
import { WalletService } from '../../core/services/wallet.service';
import { RelativeTimePipe } from '../../shared/pipes/relative-time.pipe';

@Component({
  standalone: true,
  selector: 'app-wallet',
  imports: [
    CommonModule, FormsModule,
    CardModule, ButtonModule, InputTextModule,
    TagModule, DividerModule, SkeletonModule,
    ToastModule, MessageModule,
    RelativeTimePipe,
  ],
  providers: [MessageService],
  templateUrl: './wallet.component.html',
})
export class WalletComponent implements OnInit {
  wallet        = inject(WalletService);
  private toast = inject(MessageService);

  isLoading    = signal(true);
  promoCode    = signal('');
  promoLoading = signal(false);
  promoError   = signal<string | null>(null);
  history      = signal<any[]>([]);

  ngOnInit() {
    this.wallet.loadBalance();
    this.wallet.loadCheckinStatus();
    this.loadHistory();
  }

  loadHistory() {
    this.isLoading.set(true);
    this.wallet.getTopupHistory().subscribe({
      next: data => {
        this.history.set(data);
        this.isLoading.set(false);
      },
      error: () => this.isLoading.set(false),
    });
  }

  doCheckin() {
    this.wallet.dailyCheckin().subscribe({
      next: res => {
        this.wallet.balance.set(res.balance);
        this.wallet.checkedToday.set(true);
        this.toast.add({
          severity: 'success',
          summary: 'Điểm danh thành công!',
          detail: res.message,
        });
        this.loadHistory();
      },
      error: err => this.toast.add({
        severity: 'warn',
        summary: 'Thông báo',
        detail: err.error?.detail || 'Đã điểm danh hôm nay rồi',
      }),
    });
  }

  redeemCode() {
    if (!this.promoCode().trim()) return;
    this.promoLoading.set(true);
    this.promoError.set(null);

    this.wallet.redeemCode(this.promoCode()).subscribe({
      next: res => {
        this.wallet.balance.set(res.balance);
        this.promoCode.set('');
        this.promoLoading.set(false);
        this.toast.add({
          severity: 'success',
          summary: 'Thành công!',
          detail: res.message,
        });
        this.loadHistory();
      },
      error: err => {
        this.promoError.set(err.error?.detail || 'Mã không hợp lệ');
        this.promoLoading.set(false);
      },
    });
  }

  getSourceLabel(source: string): string {
    const map: Record<string, string> = {
      'DAILY_CHECKIN': 'Điểm danh',
      'PROMO_CODE':    'Mã điểm',
      'ADMIN_BONUS':   'Thưởng',
      'PURCHASE':      'Nạp tiền',
    };
    return map[source] ?? source;
  }

  getSourceSeverity(source: string): 'success' | 'info' | 'warn' | 'danger' | 'secondary' | 'contrast' {
    const map: Record<string, 'success' | 'info' | 'warn' | 'danger' | 'secondary' | 'contrast'> = {
      'DAILY_CHECKIN': 'success',
      'PROMO_CODE':    'info',
      'ADMIN_BONUS':   'warn',
      'PURCHASE':      'contrast',
    };
    return map[source] ?? 'secondary';
  }
}
