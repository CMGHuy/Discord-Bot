import { describe, expect, it } from 'vitest';

import { focusWorkspaceHeading } from './route-focus';

describe('focusWorkspaceHeading', () => {
  it('moves focus to the workspace heading', () => {
    document.body.innerHTML = '<main class="workspace"><h1>Trades</h1></main>';
    focusWorkspaceHeading(document);
    expect(document.activeElement?.tagName).toBe('H1');
  });

  it('makes the heading programmatically focusable without adding a tab stop', () => {
    document.body.innerHTML = '<main class="workspace"><h1>Trades</h1></main>';
    focusWorkspaceHeading(document);
    expect(document.querySelector('h1')!.getAttribute('tabindex')).toBe('-1');
  });

  it('does nothing when the workspace has no heading yet', () => {
    document.body.innerHTML = '<main class="workspace"></main>';
    expect(() => focusWorkspaceHeading(document)).not.toThrow();
  });
});
