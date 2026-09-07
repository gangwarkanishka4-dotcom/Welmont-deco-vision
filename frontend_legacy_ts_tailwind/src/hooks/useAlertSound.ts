import { useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'welmont.alertSoundEnabled';

// Default OFF: an autoplaying/beeping tab surprises operators before they've opted in;
// they enable it explicitly from Settings once they want audible HIGH-severity alerts.
const DEFAULT_ENABLED = false;

export function useAlertSoundSetting(): [boolean, (v: boolean) => void] {
  const [enabled, setEnabled] = useState<boolean>(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw === null ? DEFAULT_ENABLED : raw === 'true';
    } catch {
      return DEFAULT_ENABLED;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(enabled));
    } catch {
      /* localStorage unavailable (e.g. private mode) — setting just won't persist */
    }
  }, [enabled]);

  return [enabled, setEnabled];
}

export function isAlertSoundEnabled(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true';
  } catch {
    return DEFAULT_ENABLED;
  }
}

let sharedAudioCtx: AudioContext | null = null;

/** Two short synthesized beeps via Web Audio — no audio asset to ship or license. */
export function playAlertBeep(): void {
  try {
    if (!sharedAudioCtx) {
      const Ctor = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      sharedAudioCtx = new Ctor();
    }
    const ctx = sharedAudioCtx;
    const beepAt = (startOffset: number) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'square';
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0.0001, ctx.currentTime + startOffset);
      gain.gain.exponentialRampToValueAtTime(0.15, ctx.currentTime + startOffset + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + startOffset + 0.15);
      osc.connect(gain).connect(ctx.destination);
      osc.start(ctx.currentTime + startOffset);
      osc.stop(ctx.currentTime + startOffset + 0.16);
    };
    beepAt(0);
    beepAt(0.22);
  } catch {
    /* Web Audio unavailable — fail silently, sound is a non-critical enhancement */
  }
}

export function useBeepOnce(): () => void {
  return useCallback(() => {
    if (isAlertSoundEnabled()) playAlertBeep();
  }, []);
}
