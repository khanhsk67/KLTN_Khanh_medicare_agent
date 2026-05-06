import { Component, input, output } from '@angular/core';
import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { TagModule } from 'primeng/tag';
import { TooltipModule } from 'primeng/tooltip';
import { RelativeTimePipe } from '../../../../shared/pipes/relative-time.pipe';
import { SessionSummary } from '../../../../core/models';

@Component({
  selector: 'app-session-card',
  standalone: true,
  imports: [CardModule, ButtonModule, TagModule, TooltipModule, RelativeTimePipe],
  templateUrl: './session-card.component.html',
  styleUrl: './session-card.component.scss'
})
export class SessionCardComponent {
  session = input.required<SessionSummary>();
  viewRequested = output<string>();
  deleteRequested = output<string>();
}
