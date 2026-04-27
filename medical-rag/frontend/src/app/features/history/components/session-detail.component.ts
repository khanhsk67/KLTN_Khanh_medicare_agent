import { Component, inject, signal, OnInit } from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { ScrollPanelModule } from 'primeng/scrollpanel';
import { AvatarModule } from 'primeng/avatar';
import { ProgressSpinnerModule } from 'primeng/progressspinner';
import { SkeletonModule } from 'primeng/skeleton';
import { DividerModule } from 'primeng/divider';
import { MarkdownModule } from 'ngx-markdown';
import { ApiService } from '../../../core/services/api.service';
import { MessageItem, SessionSummary } from '../../../core/models';

@Component({
  selector: 'app-session-detail',
  standalone: true,
  imports: [
    ButtonModule, ScrollPanelModule, AvatarModule,
    ProgressSpinnerModule, SkeletonModule, DividerModule,
    MarkdownModule
  ],
  template: `
    <div class="flex flex-column gap-3 p-4">

      <!-- Header -->
      <div class="flex align-items-center gap-3">
        <p-button icon="pi pi-arrow-left" [text]="true"
                  (onClick)="router.navigate(['/history'])"/>
        <h2 class="m-0 text-xl font-bold flex-1">
          {{ session()?.title || 'Chi tiết tư vấn' }}
        </h2>
        <p-button label="Tiếp tục hội thoại"
                  icon="pi pi-comments"
                  size="small"
                  (onClick)="continueChat()"/>
      </div>

      <p-divider/>

      <!-- Loading -->
      @if (isLoading()) {
        <div class="flex flex-column gap-3">
          @for (i of [1,2,3]; track i) {
            <p-skeleton height="4rem" borderRadius="8px"/>
          }
        </div>
      }

      <!-- Messages read-only -->
      @if (!isLoading()) {
        <p-scrollpanel [style]="{ height: 'calc(100vh - 200px)' }">
          @if (messages().length === 0) {
            <div class="flex flex-column align-items-center justify-content-center gap-2 py-8">
              <i class="pi pi-comments text-color-secondary" style="font-size: 3rem"></i>
              <p class="text-color-secondary m-0">Không có tin nhắn</p>
            </div>
          }
          <div class="flex flex-column gap-3 p-2">
            @for (msg of messages(); track msg.id) {
              <div class="flex gap-2"
                   [class]="msg.role === 'user' ? 'justify-content-end' : 'justify-content-start'">
                @if (msg.role === 'assistant') {
                  <p-avatar icon="pi pi-heart" shape="circle"
                            [style]="{'background': 'var(--p-primary-color)', 'color': '#fff'}"/>
                }
                <div class="p-3 border-round-lg"
                     [class]="msg.role === 'user' ? 'bg-primary text-white' : 'surface-100'"
                     style="max-width: 70%">
                  @if (msg.role === 'assistant') {
                    <markdown [data]="msg.content"/>
                  } @else {
                    <p class="m-0 text-sm line-height-3">{{ msg.content }}</p>
                  }
                </div>
                @if (msg.role === 'user') {
                  <p-avatar icon="pi pi-user" shape="circle"/>
                }
              </div>
            }
          </div>
        </p-scrollpanel>
      }

    </div>
  `,
  styles: [`
    :host { display: block; }
    .bg-primary { background: var(--p-primary-color); }
  `]
})
export class SessionDetailComponent implements OnInit {
  router = inject(Router);
  private route = inject(ActivatedRoute);
  private api = inject(ApiService);

  session = signal<SessionSummary | null>(null);
  messages = signal<MessageItem[]>([]);
  isLoading = signal(true);

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) { this.isLoading.set(false); return; }

    this.api.getSessionDetail(id).subscribe({
      next: (data) => {
        this.session.set(data.session);
        this.messages.set(data.messages);
        this.isLoading.set(false);
      },
      error: () => this.isLoading.set(false)
    });
  }

  continueChat(): void {
    this.router.navigate(['/chat'], { queryParams: { session: this.session()?.id } });
  }
}
