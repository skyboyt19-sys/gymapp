/** Haptik + Töne. Beides ist optional und scheitert leise, wenn iOS es blockiert. */

let soundEnabled = true
let vibrationEnabled = true

export function setFeedbackPrefs(sound: boolean, vibration: boolean) {
  soundEnabled = sound
  vibrationEnabled = vibration
}

type Pattern = 'tap' | 'success' | 'warn' | 'done'

const PATTERNS: Record<Pattern, number | number[]> = {
  tap: 12,
  success: [18, 60, 28],
  warn: [30, 80, 30],
  done: [40, 90, 40, 90, 120],
}

export function haptic(pattern: Pattern = 'tap') {
  if (!vibrationEnabled) return
  try {
    navigator.vibrate?.(PATTERNS[pattern])
  } catch {
    /* nicht unterstützt (iOS Safari) — kein Problem */
  }
}

let ctx: AudioContext | null = null

function audioCtx(): AudioContext | null {
  try {
    if (!ctx) {
      const Ctor: typeof AudioContext | undefined =
        window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!Ctor) return null
      ctx = new Ctor()
    }
    if (ctx.state === 'suspended') void ctx.resume()
    return ctx
  } catch {
    return null
  }
}

/**
 * iOS erlaubt Audio erst nach einer Nutzergeste. Diese Funktion wird beim
 * ersten Tap aufgerufen, damit der Timer-Ton später auch im Hintergrund geht.
 */
export function unlockAudio() {
  const c = audioCtx()
  if (!c) return
  try {
    const buf = c.createBuffer(1, 1, 22050)
    const src = c.createBufferSource()
    src.buffer = buf
    src.connect(c.destination)
    src.start(0)
  } catch {
    /* egal */
  }
}

function tone(freq: number, durationMs: number, when = 0, gain = 0.14) {
  const c = audioCtx()
  if (!c) return
  const t0 = c.currentTime + when
  const osc = c.createOscillator()
  const g = c.createGain()
  osc.type = 'sine'
  osc.frequency.value = freq
  g.gain.setValueAtTime(0.0001, t0)
  g.gain.exponentialRampToValueAtTime(gain, t0 + 0.012)
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + durationMs / 1000)
  osc.connect(g).connect(c.destination)
  osc.start(t0)
  osc.stop(t0 + durationMs / 1000 + 0.03)
}

export function beep(kind: 'tick' | 'end' | 'pr' = 'tick') {
  if (!soundEnabled) return
  if (kind === 'tick') tone(880, 90, 0, 0.08)
  else if (kind === 'end') {
    tone(880, 140)
    tone(1174, 160, 0.16)
    tone(1568, 260, 0.33)
  } else {
    tone(1046, 120)
    tone(1318, 120, 0.13)
    tone(1568, 320, 0.26)
  }
}

/** Kombinierte Rückmeldung für wichtige Ereignisse. */
export function cue(kind: 'setDone' | 'restEnd' | 'pr' | 'finish') {
  switch (kind) {
    case 'setDone':
      haptic('tap')
      break
    case 'restEnd':
      haptic('done')
      beep('end')
      break
    case 'pr':
      haptic('success')
      beep('pr')
      break
    case 'finish':
      haptic('done')
      beep('end')
      break
  }
}
