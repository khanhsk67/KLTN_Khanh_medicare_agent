import { Component, signal, inject, OnInit, DestroyRef } from '@angular/core';
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
import { PaginatorModule, PaginatorState } from 'primeng/paginator';
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
    PaginatorModule, SessionCardComponent
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
  private searchResults: SessionSummary[] = [];

  readonly sessions = signal<SessionSummary[]>([]);
  readonly isLoading = signal(true);
  readonly searchQuery = signal('');

  readonly page = signal(1);
  readonly pageSize = signal(10);
  readonly total = signal(0);

  readonly rowsPerPageOptions = [5, 10, 20, 50];
  readonly skeletonItems = [1, 2, 3, 4, 5];

  get firstIndex(): number {
    return (this.page() - 1) * this.pageSize();
  }

  ngOnInit(): void {
    this.searchSubject.pipe(
      debounceTime(300),
      distinctUntilChanged(),
      takeUntilDestroyed(this.destroyRef)
    ).subscribe(q => {
      this.searchQuery.set(q);
      this.page.set(1);
      this.runSearchOrList();
    });

    this.runSearchOrList();
  }

  private runSearchOrList(): void {
    const q = this.searchQuery().trim();
    if (q) {
      this.loadSearch(q);
    } else {
      this.loadSessions();
    }
  }

  loadSessions(): void {
    this.isLoading.set(true);
    this.api.getHistory(this.page(), this.pageSize())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (paginated) => {
          this.sessions.set(paginated.items);
          this.total.set(paginated.total);
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

  private loadSearch(query: string): void {
    this.isLoading.set(true);
    this.api.searchHistory(query)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (results) => {
          this.searchResults = results;
          this.total.set(results.length);
          this.applySearchPage();
          this.isLoading.set(false);
        },
        error: () => {
          this.messageService.add({
            severity: 'error', summary: 'Lỗi', detail: 'Không tìm kiếm được'
          });
          this.isLoading.set(false);
        }
      });
  }

  private applySearchPage(): void {
    const start = this.firstIndex;
    this.sessions.set(this.searchResults.slice(start, start + this.pageSize()));
  }

  refresh(): void {
    this.runSearchOrList();
  }

  onSearch(event: Event): void {
    this.searchSubject.next((event.target as HTMLInputElement).value);
  }

  onPageChange(event: PaginatorState): void {
    this.page.set((event.page ?? 0) + 1);
    this.pageSize.set(event.rows ?? this.pageSize());
    if (this.searchQuery().trim()) {
      this.applySearchPage();
    } else {
      this.loadSessions();
    }
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
            this.messageService.add({
              severity: 'success', summary: 'Đã xóa', detail: 'Xóa thành công'
            });
            // Nếu đang ở trang cuối và xóa item cuối cùng, lùi về trang trước
            if (this.sessions().length === 1 && this.page() > 1) {
              this.page.update(p => p - 1);
            }
            this.runSearchOrList();
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
