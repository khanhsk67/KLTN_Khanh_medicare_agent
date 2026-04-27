import {
  Component, Input, ViewChild, ElementRef, AfterViewChecked
} from '@angular/core';
import { SlicePipe } from '@angular/common';
import { FlexLayoutModule } from '@ngbracket/ngx-layout';
import { AvatarModule } from 'primeng/avatar';
import { ProgressSpinnerModule } from 'primeng/progressspinner';
import { AccordionModule } from 'primeng/accordion';
import { TagModule } from 'primeng/tag';
import { MarkdownModule } from 'ngx-markdown';
import { MessageItem, SourceChunk } from '../../../core/models';

@Component({
  selector: 'app-chat-messages',
  standalone: true,
  imports: [
    SlicePipe,
    FlexLayoutModule,
    AvatarModule, ProgressSpinnerModule, AccordionModule, TagModule,
    MarkdownModule
  ],
  template: `
    <div #scrollContainer class="messages-container" style="flex: 1; overflow-y: auto; padding: 1.5rem">

      @if (messages.length === 0) {
        <div class="empty-state" fxLayout="column" fxLayoutAlign="center center" style="min-height: 60vh; gap: 1rem">
          <i class="pi pi-heart-fill text-5xl text-primary"></i>
          <h2 class="m-0">MedConsult AI</h2>
          <p class="text-500 text-center m-0">Mô tả triệu chứng của bạn để nhận tư vấn y tế</p>
        </div>
      }

      @for (msg of messages; track msg.id) {
        <div class="mb-4">

          @if (msg.role === 'user') {
            <div fxLayout="row" fxLayoutAlign="end start" fxLayoutGap="8px">
              <div class="user-bubble">
                @if (msg.image_url) {
                  <img [src]="msg.image_url"
                       alt="uploaded"
                       class="block mb-2 w-full"
                       style="max-height: 200px; border-radius: 0.5rem; object-fit: contain" />
                }
                {{ msg.content }}
              </div>
              <p-avatar icon="pi pi-user" shape="circle" />
            </div>
          }

          @if (msg.role === 'assistant') {
            <div fxLayout="row" fxLayoutAlign="start start" fxLayoutGap="8px">
              <p-avatar icon="pi pi-heart" shape="circle"
                        [style]="{'background': 'var(--p-primary-color)', 'color': '#fff'}" />
              <div class="assistant-bubble" [class.emergency]="msg.urgency_level === 'emergency'">
                <markdown [data]="msg.content" />

                @if (msg.sources && msg.sources.length > 0) {
                  <p-accordion class="mt-2">
                    <p-accordionpanel value="sources">
                      <p-accordionheader>
                        <i class="pi pi-book mr-2"></i>
                        Nguồn tài liệu y tế ({{ msg.sources.length }})
                      </p-accordionheader>
                      <p-accordioncontent>
                        @for (s of msg.sources; track $index) {
                          <div class="source-item">
                            <div fxLayout="row" fxLayoutAlign="space-between center" class="mb-1">
                              <span class="font-semibold text-sm">{{ s.source_file || s.source || 'Tài liệu y tế' }}</span>
                              <p-tag [value]="getScoreLabel(s)" [severity]="getScoreSeverity(s)" />
                            </div>
                            <p class="text-sm text-color-secondary m-0">
                              {{ s.content | slice:0:150 }}...
                            </p>
                          </div>
                        }
                      </p-accordioncontent>
                    </p-accordionpanel>
                  </p-accordion>
                }
              </div>
            </div>
          }

        </div>
      }

      @if (isLoading) {
        <div fxLayout="row" fxLayoutAlign="start center" fxLayoutGap="8px" class="mb-4">
          <p-avatar icon="pi pi-heart" shape="circle"
                    [style]="{'background': 'var(--p-primary-color)', 'color': '#fff'}" />
          <div class="assistant-bubble" fxLayout="row" fxLayoutAlign="start center" fxLayoutGap="8px">
            <p-progressspinner class="w-2rem h-2rem" strokeWidth="4" />
            <span class="text-color-secondary text-sm">Đang phân tích...</span>
          </div>
        </div>
      }

      <div #messagesEnd></div>
    </div>
  `,
  styles: [`
    :host {
      display: flex;
      flex-direction: column;
      flex: 1;
      overflow: hidden;
      min-height: 0;
    }

    .messages-container {
      display: flex;
      flex-direction: column;
    }

    .user-bubble {
      background: var(--p-primary-color);
      color: #fff;
      padding: 0.75rem 1rem;
      border-radius: 1rem 1rem 0 1rem;
      max-width: 70%;
      word-break: break-word;
    }

    .assistant-bubble {
      background: var(--p-surface-card);
      border: 1px solid var(--p-surface-border);
      padding: 0.75rem 1rem;
      border-radius: 1rem 1rem 1rem 0;
      max-width: 75%;
      word-break: break-word;
    }

    .assistant-bubble.emergency {
      border-color: #c62828;
      border-width: 2px;
    }

    .source-item {
      border-bottom: 1px solid var(--p-surface-border);
      padding: 0.5rem 0;
    }

    .source-item:last-child {
      border-bottom: none;
      padding-bottom: 0;
    }
  `]
})
export class ChatMessagesComponent implements AfterViewChecked {
  @Input() messages: MessageItem[] = [];
  @Input() isLoading = false;

  @ViewChild('messagesEnd') private messagesEnd!: ElementRef;

  private prevLength = 0;
  private prevLoading = false;

  ngAfterViewChecked(): void {
    const changed = this.messages.length !== this.prevLength || this.isLoading !== this.prevLoading;
    if (changed) {
      this.prevLength = this.messages.length;
      this.prevLoading = this.isLoading;
      this.scrollToBottom();
    }
  }

  getScoreLabel(s: SourceChunk): string {
    const score = (s.relevance_score ?? s.score ?? 0) * 100;
    return score.toFixed(0) + '%';
  }

  getScoreSeverity(s: SourceChunk): 'success' | 'warn' | 'danger' {
    const score = s.relevance_score ?? s.score ?? 0;
    if (score >= 0.8) return 'success';
    if (score >= 0.65) return 'warn';
    return 'danger';
  }

  private scrollToBottom(): void {
    setTimeout(() => {
      this.messagesEnd?.nativeElement?.scrollIntoView({ behavior: 'smooth' });
    }, 50);
  }
}
