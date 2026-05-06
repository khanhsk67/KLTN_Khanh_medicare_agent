import { Component, output } from '@angular/core';
import { FlexLayoutModule } from '@ngbracket/ngx-layout';
import { ButtonModule } from 'primeng/button';

@Component({
  selector: 'app-emergency-banner',
  standalone: true,
  imports: [FlexLayoutModule, ButtonModule],
  templateUrl: './emergency-banner.component.html',
  styleUrl: './emergency-banner.component.scss'
})
export class EmergencyBannerComponent {
  readonly dismissed = output<void>();
}
