"use client";
import { useEffect, useRef, useState } from "react";
import { useAui, useAuiState } from "@assistant-ui/react";
import { Square, Volume2 } from "lucide-react";
import { ParticlesOrb } from "@/components/voiceorb/particles-orb";
import type { OrbState } from "@/components/voiceorb/orb-state";
import { useSalesStore } from "@/modules/sales/store";
import { captureVoice } from "./voice-capture";
import { VoicePlayback } from "./voice-playback";

async function voiceError(response: Response) {
  const data = await response.json().catch(() => null);
  return new Error(
    typeof data?.detail === "string"
      ? data.detail
      : "Voice is unavailable. Try again.",
  );
}
export function VoicePanel() {
  const aui = useAui();
  const running = useAuiState((s) => s.thread.isRunning);
  const response = useSalesStore((s) => s.voiceResponse);
  const savedReply = useSalesStore(
    (s) =>
      s.messages
        .slice()
        .reverse()
        .find(
          (message) =>
            message.role === "assistant" &&
            message.status?.type !== "running" &&
            message.text.trim(),
        )?.text,
  );
  const replayText = response?.text || savedReply;
  const chatReady = useSalesStore(
    (s) =>
      s.apiStatus === "connected" && s.chatStatus?.configured && !s.chatLoading,
  );
  const [configured, setConfigured] = useState(false);
  const [state, setState] = useState<OrbState>("idle");
  const [error, setError] = useState("");
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [microphone, setMicrophone] = useState("");
  const [hasSound, setHasSound] = useState(false);
  const level = useRef(0);
  const capture = useRef<Awaited<ReturnType<typeof captureVoice>> | null>(null);
  const request = useRef<AbortController | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const generation = useRef(0);
  const seen = useRef(response?.id);
  const mounted = useRef(true);
  const spaceHeld = useRef(false);
  const playback = useRef<VoicePlayback | null>(null);
  if (!playback.current)
    playback.current = new VoicePlayback({
      synthesize: async (text, signal) => {
        const result = await fetch("/api/sales/voice/speak", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
          signal,
        });
        if (!result.ok) throw await voiceError(result);
        return result.arrayBuffer();
      },
      onState: (value) => {
        if (mounted.current) {
          setState(value);
          if (value === "speaking") setError("");
        }
      },
      onError: (message) => {
        if (mounted.current) setError(message);
      },
    });
  const cleanup = () => {
    generation.current++;
    request.current?.abort();
    request.current = null;
    capture.current?.cancel();
    capture.current = null;
    if (timer.current) clearTimeout(timer.current);
    playback.current?.cancel();
  };
  useEffect(() => {
    mounted.current = true;
    const abort = new AbortController();
    fetch("/api/sales/voice/status", { signal: abort.signal })
      .then((r) => r.json())
      .then((s) => {
        setConfigured(s.configured);
        if (!s.configured) setError("Add GRADIUM_API_KEY to enable voice.");
      })
      .catch(() => {
        if (!abort.signal.aborted) setError("Voice backend unavailable.");
      });
    return () => {
      mounted.current = false;
      abort.abort();
      cleanup();
      playback.current?.close();
    };
  }, []);
  useEffect(() => {
    if (!response || seen.current === response.id) return;
    seen.current = response.id;
    playback.current?.enqueue(response);
  }, [response]);
  const submit = async () => {
    spaceHeld.current = false;
    if (!capture.current) return;
    if (timer.current) clearTimeout(timer.current);
    const recording = capture.current;
    capture.current = null;
    const epoch = generation.current;
    const abort = new AbortController();
    request.current = abort;
    setState("connecting");
    try {
      const audio = recording.stop();
      const result = await fetch("/api/sales/voice/transcribe", {
        method: "POST",
        body: audio,
        headers: { "Content-Type": "audio/wav" },
        signal: abort.signal,
      });
      if (!result.ok) throw await voiceError(result);
      const { text } = await result.json();
      if (!mounted.current || epoch !== generation.current) return;
      useSalesStore.getState().set({ voiceInputPending: true });
      setState("idle");
      await aui.thread.append({
        role: "user",
        content: [{ type: "text", text }],
      });
    } catch (e) {
      if (!abort.signal.aborted && mounted.current) {
        const message = e instanceof Error ? e.message : "Voice failed.";
        setError(
          message.startsWith("No speech detected")
            ? "Audio was captured, but no words were recognized. Try another microphone or speak more clearly after Listening appears."
            : message,
        );
        setState("error");
      }
    }
  };
  const tap = async () => {
    if (state === "listening") {
      await submit();
      return;
    }
    if (running || state === "speaking" || state === "connecting") {
      cleanup();
      if (running) aui.thread.cancelRun();
      setState("idle");
      return;
    }
    cleanup();
    setError("");
    setHasSound(false);
    setState("connecting");
    const epoch = generation.current;
    try {
      await playback.current?.unlock();
      if (!mounted.current || epoch !== generation.current) return;
      const recording = await captureVoice({
        deviceId,
        onLevel: (value) => {
          level.current = value;
          if (value > 0.001 && mounted.current && epoch === generation.current)
            setHasSound(true);
        },
        onDevice: (device) => {
          if (mounted.current && epoch === generation.current)
            setMicrophone(device.label);
        },
      });
      if (!mounted.current || epoch !== generation.current) {
        recording.cancel();
        return;
      }
      capture.current = recording;
      setState("listening");
      void navigator.mediaDevices
        .enumerateDevices()
        .then((available) => {
          if (mounted.current && epoch === generation.current)
            setDevices(
              available.filter((device) => device.kind === "audioinput"),
            );
        })
        .catch(() => {});
      timer.current = setTimeout(() => void submit(), 44000);
    } catch (e) {
      if (mounted.current && epoch === generation.current) {
        setError(
          e instanceof Error && e.name === "NotAllowedError"
            ? "Microphone permission is needed to speak."
            : "Could not start the microphone. Please try again.",
        );
        setState("error");
      }
    }
  };
  useEffect(() => {
    const editable = (target: EventTarget | null) =>
      target instanceof HTMLElement &&
      Boolean(
        target.closest(
          "input, textarea, select, [contenteditable='true'], [role='textbox'], a, button:not(.voice-orb-button), [role='button']:not(.voice-orb-button)",
        ),
      );
    const down = (event: KeyboardEvent) => {
      if (
        event.code !== "Space" ||
        editable(event.target) ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey
      )
        return;
      if (!configured || !chatReady) return;
      event.preventDefault();
      if (
        event.repeat ||
        spaceHeld.current ||
        running ||
        (state !== "idle" && state !== "error")
      )
        return;
      spaceHeld.current = true;
      void tap();
    };
    const up = (event: KeyboardEvent) => {
      if (event.code !== "Space" || !spaceHeld.current) return;
      event.preventDefault();
      spaceHeld.current = false;
      if (capture.current) void submit();
      else {
        // Release during permission/setup: discard any recording that resolves later.
        cleanup();
        setState("idle");
      }
    };
    const blur = () => {
      if (!spaceHeld.current) return;
      spaceHeld.current = false;
      cleanup();
      setState("idle");
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", blur);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", blur);
    };
  });
  const displayed =
    state === "speaking" ? "speaking" : running ? "thinking" : state;
  const label = running
    ? "Stop response"
    : state === "listening"
      ? "Send voice request"
      : state === "speaking"
        ? "Stop speaking"
        : state === "connecting"
          ? "Cancel voice request"
          : "Start voice request";
  return (
    <div className="voice-panel">
      <button
        className="voice-orb-button"
        aria-label={label}
        aria-keyshortcuts="Space"
        title="Hold Space to record; release to send. Or tap to start/stop."
        aria-pressed={state === "listening"}
        disabled={!configured || !chatReady}
        onClick={() => void tap()}
      >
        <ParticlesOrb
          state={!configured || !chatReady ? "disabled" : displayed}
          levelRef={state === "listening" ? level : undefined}
          size={120}
          colorFrom="#274c67"
          colorTo="#ff6f00"
          label={displayed}
        />
        <span className="voice-orb-icon">
          {running ||
          state === "listening" ||
          state === "speaking" ||
          state === "connecting" ? (
            <Square size={17} />
          ) : null}
        </span>
      </button>
      <span className="voice-status" role="status">
        {state === "speaking"
          ? "Speaking · tap to stop"
          : running
            ? "Working…"
            : state === "listening"
              ? !hasSound
                ? "Listening · waiting for microphone sound"
                : spaceHeld.current
                  ? "Listening · release Space to send"
                  : "Listening · tap to send"
              : state === "connecting"
                ? "Connecting…"
                : "Hold Space to speak · or tap"}
      </span>
      {
        <button
          className="icon-button"
          aria-label={replayText ? "Hear latest reply" : "Test speaker"}
          title={replayText ? "Hear latest reply" : "Test speaker"}
          disabled={!configured || state === "listening"}
          onClick={() => {
            setError("");
            playback.current?.cancel();
            void playback.current
              ?.unlock()
              .then(() =>
                playback.current?.enqueue({
                  text: replayText || "Pulse is ready. You can speak now.",
                  kind: "final",
                }),
              )
              .catch(() =>
                setError(
                  "Audio is blocked. Check the browser's site sound permission.",
                ),
              );
          }}
        >
          <Volume2 size={17} />
        </button>
      }
      {microphone &&
        (devices.length > 1 ? (
          <select
            className="voice-input-select"
            aria-label="Microphone input"
            value={deviceId}
            disabled={
              state === "listening" || state === "connecting" || running
            }
            onChange={(event) => setDeviceId(event.target.value)}
          >
            <option value="">Default · {microphone}</option>
            {devices
              .filter((device) => device.deviceId !== "default")
              .map((device) => (
                <option key={device.deviceId} value={device.deviceId}>
                  {device.label || "Microphone"}
                </option>
              ))}
          </select>
        ) : (
          <span className="voice-input-name">{microphone}</span>
        ))}
      {error && (
        <p className="voice-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
