import { SpeechPort } from './voice-speaker';

/** A stand-in for the browser's `speechSynthesis` (jsdom has none). The
 *  test drives the current utterance's events by hand. Imported by specs only. */
export class FakeSpeech implements SpeechPort {
  readonly spoken: SpeechSynthesisUtterance[] = [];
  cancelled = 0;
  speaking = false;
  onvoiceschanged: (() => void) | null = null;
  private voiceList: SpeechSynthesisVoice[] = [];
  private current: SpeechSynthesisUtterance | null = null;

  speak(utterance: SpeechSynthesisUtterance): void {
    this.spoken.push(utterance);
    this.current = utterance;
  }

  /** Like Chrome: a cancelled utterance reports an "interrupted" error. */
  cancel(): void {
    this.cancelled += 1;
    this.fail('interrupted');
  }

  getVoices(): SpeechSynthesisVoice[] {
    return this.voiceList;
  }

  texts(): string[] {
    return this.spoken.map((utterance) => utterance.text);
  }

  start(): void {
    this.speaking = true;
    this.current?.onstart?.call(this.current, {} as SpeechSynthesisEvent);
  }

  finish(): void {
    const utterance = this.release();
    utterance?.onend?.call(utterance, {} as SpeechSynthesisEvent);
  }

  fail(error = 'not-allowed'): void {
    const utterance = this.release();
    utterance?.onerror?.call(utterance, { error } as unknown as SpeechSynthesisErrorEvent);
  }

  setVoices(names: string[]): void {
    this.voiceList = names.map((name) => ({ name }) as unknown as SpeechSynthesisVoice);
    this.onvoiceschanged?.();
  }

  private release(): SpeechSynthesisUtterance | null {
    const utterance = this.current;
    this.current = null;
    this.speaking = false;
    return utterance;
  }
}

/** A plain-object utterance: jsdom has no SpeechSynthesisUtterance. */
export function fakeUtterance(text: string): SpeechSynthesisUtterance {
  return { text, rate: 1, voice: null, onstart: null, onend: null, onerror: null } as unknown as SpeechSynthesisUtterance;
}
