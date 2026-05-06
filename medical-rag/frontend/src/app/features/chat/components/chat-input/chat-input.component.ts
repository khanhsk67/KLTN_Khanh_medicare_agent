import { Component, Input, Output, EventEmitter, signal, inject, NgZone } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { Textarea } from 'primeng/textarea';
import { TooltipModule } from 'primeng/tooltip';

@Component({
  selector: 'app-chat-input',
  standalone: true,
  imports: [FormsModule, ButtonModule, Textarea, TooltipModule],
  templateUrl: './chat-input.component.html',
  styleUrl: './chat-input.component.scss'
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
