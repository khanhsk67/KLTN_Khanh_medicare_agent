import { Component, inject, signal, computed, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { InputTextModule } from 'primeng/inputtext';
import { TooltipModule } from 'primeng/tooltip';
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
    InputTextModule, TooltipModule,
    SkeletonModule, ToastModule, MessageModule,
    RelativeTimePipe,
  ],
  providers: [MessageService],
  templateUrl: './wallet.component.html',
  styleUrl: './wallet.component.scss',
})
export class WalletComponent implements OnInit {
  wallet        = inject(WalletService);
  private toast = inject(MessageService);

  private readonly HISTORY_PAGE_SIZE = 10;

  isLoading    = signal(true);
  promoCode    = signal('');
  promoLoading = signal(false);
  promoError   = signal<string | null>(null);
  history      = signal<any[]>([]);
  historyDisplayCount = signal(this.HISTORY_PAGE_SIZE);

  // Demo promo suggestions
  readonly suggestedPromos = ['THESIS2026', 'WELCOME100', 'TESTDEMO'];

  // === Derived stats from history ===
  readonly totalEarned = computed(() =>
    this.history().reduce((sum, tx) => sum + (tx.points || 0), 0)
  );
  readonly checkinCount = computed(() =>
    this.history().filter(tx => tx.source === 'DAILY_CHECKIN').length
  );
  readonly promoCount = computed(() =>
    this.history().filter(tx => tx.source === 'PROMO_CODE').length
  );

  // === Pagination (load more pattern) ===
  readonly displayedHistory = computed(() =>
    this.history().slice(0, this.historyDisplayCount())
  );
  readonly remainingHistory = computed(() =>
    Math.max(0, this.history().length - this.historyDisplayCount())
  );

  loadMoreHistory(): void {
    this.historyDisplayCount.update(c => c + this.HISTORY_PAGE_SIZE);
  }

  ngOnInit() {
    this.wallet.loadBalance();
    this.wallet.loadCheckinStatus();
    this.loadHistory();
  }

  loadHistory() {
    this.isLoading.set(true);
    this.historyDisplayCount.set(this.HISTORY_PAGE_SIZE);
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

  applySuggested(code: string): void { this.promoCode.set(code); }

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

  getSourceCssClass(source: string): string {
    const map: Record<string, string> = {
      'DAILY_CHECKIN': 'checkin',
      'PROMO_CODE':    'promo',
      'ADMIN_BONUS':   'bonus',
      'PURCHASE':      'purchase',
    };
    return map[source] ?? 'default';
  }
}
