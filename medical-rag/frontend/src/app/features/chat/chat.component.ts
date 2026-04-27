import { Component, signal, inject, OnInit, computed, NgZone } from '@angular/core';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { ChatService } from '../../core/services/chat.service';
import { AuthService } from '../../core/services/auth.service';
import { MessageItem, ChatSession } from '../../core/models';
import { ChatMessagesComponent } from './components/chat-messages.component';
import { ChatInputComponent } from './components/chat-input.component';
import { EmergencyBannerComponent } from './components/emergency-banner.component';
import { WalletService } from '../../core/services/wallet.service';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [
    RouterLink,
    RouterLinkActive,
    ToastModule,
    ChatMessagesComponent,
    ChatInputComponent,
    EmergencyBannerComponent
  ],
  providers: [MessageService],
  templateUrl: './chat.component.html',
  styleUrl: './chat.component.scss'
})
export class ChatComponent implements OnInit {

  constructor(private router: Router
    
  ) {}
  private readonly chatService = inject(ChatService);
  private readonly messageService = inject(MessageService);
  private readonly authService = inject(AuthService);
  private readonly ngZone = inject(NgZone);
  private readonly walletService = inject(WalletService);

  readonly messages = signal<MessageItem[]>([]);
  readonly isLoading = signal(false);
  readonly sessionId = signal<string | undefined>(undefined);
  readonly isEmergency = signal(false);
  readonly sidebarOpen = signal(true);
  readonly sessions = signal<ChatSession[]>([]);

  readonly hasMessages = computed(() => this.messages().length > 0);

  ngOnInit(): void {
    this.loadSessions();
  }

  loadSessions(): void {
    this.chatService.getSessions().subscribe({
      next: (s) => this.sessions.set(s),
      error: () => {}
    });
  }

  toggleSidebar(): void {
    this.sidebarOpen.update(v => !v);
  }

  newChat(): void {
    this.messages.set([]);
    this.sessionId.set(undefined);
    this.isEmergency.set(false);
  }

  loadSession(sessionId: string): void {
    if (this.isLoading()) return;
    this.sessionId.set(sessionId);
    this.isLoading.set(true);
    this.chatService.getMessages(sessionId).subscribe({
      next: (msgs) => {
        this.messages.set(msgs);
        this.isLoading.set(false);
      },
      error: () => this.isLoading.set(false)
    });
  }

  logout(): void {
    // this.authService.logout();
    this.authService.logout().subscribe({
      next: () => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
        this.router.navigate(['/auth/login']);
      },
    });
  }


  onMessageSent(payload: { text: string; imageBase64?: string; imagePreview?: string }): void {
    const { text, imageBase64, imagePreview } = payload;
    if (!text || this.isLoading()) return;

    const userMsg: MessageItem = {
      id: crypto.randomUUID(),
      session_id: this.sessionId() ?? '',
      role: 'user',
      content: text,
      image_url: imagePreview ?? imageBase64,
      created_at: new Date().toISOString()
    };
    this.messages.update(msgs => [...msgs, userMsg]);
    this.isLoading.set(true);

    const assistantMsg: MessageItem = {
      id: crypto.randomUUID(),
      session_id: this.sessionId() ?? '',
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString()
    };
    this.messages.update(msgs => [...msgs, assistantMsg]);

    // Chạy stream ngoài zone: zone không block onMicrotaskEmpty,
    // CD kích hoạt ngay sau khi handler synchronous này return.
    this.ngZone.runOutsideAngular(() => {
      this.runStream(text, imageBase64);
    });
  }

  private async runStream(text: string, imageBase64?: string): Promise<void> {
    try {
      const stream = this.chatService.streamChat(this.sessionId(), text, imageBase64);
      for await (const raw of stream) {
        let event: { type: string; content?: string; session_id?: string; urgency_level?: string; sources?: unknown[]; balance_remaining?: number; points_charged?: number };
        try {
          event = JSON.parse(raw);
        } catch {
          continue;
        }

        if (event.type === 'token' && event.content) {
          this.ngZone.run(() => {
            this.messages.update(msgs => {
              const updated = [...msgs];
              const last = updated[updated.length - 1];
              updated[updated.length - 1] = { ...last, content: last.content + event.content };
              return updated;
            });
          });
        } else if (event.type === 'done') {
          this.ngZone.run(() => {
            if (event.session_id) this.sessionId.set(event.session_id);

            if (event.urgency_level === 'emergency' || event.urgency_level === 'warning') {
              this.isEmergency.set(true);
            }

            if (event.sources || event.urgency_level) {
              this.messages.update(msgs => {
                const updated = [...msgs];
                updated[updated.length - 1] = {
                  ...updated[updated.length - 1],
                  urgency_level: event.urgency_level as MessageItem['urgency_level'],
                  sources: event.sources as MessageItem['sources']
                };
                return updated;
              });
            }

            // Cập nhật số dư ví ngay sau khi chat hoàn thành
            if (event.balance_remaining !== undefined) {
              this.walletService.balance.set(event.balance_remaining);
            }

            this.loadSessions();
          });
        } else if (event.type === 'error') {
          this.ngZone.run(() => {
            this.messageService.add({
              severity: 'error',
              summary: 'Lỗi',
              detail: event.content ?? 'Có lỗi xảy ra, vui lòng thử lại.'
            });
            this.messages.update(msgs => msgs.slice(0, -1));
          });
          break;
        }
      }
    } catch {
      this.ngZone.run(() => {
        this.messageService.add({
          severity: 'error',
          summary: 'Lỗi kết nối',
          detail: 'Không thể kết nối tới server. Vui lòng thử lại.'
        });
        this.messages.update(msgs => msgs.slice(0, -1));
      });
    } finally {
      this.ngZone.run(() => this.isLoading.set(false));
    }
  }
}
