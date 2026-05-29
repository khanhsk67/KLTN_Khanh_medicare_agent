import { Component, inject, signal, OnInit } from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';
import { AvatarModule } from 'primeng/avatar';
import { SkeletonModule } from 'primeng/skeleton';
import { MarkdownModule } from 'ngx-markdown';
import { ApiService } from '../../../../core/services/api.service';
import { MessageItem, SessionSummary } from '../../../../core/models';

@Component({
  selector: 'app-session-detail',
  standalone: true,
  imports: [
    AvatarModule, SkeletonModule, MarkdownModule
  ],
  templateUrl: './session-detail.component.html',
  styleUrl: './session-detail.component.scss'
})
export class SessionDetailComponent implements OnInit {
  router = inject(Router);
  private route = inject(ActivatedRoute);
  private api = inject(ApiService);

  session = signal<SessionSummary | null>(null);
  messages = signal<MessageItem[]>([]);
  isLoading = signal(true);

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) { this.isLoading.set(false); return; }

    this.api.getSessionDetail(id).subscribe({
      next: (data) => {
        this.session.set(data.session);
        this.messages.set(data.messages);
        this.isLoading.set(false);
      },
      error: () => this.isLoading.set(false)
    });
  }

  continueChat(): void {
    this.router.navigate(['/chat'], { queryParams: { session: this.session()?.id } });
  }
}
