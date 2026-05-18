import { Component, Input, Output, EventEmitter, signal, inject, NgZone } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { Textarea } from 'primeng/textarea';
import { TooltipModule } from 'primeng/tooltip';

interface SelectedImage {
  file: File;
  preview: string;   // full data URL (cho <img [src])
  base64: string;    // chỉ phần base64 (gửi BE)
  name: string;
}

const MAX_IMAGES = 8;

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
  @Output() messageSent = new EventEmitter<{
    text: string;
    imagesBase64: string[];
    imagePreviews: string[];
  }>();

  messageText = '';
  readonly selectedImages = signal<SelectedImage[]>([]);
  readonly maxImages = MAX_IMAGES;

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const files = input.files ? Array.from(input.files) : [];
    if (files.length === 0) return;

    const currentCount = this.selectedImages().length;
    const remainingSlots = MAX_IMAGES - currentCount;
    const accepted = files.slice(0, remainingSlots);

    accepted.forEach(file => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const dataUrl = e.target?.result as string;
        this.ngZone.run(() => {
          this.selectedImages.update(list => [
            ...list,
            {
              file,
              preview: dataUrl,
              base64: dataUrl.split(',')[1],
              name: file.name,
            }
          ]);
        });
      };
      reader.readAsDataURL(file);
    });

    input.value = '';
  }

  removeImage(index: number): void {
    this.selectedImages.update(list => list.filter((_, i) => i !== index));
  }

  clearImages(): void {
    this.selectedImages.set([]);
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

    const imgs = this.selectedImages();
    this.messageSent.emit({
      text,
      imagesBase64: imgs.map(i => i.base64),
      imagePreviews: imgs.map(i => i.preview),
    });
    this.messageText = '';
    this.selectedImages.set([]);
  }
}
