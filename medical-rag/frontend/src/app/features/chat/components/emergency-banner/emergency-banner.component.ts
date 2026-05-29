import { Component, output } from '@angular/core';

@Component({
  selector: 'app-emergency-banner',
  standalone: true,
  imports: [],
  templateUrl: './emergency-banner.component.html',
  styleUrl: './emergency-banner.component.scss'
})
export class EmergencyBannerComponent {
  readonly dismissed = output<void>();
}
