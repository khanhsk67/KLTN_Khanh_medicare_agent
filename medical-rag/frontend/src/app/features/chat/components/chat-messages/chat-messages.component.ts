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
import { MessageItem, SourceChunk } from '../../../../core/models';

@Component({
  selector: 'app-chat-messages',
  standalone: true,
  imports: [
    SlicePipe,
    FlexLayoutModule,
    AvatarModule, ProgressSpinnerModule, AccordionModule, TagModule,
    MarkdownModule
  ],
  templateUrl: './chat-messages.component.html',
  styleUrl: './chat-messages.component.scss'
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
