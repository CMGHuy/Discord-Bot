import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

/** Honest destination for a planned workspace. Route data keeps one component
 * reusable while preserving the shell-owned title/subtitle contract. */
@Component({
  selector: 'sb-planned-workspace',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <section class="planned">
      <p class="eyebrow">Planned workspace</p>
      <p>{{ planned }}</p>
      <p>This workspace is not built yet.</p>
      <a [routerLink]="insteadLink">Use {{ insteadLabel }} today</a>
    </section>
  `,
  styles: `
    .planned { max-width: 52ch; padding: var(--space-20); background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
    .planned p { color: var(--text-secondary); line-height: 1.5; }
    .eyebrow { color: var(--text-faint); font-size: var(--text-micro); letter-spacing: .08em; text-transform: uppercase; }
    a { color: var(--accent); }
  `,
})
export class PlannedWorkspace {
  private readonly data = inject(ActivatedRoute).snapshot.data;
  protected readonly planned = String(this.data['planned'] ?? 'This workspace');
  protected readonly insteadLabel = String(this.data['insteadLabel'] ?? 'Dashboard');
  protected readonly insteadLink = String(this.data['insteadLink'] ?? '/dashboard');
}
