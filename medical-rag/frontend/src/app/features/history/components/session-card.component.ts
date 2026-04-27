import { Component, input, output } from '@angular/core';
import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { TagModule } from 'primeng/tag';
import { TooltipModule } from 'primeng/tooltip';
import { RelativeTimePipe } from '../../../shared/pipes/relative-time.pipe';
import { SessionSummary } from '../../../core/models';

@Component({
  selector: 'app-session-card',
  standalone: true,
  imports: [CardModule, ButtonModule, TagModule, TooltipModule, RelativeTimePipe],
  template: `
    <p-card styleClass="mb-2 cursor-pointer hover:surface-hover
                        transition-colors transition-duration-200">
      <div class="flex align-items-center justify-content-between gap-3">

        <!-- Info -->
        <div class="flex flex-column gap-1 flex-1" style="min-width: 0"
             (click)="viewRequested.emit(session().id)">
          <span class="font-semibold text-overflow-ellipsis overflow-hidden white-space-nowrap">
            {{ session().title || 'Cuộc tư vấn' }}
          </span>
          <span class="text-color-secondary text-sm">
            {{ session().created_at | relativeTime }}
          </span>
          <span class="text-sm text-color-secondary">
            <i class="pi pi-comments mr-1"></i>
            {{ session().message_count ?? 0 }} tin nhắn
          </span>
        </div>

        <!-- Actions -->
        <div class="flex align-items-center gap-1" style="flex-shrink: 0">
          <p-button icon="pi pi-eye" [text]="true" [rounded]="true" severity="info"
                    pTooltip="Xem chi tiết" tooltipPosition="top"
                    (onClick)="viewRequested.emit(session().id)"/>
          <p-button icon="pi pi-trash" [text]="true" [rounded]="true" severity="danger"
                    pTooltip="Xóa" tooltipPosition="top"
                    (onClick)="deleteRequested.emit(session().id)"/>
        </div>

      </div>
    </p-card>
  `,
  styles: [':host { display: block; }']
})
export class SessionCardComponent {
  session = input.required<SessionSummary>();
  viewRequested = output<string>();
  deleteRequested = output<string>();
}
