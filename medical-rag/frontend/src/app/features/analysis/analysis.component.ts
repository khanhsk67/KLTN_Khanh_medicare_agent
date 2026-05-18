import { Component, signal, computed, effect, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { forkJoin, of } from 'rxjs';
import { catchError, filter } from 'rxjs/operators';
import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { ChartModule } from 'primeng/chart';
import { TimelineModule } from 'primeng/timeline';
import { SelectButtonModule } from 'primeng/selectbutton';
import { ProgressSpinnerModule } from 'primeng/progressspinner';
import { ChipModule } from 'primeng/chip';
import { PanelModule } from 'primeng/panel';
import { TagModule } from 'primeng/tag';
import { SkeletonModule } from 'primeng/skeleton';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { MarkdownModule } from 'ngx-markdown';
import { ApiService } from '../../core/services/api.service';
import { HealthDashboard, HealthTimelineItem, HealthRiskResponse } from '../../core/models';
import { RelativeTimePipe } from '../../shared/pipes/relative-time.pipe';
import { SeverityPipe } from '../../shared/pipes/severity.pipe';

@Component({
  selector: 'app-analysis',
  standalone: true,
  imports: [
    FormsModule,
    ButtonModule,
    CardModule,
    ChartModule,
    TimelineModule,
    SelectButtonModule,
    ProgressSpinnerModule, 
    ChipModule, 
    PanelModule, 
    TagModule, 
    SkeletonModule,
    ToastModule, 
    MarkdownModule,
    RelativeTimePipe,
    SeverityPipe
  ],
  providers: [MessageService],
  templateUrl: './analysis.component.html',
  styleUrl: './analysis.component.scss',
})
export class AnalysisComponent {
  private readonly api = inject(ApiService);
  private readonly messageService = inject(MessageService);

  private readonly TIMELINE_PAGE_SIZE = 10;

  readonly periodDays = signal(30);
  readonly isLoading = signal(false);
  readonly analysisData = signal<HealthDashboard | null>(null);
  readonly timelineEvents = signal<HealthTimelineItem[]>([]);
  readonly weatherData = signal<HealthRiskResponse | null>(null);
  readonly timelineDisplayCount = signal(this.TIMELINE_PAGE_SIZE);

  readonly displayedTimelineEvents = computed(() =>
    this.timelineEvents().slice(0, this.timelineDisplayCount())
  );

  readonly remainingTimelineCount = computed(() =>
    Math.max(0, this.timelineEvents().length - this.timelineDisplayCount())
  );

  
  filterKnowlegde : string = '';
  resultText: string = '';
  readonly periodOptions = [
    { label: '7 ngày', value: 7 },
    { label: '30 ngày', value: 30 },
    { label: '90 ngày', value: 90 }
  ];

  readonly barOptions = {
    responsive: true,
    plugins: { legend: { display: false } },
    scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } }
  };

  readonly lineOptions = {
    responsive: true,
    plugins: { legend: { display: false } },
    scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } }
  };

  readonly doughnutOptions = {
    responsive: true,
    maintainAspectRatio: true,
    aspectRatio: 1.1,
    plugins: {
      legend: { position: 'top' }
    }
  };

  readonly summaryStats = computed(() => {
    const d = this.analysisData();
    if (!d) return [];
    return [
      { label: 'Tổng tư vấn', value: d.total_sessions, icon: 'pi-comments', color: '#3B82F6' },
      { label: 'Tổng tin nhắn', value: d.total_messages, icon: 'pi-envelope', color: '#10B981' },
      { label: 'TB tin nhắn/phiên', value: d.avg_messages_per_session.toFixed(1), icon: 'pi-chart-bar', color: '#F59E0B' },
      { label: 'Triệu chứng gặp nhiều', value: d.top_symptoms[0]?.name ?? '—', icon: 'pi-heart', color: '#EF4444' }
    ];
  });

  readonly symptomsChartData = computed(() => {
    const d = this.analysisData();
    if (!d?.top_symptoms?.length) return null;
    const top = d.top_symptoms.slice(0, 8);
    return {
      labels: top.map(s => s.name),
      datasets: [{
        label: 'Số lần',
        data: top.map(s => s.count),
        backgroundColor: 'rgba(59, 130, 246, 0.75)',
        borderRadius: 4
      }]
    };
  });

  readonly severityChartData = computed(() => {
    const d = this.analysisData();
    if (!d?.severity_distribution) return null;
    const dist = d.severity_distribution;
    if (dist.severe + dist.moderate + dist.mild === 0) return null;
    return {
      labels: ['Nghiêm trọng', 'Trung bình', 'Nhẹ'],
      datasets: [{
        data: [dist.severe, dist.moderate, dist.mild],
        backgroundColor: ['#EF4444', '#F59E0B', '#10B981']
      }]
    };
  });

  readonly frequencyChartData = computed(() => {
    const d = this.analysisData();
    if (!d?.consultation_frequency?.length) return null;
    return {
      labels: d.consultation_frequency.map(f => f.date),
      datasets: [{
        label: 'Số tư vấn',
        data: d.consultation_frequency.map(f => f.count),
        fill: true,
        tension: 0.4,
        borderColor: '#3B82F6',
        backgroundColor: 'rgba(59, 130, 246, 0.1)'
      }]
    };
  });

  constructor() {
    effect(() => {
      this.loadAll(this.periodDays());
    });
  }

  loadMoreTimeline(): void {
    this.timelineDisplayCount.update(c => c + this.TIMELINE_PAGE_SIZE);
  }

  private loadAll(days: number): void {
    this.isLoading.set(true);
    this.analysisData.set(null);
    this.timelineEvents.set([]);
    this.timelineDisplayCount.set(this.TIMELINE_PAGE_SIZE);

    forkJoin({
      dashboard: this.api.getDashboard(days),
      timeline: this.api.getHealthTimeline(days),
      weather: this.api.getWeatherRisk().pipe(catchError(() => of(null)))
    }).subscribe({
      next: ({ dashboard, timeline, weather }) => {
        this.analysisData.set(dashboard);
        this.timelineEvents.set(timeline);
        this.weatherData.set(weather);
        this.isLoading.set(false);
      },
      error: () => {
        this.messageService.add({
          severity: 'error',
          summary: 'Lỗi',
          detail: 'Không thể tải dữ liệu phân tích'
        });
        this.isLoading.set(false);
      }
    });
  }

  getRiskSeverity(level: string): 'danger' | 'warn' | 'success' {
    if (level === 'cao') return 'danger';
    if (level === 'trung bình') return 'warn';
    return 'success';
  }

  getTempColor(temp: number): string {
    if (temp > 35) return '#EF4444';
    if (temp > 30) return '#F59E0B';
    if (temp < 20) return '#3B82F6';
    return '#10B981';
  }


  // basicRag(text: string){
  //   const knowledge = [
  //     "Angular là framework front-end dùng TypeScript.",
  //     "FastAPI là framework Python để xây dựng API.",
  //     "MongoDB là cơ sở dữ liệu NoSQL.",
  //     "RAG là kỹ thuật kết hợp tìm kiếm tài liệu và mô hình ngôn ngữ."
  //   ];
  //   return knowledge.filter(k => k.toLowerCase().includes(text.toLowerCase()));
  // }

  // handlefilter(text: string){
    
  //   const result = this.basicRag(text);
  //   console.log(result);
  //   this.resultText = result.join('\n');
  //   console.log("nà",this.resultText);
    
  //   return result;
    
  // }
}
