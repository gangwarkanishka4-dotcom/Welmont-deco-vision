import { useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'welmont.alertSoundEnabled';

// Default OFF: an autoplaying/beeping tab surprises operators before they've opted in;
// they enable it explicitly from Settings once they want audible HIGH-severity alerts.
const DEFAULT_ENABLED = false;

export function useAlertSoundSetting() {
  const [enabled, setEnabled] = useState(() => {
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

export function isAlertSoundEnabled() {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true';
  } catch {
    return DEFAULT_ENABLED;
  }
}

let sharedAudioCtx = null;

/** A harsh, mechanical-buzzer-style alert via Web Audio — no audio asset to
 * ship or license. Two ingredients make a plain tone read as "buzzer"
 * rather than "beep": a low square-wave carrier (square waves are rich in
 * harsh odd harmonics at this range) and fast on-off amplitude modulation
 * (a second square-wave oscillator chopping the gain), which is what gives
 * a doorbell/game-show buzzer its rattling texture. */
export function playAlertBeep() {
  try {
    if (!sharedAudioCtx) {
      const Ctor = window.AudioContext || window.webkitAudioContext;
      sharedAudioCtx = new Ctor();
    }
    const ctx = sharedAudioCtx;

    const buzzAt = (startOffset, duration) => {
      const start = ctx.currentTime + startOffset;

      const carrier = ctx.createOscillator();
      carrier.type = 'square';
      carrier.frequency.value = 220; // low and harsh, not a clean electronic tone

      // Amplitude-modulates the carrier's gain by connecting an oscillator
      // straight into the AudioParam: mainGain swings between ~0 and ~1
      // every time the LFO cycles, chopping the tone into a buzz.
      const lfo = ctx.createOscillator();
      lfo.type = 'square';
      lfo.frequency.value = 28;
      const lfoGain = ctx.createGain();
      lfoGain.gain.value = 0.5;
      lfo.connect(lfoGain);

      const mainGain = ctx.createGain();
      mainGain.gain.value = 0.5;
      lfoGain.connect(mainGain.gain);

      const envelope = ctx.createGain();
      envelope.gain.setValueAtTime(0.0001, start);
      envelope.gain.exponentialRampToValueAtTime(0.35, start + 0.02);
      envelope.gain.setValueAtTime(0.35, start + duration - 0.03);
      envelope.gain.exponentialRampToValueAtTime(0.0001, start + duration);

      carrier.connect(mainGain).connect(envelope).connect(ctx.destination);
      carrier.start(start);
      lfo.start(start);
      carrier.stop(start + duration);
      lfo.stop(start + duration);
    };

    buzzAt(0, 0.5);
    buzzAt(0.65, 0.5);
  } catch {
    /* Web Audio unavailable — fail silently, sound is a non-critical enhancement */
  }
}

export function useBeepOnce() {
  return useCallback(() => {
    if (isAlertSoundEnabled()) playAlertBeep();
  }, []);
}

// Voice names that tend to sound the most natural (not robotic) among what
// browsers commonly ship, roughly in preference order. "Online (Natural)"
// voices (Edge/Windows 11) and Google's network voices (Chrome) are full
// neural TTS, well ahead of older on-device engines like classic "Zira".
const PREFERRED_FEMALE_VOICE_NAMES = [
  'Google UK English Female',
  'Google US English',
  'Microsoft Aria Online (Natural)',
  'Microsoft Jenny Online (Natural)',
  'Microsoft Michelle Online (Natural)',
  'Microsoft Emma Online (Natural)',
  'Samantha', // macOS/iOS default female voice
  'Microsoft Zira',
  'Microsoft Susan',
  'Female',
];

// Windows/Edge/Chrome/macOS ship voices named after a person, with no
// separate "gender" field exposed to the page — the name IS the only signal.
// These cover the female and male given names actually used across the
// common voice packs (classic SAPI5 David/Zira/Mark, Windows 11's Natural
// voice pairs like Aria/Guy, Sonia/Ryan, Natasha/William, and macOS/Chrome
// extras), so a machine whose exact voices aren't in the preferred list
// above still resolves to a female one instead of an arbitrary pick.
const FEMALE_NAME_PATTERN =
  /female|zira|susan|samantha|aria|jenny|michelle|emma|hazel|sonia|libby|natasha|clara|elsa|ana|catherine|karen|moira|tessa|victoria|fiona|serena|nicky|kate|salli|joanna|ivy|kimberly|amy|olivia|ruth|anna|maria|laura|sara|monica|paulina|carmen|elena|isabela|camila|valentina/i;
const MALE_NAME_PATTERN =
  /\bmale\b|david|mark|guy|ryan|william|liam|james|ravi|daniel|george|thomas|eric|justin|brian|matthew|alex(?!a)|fred|paul|richard|sean|tom|diego|jorge|carlos|juan|pablo|felipe|miguel/i;

let cachedVoice;
let cachedVoiceFor = null;

function pickFemaleVoice() {
  if (!window.speechSynthesis) return null;
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return null;

  // getVoices() is stable once populated — recompute only if the list actually changed.
  const key = voices.length + ':' + (voices[0]?.name ?? '');
  if (cachedVoiceFor === key) return cachedVoice;
  cachedVoiceFor = key;

  const byName = (name) => voices.find((v) => v.name === name);
  const exact = PREFERRED_FEMALE_VOICE_NAMES.map(byName).find(Boolean);
  if (exact) return (cachedVoice = exact);

  // No exact match (different OS/browser voice pack) — restrict to English so
  // the announcement is intelligible, then prefer, in order: a voice whose
  // name is recognizably female; failing that, the best-quality voice that
  // at least isn't recognizably male; only truly unlabeled voices fall
  // through to an arbitrary pick.
  const english = voices.filter((v) => v.lang?.toLowerCase().startsWith('en'));
  const pool = english.length ? english : voices;

  const female = pool.find((v) => FEMALE_NAME_PATTERN.test(v.name));
  if (female) return (cachedVoice = female);

  const notMale = pool.filter((v) => !MALE_NAME_PATTERN.test(v.name));
  const naturalNotMale = notMale.find((v) => /natural|neural|online/i.test(v.name));
  return (cachedVoice = naturalNotMale ?? notMale[0] ?? pool[0] ?? null);
}

/** Speaks a short line via the browser's built-in text-to-speech — no audio
 * asset or backend TTS call needed. Runs after the beep's ~0.4s tail so the
 * two don't talk over each other. Picks the most natural-sounding female
 * voice this browser/OS has installed. */
export function speakAlert(text) {
  try {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel(); // don't queue behind a previous announcement
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.95; // a hair slower than default reads as calmer/more natural, not robotic
    utterance.pitch = 1.05;
    const voice = pickFemaleVoice();
    if (voice) utterance.voice = voice;
    window.speechSynthesis.speak(utterance);
  } catch {
    /* speech synthesis unavailable — fail silently, same as the beep */
  }
}

// Chrome/Edge load voices asynchronously — the first speakAlert() call can
// land before getVoices() has anything, so prime the cache as soon as the
// list is ready rather than waiting for the first real alert to expose that.
if (typeof window !== 'undefined' && window.speechSynthesis) {
  window.speechSynthesis.addEventListener?.('voiceschanged', pickFemaleVoice);
}

export function useAnnounceOnce() {
  return useCallback((text) => {
    if (!isAlertSoundEnabled()) return;
    setTimeout(() => speakAlert(text), 400);
  }, []);
}
