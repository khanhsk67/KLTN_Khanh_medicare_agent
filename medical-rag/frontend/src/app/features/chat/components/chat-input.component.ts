import { Component, Input, Output, EventEmitter, signal, inject, NgZone } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { Textarea } from 'primeng/textarea';
import { TooltipModule } from 'primeng/tooltip';

@Component({
  selector: 'app-chat-input',
  standalone: true,
  imports: [FormsModule, ButtonModule, Textarea, TooltipModule],
  template: `
    <div class="chat-input-wrapper" [class.chat-input-wrapper--centered]="centered">

      <!-- Image preview -->
      @if (selectedImage()) {
        <div class="image-preview">
          <img [src]="selectedImage()!.preview" width="60" height="60"
               style="object-fit:cover;border-radius:8px;flex-shrink:0" />
          <span class="image-name">{{ selectedImage()!.name }}</span>
          <button type="button" class="remove-img-btn" (click)="removeImage()" title="Xóa ảnh">
            <i class="pi pi-times"></i>
          </button>
        </div>
      }

      <div class="input-row">
        <!-- Hidden file input -->
        <input #fileInput type="file" accept="image/*"
               (change)="onFileSelected($event)"
               style="display:none" />

        <!-- Attach image button -->
        <button type="button" class="action-btn"
                pTooltip="Đính kèm ảnh" tooltipPosition="top"
                [disabled]="disabled"
                (click)="fileInput.click()">
          <i class="pi pi-image"></i>
        </button>

        <!-- Textarea -->
        <textarea pInputTextarea class="msg-textarea"
                  [(ngModel)]="messageText"
                  [autoResize]="true"
                  rows="1"
                  placeholder="Mô tả triệu chứng... (Enter gửi, Shift+Enter xuống dòng)"
                  [disabled]="disabled"
                  (keydown)="onKeydown($event)"
                  style="resize:none"></textarea>

        <!-- Send button -->
        <button type="button" class="send-btn"
                [disabled]="disabled || !messageText.trim()"
                (click)="send()"
                pTooltip="Gửi" tooltipPosition="top">
          <i class="pi pi-send"></i>
        </button>
      </div>
    </div>
  `,
  styles: [`
    .chat-input-wrapper {
      padding: 0.75rem 1rem;
      background: #fff;
    }

    .chat-input-wrapper--centered {
      border: 1px solid #e5e7eb;
      border-radius: 1rem;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
      padding: 0.625rem 0.875rem;
    }

    .image-preview {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 8px;
      padding-bottom: 8px;
      border-bottom: 1px solid #f3f4f6;
    }

    .image-name {
      font-size: 0.8rem;
      color: #6b7280;
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .remove-img-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 28px;
      height: 28px;
      border: none;
      border-radius: 50%;
      background: transparent;
      color: #ef4444;
      cursor: pointer;
      font-size: 0.75rem;
      flex-shrink: 0;
    }

    .remove-img-btn:hover {
      background: #fee2e2;
    }

    .input-row {
      display: flex;
      align-items: flex-end;
      gap: 8px;
    }

    .action-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 36px;
      height: 36px;
      border: none;
      border-radius: 0.5rem;
      background: transparent;
      color: #6b7280;
      cursor: pointer;
      font-size: 1rem;
      flex-shrink: 0;
      transition: background 0.15s, color 0.15s;
    }

    .action-btn:hover:not([disabled]) {
      background: #f3f4f6;
      color: #374151;
    }

    .action-btn[disabled] {
      opacity: 0.4;
      cursor: not-allowed;
    }

    .msg-textarea {
      flex: 1;
      border: none !important;
      outline: none !important;
      box-shadow: none !important;
      background: transparent !important;
      font-size: 0.9375rem;
      line-height: 1.5;
      padding: 0.375rem 0 !important;
      max-height: 200px;
      overflow-y: auto;
    }

    .send-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 36px;
      height: 36px;
      border: none;
      border-radius: 50%;
      background: #111827;
      color: #fff;
      cursor: pointer;
      font-size: 0.875rem;
      flex-shrink: 0;
      transition: background 0.15s, opacity 0.15s;
    }

    .send-btn:hover:not([disabled]) {
      background: #374151;
    }

    .send-btn[disabled] {
      opacity: 0.35;
      cursor: not-allowed;
    }
  `]
})
export class ChatInputComponent {
  private readonly ngZone = inject(NgZone);

  @Input() disabled = false;
  @Input() centered = false;
  @Output() messageSent = new EventEmitter<{ text: string; imageBase64?: string; imagePreview?: string }>();

  messageText = '';
  readonly selectedImage = signal<{
    file: File; preview: string; base64: string; name: string
  } | null>(null);

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      const dataUrl = e.target?.result as string;
      this.ngZone.run(() => {
        this.selectedImage.set({
          file,
          preview: dataUrl,
          base64: dataUrl.split(',')[1],
          name: file.name
        });
      });
    };
    reader.readAsDataURL(file);
    input.value = '';
  }

  removeImage(): void {
    this.selectedImage.set(null);
  }

  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.send();
    }
  }

  send(): void {
    const text = this.messageText.trim();
    if (!text || this.disabled) return;

    this.messageSent.emit({
      text,
      imageBase64: this.selectedImage()?.base64,
      imagePreview: this.selectedImage()?.preview
    });
    this.messageText = '';
    this.selectedImage.set(null);
  }
}
