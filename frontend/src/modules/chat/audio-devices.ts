/** Automatic earphone/headset routing for voice input and output. */

export interface AudioDeviceLike {
  deviceId: string;
  label: string;
}

const EARPIECE =
  /buds|airpod|headset|headphone|earphone|earbud|jabra|plantronics|poly|sony|bose|soundcore|sennheiser|anker|usb|bluetooth|\bwh-|\bwf-|hfp|hsp/i;

/**
 * Choose a device id: an explicitly saved choice wins while it is still
 * plugged in; otherwise prefer an earphone-like label (e.g. OnePlus Buds 3);
 * otherwise "" follows the system default.
 */
export function pickAudioDevice(
  devices: AudioDeviceLike[],
  savedId: string,
): string {
  if (savedId && devices.some((d) => d.deviceId === savedId)) return savedId;
  const ear = devices.find((d) => d.deviceId && EARPIECE.test(d.label || ""));
  if (ear) return ear.deviceId;
  return "";
}
