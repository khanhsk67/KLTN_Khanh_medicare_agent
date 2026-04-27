import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ButtonModule } from 'primeng/button';
import { TooltipModule } from 'primeng/tooltip';
import { BadgeModule } from 'primeng/badge';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { WalletService } from '../../core/services/wallet.service';

@Component({
  standalone: true,
  selector: 'app-wallet-widget',
  imports: [CommonModule, ButtonModule, TooltipModule, BadgeModule, ToastModule],
  providers: [MessageService],
  template: `
    <p-toast position="top-right"/>

    <div class="flex align-items-center gap-2">
      <!-- Số dư -->
      <div class="flex align-items-center gap-1 surface-100
                  border-round-lg px-3 py-2">
        <i class="pi pi-wallet text-primary"></i>
        <span class="font-semibold text-sm">
          {{ wallet.balance() }} điểm
        </span>
      </div>

      <!-- Nút điểm danh -->
      @if (!wallet.checkedToday()) {
        <p-button
          label="+50đ"
          icon="pi pi-star"
          size="small"
          severity="success"
          pTooltip="Điểm danh nhận 50 điểm"
          [loading]="isCheckinLoading"
          (onClick)="doCheckin()"/>
      } @else {
        <p-button
          icon="pi pi-check-circle"
          size="small"
          [text]="true"
          severity="success"
          pTooltip="Đã điểm danh hôm nay"
          [disabled]="true"/>
      }
    </div>
  `,
})
export class WalletWidgetComponent implements OnInit {
  wallet        = inject(WalletService);
  private toast = inject(MessageService);

  isCheckinLoading = false;

  ngOnInit() {
    this.wallet.loadBalance();
    this.wallet.loadCheckinStatus();
  }

  doCheckin() {
    this.isCheckinLoading = true;
    this.wallet.dailyCheckin().subscribe({
      next: res => {
        this.wallet.balance.set(res.balance);
        this.wallet.checkedToday.set(true);
        this.toast.add({
          severity: 'success',
          summary: 'Điểm danh thành công!',
          detail: res.message,
        });
        this.isCheckinLoading = false;
      },
      error: err => {
        this.toast.add({
          severity: 'warn',
          summary: 'Thông báo',
          detail: err.error?.detail || 'Đã điểm danh hôm nay rồi',
        });
        this.isCheckinLoading = false;
      },
    });
  }
}
