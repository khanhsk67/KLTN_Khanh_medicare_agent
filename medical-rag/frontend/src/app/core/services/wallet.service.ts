import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';

@Injectable({ providedIn: 'root' })
export class WalletService {
  private http = inject(HttpClient);

  // Signal toàn cục — chia sẻ state realtime qua mọi component
  balance      = signal<number>(0);
  checkedToday = signal<boolean>(false);

  loadBalance() {
    this.http.get<{ balance: number }>('/api/wallet').subscribe({
      next: res => this.balance.set(res.balance),
      error: () => {}
    });
  }

  loadCheckinStatus() {
    this.http.get<{ checked_today: boolean }>('/api/checkin/status').subscribe({
      next: res => this.checkedToday.set(res.checked_today),
      error: () => {}
    });
  }

  dailyCheckin() {
    return this.http.post<{
      rewarded_points: number;
      balance: number;
      message: string;
    }>('/api/checkin/daily', {});
  }

  redeemCode(code: string) {
    return this.http.post<{
      points_received: number;
      balance: number;
      message: string;
    }>('/api/promo-codes/redeem', { code });
  }

  getTopupHistory() {
    return this.http.get<any[]>('/api/wallet/topup-history');
  }
}
