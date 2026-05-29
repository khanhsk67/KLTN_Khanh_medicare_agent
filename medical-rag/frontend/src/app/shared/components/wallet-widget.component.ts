import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { TooltipModule } from 'primeng/tooltip';
import { BadgeModule } from 'primeng/badge';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { WalletService } from '../../core/services/wallet.service';

@Component({
  standalone: true,
  selector: 'app-wallet-widget',
  imports: [CommonModule, RouterLink, TooltipModule, BadgeModule, ToastModule],
  providers: [MessageService],
  templateUrl: './wallet-widget.component.html',
  styleUrl: './wallet-widget.component.scss'
})
export class WalletWidgetComponent implements OnInit {
  wallet        = inject(WalletService);
  private toast = inject(MessageService);

  isCheckinLoading = false;

  ngOnInit() {
    this.wallet.loadBalance();
    this.wallet.loadCheckinStatus();
  }

  doCheckin(event?: Event) {
    // Prevent click from bubbling to the parent <a routerLink="/wallet">
    event?.preventDefault();
    event?.stopPropagation();
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
