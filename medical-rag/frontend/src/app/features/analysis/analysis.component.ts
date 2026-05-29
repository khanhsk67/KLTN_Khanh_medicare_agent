import { Component, signal, computed, effect, inject } from '@angular/core';
import { DOCUMENT } from '@angular/common';
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
  styleUrl: './analysis.component.scss'
})
export class AnalysisComponent {
  private readonly api = inject(ApiService);
  private readonly messageService = inject(MessageService);
  private readonly document = inject(DOCUMENT);

  readonly themeMode = signal<'light' | 'dark'>(
    (typeof localStorage !== 'undefined' && localStorage.getItem('medicare-theme') === 'dark')
      ? 'dark'
      : 'light'
  );

  toggleTheme(): void {
    this.themeMode.update(m => (m === 'light' ? 'dark' : 'light'));
  }

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

  readonly doughnutOptions = computed(() => {
    const isDark = this.themeMode() === 'dark';
    return {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '68%',
      rotation: -90,
      circumference: 360,
      layout: { padding: 8 },
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            usePointStyle: true,
            pointStyle: 'circle',
            padding: 18,
            font: { size: 12, weight: 600 },
            color: isDark ? '#cbd5e1' : '#475569'
          }
        },
        tooltip: {
          backgroundColor: isDark ? 'rgba(15, 23, 42, 0.95)' : 'rgba(15, 23, 42, 0.92)',
          titleColor: '#ffffff',
          bodyColor: '#e2e8f0',
          padding: 12,
          cornerRadius: 10,
          displayColors: true,
          borderColor: 'rgba(56, 189, 248, 0.3)',
          borderWidth: 1,
          callbacks: {
            label: (ctx: any) => ` ${ctx.label}: ${ctx.parsed} lượt`
          }
        }
      },
      elements: {
        arc: {
          borderWidth: 4,
          borderColor: isDark ? 'rgba(15, 23, 42, 0.8)' : 'transparent',
          borderRadius: 12,
          hoverBorderWidth: 0,
          hoverOffset: 14
        }
      },
      animation: { animateRotate: true, animateScale: true, duration: 900, easing: 'easeOutQuart' as const }
    };
  });

  readonly doughnutPlugins = [{
    id: 'centerTotalText',
    afterDraw: (chart: any) => {
      const { ctx, data, chartArea } = chart;
      const dataset = data.datasets?.[0];
      if (!dataset || !chartArea) return;
      const total = (dataset.data as number[]).reduce((a, b) => a + (Number(b) || 0), 0);
      if (!total) return;
      const cx = (chartArea.left + chartArea.right) / 2;
      const cy = (chartArea.top + chartArea.bottom) / 2;
      const isDark = typeof document !== 'undefined' && document.body.classList.contains('dark-mode');
      ctx.save();
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = isDark ? '#f8fafc' : '#0f172a';
      ctx.font = '800 2rem "Inter", system-ui, sans-serif';
      ctx.fillText(String(total), cx, cy - 10);
      ctx.fillStyle = isDark ? '#94a3b8' : '#64748b';
      ctx.font = '600 0.75rem "Inter", system-ui, sans-serif';
      ctx.fillText('Tổng triệu chứng', cx, cy + 18);
      ctx.restore();
    }
  }];

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

  readonly severityChartData = computed(() => {
    const d = this.analysisData();
    if (!d?.severity_distribution) return null;
    const dist = d.severity_distribution;
    if (dist.severe + dist.moderate + dist.mild === 0) return null;
    return {
      labels: ['Nghiêm trọng', 'Trung bình', 'Nhẹ'],
      datasets: [{
        data: [dist.severe, dist.moderate, dist.mild],
        backgroundColor: ['#ef4444', '#f59e0b', '#10b981'],
        hoverBackgroundColor: ['#dc2626', '#d97706', '#059669']
      }]
    };
  });

  readonly weeklyForecast = computed(() => {
    const dayNames = ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7'];
    const placeholderConditions = [
      { icon: 'pi-sun', label: 'Nắng' },
      { icon: 'pi-cloud', label: 'Có mây' },
      { icon: 'pi-cloud-showers-heavy', label: 'Mưa' },
      { icon: 'pi-sun', label: 'Nắng' },
      { icon: 'pi-cloud', label: 'Nhiều mây' },
      { icon: 'pi-cloud-rain', label: 'Mưa nhẹ' }
    ];
    const today = new Date();
    return placeholderConditions.map((cond, i) => {
      const d = new Date(today);
      d.setDate(today.getDate() + i);
      return { name: dayNames[d.getDay()], icon: cond.icon, label: cond.label };
    });
  });

  constructor() {
    effect(() => {
      const mode = this.themeMode();
      const body = this.document.body;
      if (mode === 'dark') body.classList.add('dark-mode');
      else body.classList.remove('dark-mode');
      try { localStorage.setItem('medicare-theme', mode); } catch {}
    });

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
