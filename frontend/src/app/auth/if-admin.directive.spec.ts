import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { patchState } from '@ngrx/signals';
import { unprotected } from '@ngrx/signals/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import type { Role } from '../api/models';
import { SessionStore } from '../stores/session.store';
import { IfAdminDirective } from './if-admin.directive';

@Component({
  imports: [IfAdminDirective],
  template: `<button *ifAdmin type="button" class="write">Close</button><p class="read">Book</p>`,
})
class Host {}

describe('IfAdminDirective (v207)', () => {
  let fixture: ComponentFixture<Host>;
  const el = () => fixture.nativeElement as HTMLElement;

  const as = (role: Role | null) => {
    patchState(unprotected(TestBed.inject(SessionStore)), {
      status: role ? 'authenticated' : 'anonymous', username: role ? 'someone' : null, role,
    });
    fixture.detectChanges();
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideHttpClient(), provideHttpClientTesting()],
    });
    fixture = TestBed.createComponent(Host);
  });

  it('renders the control for the admin', () => {
    as('admin');
    expect(el().querySelectorAll('button.write')).toHaveLength(1);
  });

  it('renders nothing for a viewer, and leaves the rest of the page alone', () => {
    as('viewer');
    expect(el().querySelector('button.write')).toBeNull();
    expect(el().querySelector('p.read')).not.toBeNull();
  });

  it('renders nothing without a role', () => {
    as(null);
    expect(el().querySelector('button.write')).toBeNull();
  });

  it('follows the role as it changes, never rendering twice', () => {
    as('viewer');
    as('admin');
    as('admin');
    expect(el().querySelectorAll('button.write')).toHaveLength(1);
    as('viewer');
    expect(el().querySelector('button.write')).toBeNull();
  });
});
