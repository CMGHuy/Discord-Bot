import { ChangeDetectionStrategy, Component, input } from '@angular/core';
export type PanelTrack = 'narrow' | 'wide';
@Component({ selector: 'sb-panel-grid', changeDetection: ChangeDetectionStrategy.OnPush, host: { '[class]': 'track()' }, template: `<ng-content />`, styles: `:host { display: grid; gap: var(--space-14); grid-template-columns: repeat(auto-fill, minmax(min(220px, 100%), 1fr)); } :host(.wide) { grid-template-columns: repeat(auto-fill, minmax(min(320px, 100%), 1fr)); } @media (max-width: 639px) { :host, :host(.wide) { grid-template-columns: minmax(0, 1fr); } }` })
export class PanelGrid { readonly track = input<PanelTrack>('narrow'); }
