import { Component, signal, computed, inject, OnInit, DestroyRef } from '@angular/core';
import { Router } from '@angular/router';
import { Subject } from 'rxjs';
import { debounceTime, distinctUntilChanged } from 'rxjs/operators';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { DataViewModule } from 'primeng/dataview';
import { InputTextModule } from 'primeng/inputtext';
import { IconFieldModule } from 'primeng/iconfield';
import { InputIconModule } from 'primeng/inputicon';
import { ButtonModule } from 'primeng/button';
import { SkeletonModule } from 'primeng/skeleton';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { ToastModule } from 'primeng/toast';
import { ConfirmationService, MessageService } from 'primeng/api';
import { ApiService } from '../../core/services/api.service';
import { SessionSummary } from '../../core/models';
import { SessionCardComponent } from './components/session-card/session-card.component';

@Component({
  selector: 'app-history',
  standalone: true,
  imports: [
    DataViewModule, InputTextModule, IconFieldModule, InputIconModule,
    ButtonModule, SkeletonModule, ConfirmDialogModule, ToastModule,
    SessionCardComponent
  ],
  providers: [ConfirmationService, MessageService],
  templateUrl: './history.component.html'
})
export class HistoryComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly confirmationService = inject(ConfirmationService);
  private readonly messageService = inject(MessageService);
  private readonly destroyRef = inject(DestroyRef);

  private readonly searchSubject = new Subject<string>();

  readonly allSessions = signal<SessionSummary[]>([]);
  readonly isLoading = signal(true);
  readonly searchQuery = signal('');

  readonly filteredSessions = computed(() => {
    const q = this.searchQuery().toLowerCase().trim();
    if (!q) return this.allSessions();
    return this.allSessions().filter(s =>
      (s.title ?? '').toLowerCase().includes(q)
    );
  });

  readonly skeletonItems = [1, 2, 3, 4, 5];

  ngOnInit(): void {
    this.searchSubject.pipe(
      debounceTime(300),
      distinctUntilChanged(),
      takeUntilDestroyed(this.destroyRef)
    ).subscribe(q => this.searchQuery.set(q));

    this.loadSessions();
  }

  loadSessions(): void {
    this.isLoading.set(true);
    this.api.getHistory().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (paginated) => {
        this.allSessions.set(paginated.items);
        this.isLoading.set(false);
      },
      error: () => {
        this.messageService.add({
          severity: 'error', summary: 'Lỗi', detail: 'Không tải được lịch sử'
        });
        this.isLoading.set(false);
      }
    });
  }

  onSearch(event: Event): void {
    this.searchSubject.next((event.target as HTMLInputElement).value);
  }

  onView(sessionId: string): void {
    this.router.navigate(['/history', sessionId]);
  }

  onDelete(sessionId: string): void {
    this.confirmationService.confirm({
      message: 'Bạn có chắc muốn xóa cuộc hội thoại này không?',
      header: 'Xác nhận xóa',
      icon: 'pi pi-exclamation-triangle',
      acceptLabel: 'Xóa',
      rejectLabel: 'Hủy',
      acceptButtonStyleClass: 'p-button-danger',
      accept: () => {
        this.api.deleteSession(sessionId).subscribe({
          next: () => {
            this.allSessions.update(s => s.filter(x => x.id !== sessionId));
            this.messageService.add({
              severity: 'success', summary: 'Đã xóa', detail: 'Xóa thành công'
            });
          },
          error: () => {
            this.messageService.add({
              severity: 'error', summary: 'Lỗi', detail: 'Không thể xóa'
            });
          }
        });
      }
    });
  }
}
