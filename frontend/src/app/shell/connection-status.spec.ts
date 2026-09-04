import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { ConnectionStatus } from './connection-status';

describe('ConnectionStatus', () => {
  let fixture: ComponentFixture<ConnectionStatus>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [ConnectionStatus],
      providers: [provideZonelessChangeDetection()],
    });
    fixture = TestBed.createComponent(ConnectionStatus);
    fixture.componentRef.setInput('state', 'live');
  });

  const render = (botAlive: boolean | null, botHealthy: boolean | null) => {
    fixture.componentRef.setInput('botAlive', botAlive);
    fixture.componentRef.setInput('botHealthy', botHealthy);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  };

  it('says the bot is failing when it is alive but not healthy', () => {
    const el = render(true, false);
    expect(el.textContent).toContain('bot failing');
    expect(el.textContent).not.toContain('bot offline');
  });

  it('still says offline when the bot is not alive, and not both', () => {
    const el = render(false, false);
    expect(el.textContent).toContain('bot offline');
    expect(el.textContent).not.toContain('bot failing');
  });

  it('says nothing about the bot while health is unknown', () => {
    const el = render(true, null);
    expect(el.textContent).not.toContain('bot failing');
    expect(el.textContent).not.toContain('bot offline');
  });

  it('styles a failing bot with the same amber class as an offline one', () => {
    // NG52 colour review: health chrome is greyscale and amber only, and two
    // severities of one caution are told apart by their label, not a new
    // colour. Asserting the shared `.bot` class is what pins that down -- a
    // future green/red variant would have to drop it and fail here.
    const failing = render(true, false).querySelector('.bot-failing');
    expect(failing).toBeTruthy();
    expect(failing!.classList.contains('bot')).toBe(true);
  });
});
