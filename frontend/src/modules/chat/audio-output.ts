/** Speaker routing: a saved choice wins, otherwise a lone real output
 * (e.g. the SoundDrum Bluetooth speaker) is picked automatically. The
 * "default" and "communications" pseudo-devices never count as speakers. */

export interface AudioOutputLike {
  deviceId: string;
  label: string;
}

const PSEUDO = new Set(["default", "communications"]);

export function pickSpeakerOutput(
  devices: AudioOutputLike[],
  savedId: string,
): string {
  if (savedId && devices.some((d) => d.deviceId === savedId)) return savedId;
  const real = devices.filter((d) => d.deviceId && !PSEUDO.has(d.deviceId));
  if (real.length === 1) return real[0].deviceId;
  return "";
}
