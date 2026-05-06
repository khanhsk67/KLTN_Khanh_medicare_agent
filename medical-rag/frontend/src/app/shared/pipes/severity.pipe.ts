import { Pipe, PipeTransform } from '@angular/core';

type SeverityTag = 'danger' | 'warn' | 'success';

@Pipe({
  name: 'severity',
  standalone: true,
  pure: true
})
export class SeverityPipe implements PipeTransform {
  transform(value: string, mode: 'label' | 'tag' = 'label'): string | SeverityTag {
    if (mode === 'tag') {
      if (value === 'severe') return 'danger';
      if (value === 'moderate') return 'warn';
      return 'success';
    }
    const labels: Record<string, string> = {
      severe: 'Nghiêm trọng',
      moderate: 'Trung bình',
      mild: 'Nhẹ'
    };
    return labels[value] ?? value;
  }
}
