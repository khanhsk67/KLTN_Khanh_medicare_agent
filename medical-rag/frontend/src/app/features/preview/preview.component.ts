import { Component, signal, effect, inject } from '@angular/core';
import { DOCUMENT } from '@angular/common';

type PreviewTab = 'navbar' | 'auth' | 'chat' | 'wallet' | 'history';

@Component({
  selector: 'app-preview',
  standalone: true,
  templateUrl: './preview.component.html',
  styleUrl: './preview.component.scss'
})
export class PreviewComponent {
  private readonly document = inject(DOCUMENT);

  readonly activeTab = signal<PreviewTab>('navbar');
  readonly themeMode = signal<'light' | 'dark'>(
    (typeof localStorage !== 'undefined' && localStorage.getItem('medicare-theme') === 'dark') ? 'dark' : 'light'
  );

  readonly tabs: { id: PreviewTab; label: string }[] = [
    { id: 'navbar', label: 'Navbar' },
    { id: 'auth', label: 'Auth (Login/Register)' },
    { id: 'chat', label: 'Chat' },
    { id: 'wallet', label: 'Wallet' },
    { id: 'history', label: 'History' }
  ];

  constructor() {
    effect(() => {
      const mode = this.themeMode();
      const body = this.document.body;
      if (mode === 'dark') body.classList.add('dark-mode');
      else body.classList.remove('dark-mode');
      try { localStorage.setItem('medicare-theme', mode); } catch {}
    });
  }

  setTab(id: PreviewTab): void { this.activeTab.set(id); }
  toggleTheme(): void { this.themeMode.update(m => (m === 'light' ? 'dark' : 'light')); }
}
