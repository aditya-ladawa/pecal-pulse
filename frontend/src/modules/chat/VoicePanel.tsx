"use client";
import { useEffect, useRef, useState } from "react";
import { useAui, useAuiState } from "@assistant-ui/react";
import { RoomAudioRenderer, RoomContext } from "@livekit/components-react";
import { Square, Volume2 } from "lucide-react";
import { ParticlesOrb } from "@/components/voiceorb/particles-orb";
import { createLiveKitAdapter } from "@/components/voiceorb/create-livekit-adapter";
import type { OrbState } from "@/components/voiceorb/orb-state";
import { useSalesStore } from "@/modules/sales/store";
import { LiveKitVoice } from "./voice-livekit";

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
          (m) =>
            m.role === "assistant" &&
            m.status?.type !== "running" &&
            m.text.trim(),
        )?.text,
  );
  const chatReady = useSalesStore(
    (s) =>
      s.apiStatus === "connected" && s.chatStatus?.configured && !s.chatLoading,
  );
  const [configured, setConfigured] = useState(false);
  const [state, setState] = useState<OrbState>("idle");
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState("");
  const [voice, setVoice] = useState<LiveKitVoice | null>(null);
  const [adapter, setAdapter] = useState<ReturnType<
    typeof createLiveKitAdapter
  > | null>(null);
  const mounted = useRef(false);
  const generation = useRef(0);
  const spaceHeld = useRef(false);
  const listening = useRef(false);
  const seen = useRef(response?.id);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    mounted.current = true;
    const client = new LiveKitVoice({
      onSpeaking: (value) => {
        if (mounted.current) setSpeaking(value);
      },
      onError: (message) => {
        if (mounted.current) {
          setError(message);
          setState("error");
        }
      },
    });
    const meter = createLiveKitAdapter();
    setVoice(client);
    setAdapter(meter);
    const abort = new AbortController();
    fetch("/api/sales/voice/status", { signal: abort.signal })
      .then((r) => r.json())
      .then((s) => {
        setConfigured(s.configured);
        if (!s.configured)
          setError("Configure LiveKit in the root .env to enable voice.");
      })
      .catch(() => {
        if (!abort.signal.aborted) setError("Voice backend unavailable.");
      });
    return () => {
      mounted.current = false;
      generation.current++;
      abort.abort();
      if (timer.current) clearTimeout(timer.current);
      meter.dispose();
      client.close();
    };
  }, []);

  useEffect(() => {
    if (!voice || !response || seen.current === response.id) return;
    seen.current = response.id;
    // LiveKit already speaks one immediate acknowledgement. Tool narration stays text-only.
    if (response.kind === "progress") return;
    void voice.speak(response.text).catch((e) => {
      if (mounted.current) setError(e.message || "Could not speak this reply.");
    });
  }, [response, voice]);

  const cancel = () => {
    generation.current++;
    spaceHeld.current = false;
    listening.current = false;
    if (timer.current) clearTimeout(timer.current);
    adapter?.setTrack();
    void voice?.cancel();
    if (running) aui.thread.cancelRun();
    setSpeaking(false);
    setState("idle");
  };
  const submit = async () => {
    spaceHeld.current = false;
    if (!voice || !listening.current) return;
    listening.current = false;
    if (timer.current) clearTimeout(timer.current);
    adapter?.setTrack();
    setState("connecting");
    const epoch = generation.current;
    try {
      const text = await voice.finish();
      if (!text || !mounted.current || epoch !== generation.current) return;
      setState("idle");
      useSalesStore.getState().set({ voiceInputPending: true });
      await aui.thread.append({
        role: "user",
        content: [{ type: "text", text }],
      });
    } catch (e) {
      if (mounted.current && epoch === generation.current) {
        setError(
          e instanceof Error ? e.message : "Could not transcribe speech.",
        );
        setState("error");
      }
    }
  };
  const start = async () => {
    if (!voice) return;
    // A new spoken turn interrupts both audio and the running LangGraph turn.
    if (running) aui.thread.cancelRun();
    setError("");
    setState("connecting");
    setSpeaking(false);
    const epoch = ++generation.current;
    try {
      if (
        !(await voice.start()) ||
        !mounted.current ||
        epoch !== generation.current
      )
        return;
      listening.current = true;
      setState("listening");
      adapter?.setTrack({ publication: voice.microphone() });
      timer.current = setTimeout(() => void submit(), 44000);
    } catch (e) {
      if (mounted.current && epoch === generation.current) {
        void voice.cancel();
        setError(e instanceof Error ? e.message : "Could not start voice.");
        setState("error");
      }
    }
  };
  const tap = () => {
    if (listening.current) void submit();
    else if (running || speaking || state === "connecting") cancel();
    else void start();
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
        event.metaKey ||
        !configured ||
        !chatReady
      )
        return;
      event.preventDefault();
      if (
        event.repeat ||
        spaceHeld.current ||
        listening.current ||
        state === "connecting"
      )
        return;
      spaceHeld.current = true;
      void start();
    };
    const up = (event: KeyboardEvent) => {
      if (event.code !== "Space" || !spaceHeld.current) return;
      event.preventDefault();
      spaceHeld.current = false;
      if (listening.current) void submit();
      else cancel();
    };
    const blur = () => {
      if (spaceHeld.current) cancel();
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
    state === "listening"
      ? "listening"
      : speaking
        ? "speaking"
        : running
          ? "thinking"
          : state;
  const active =
    listening.current || speaking || running || state === "connecting";
  return (
    <div className="voice-panel">
      {voice && (
        <RoomContext.Provider value={voice.room}>
          <RoomAudioRenderer />
        </RoomContext.Provider>
      )}
      <button
        className="voice-orb-button"
        aria-label={
          listening.current
            ? "Send voice request"
            : active
              ? "Stop response"
              : "Start voice request"
        }
        aria-keyshortcuts="Space"
        title="Hold Space to speak; release to send. Or tap."
        aria-pressed={state === "listening"}
        disabled={!configured || !chatReady}
        onClick={tap}
      >
        <ParticlesOrb
          state={!configured || !chatReady ? "disabled" : displayed}
          levelRef={state === "listening" ? adapter?.levelRef : undefined}
          size={120}
          colorFrom="#274c67"
          colorTo="#ff6f00"
          label={displayed}
        />
        <span className="voice-orb-icon">{active && <Square size={17} />}</span>
      </button>
      <span className="voice-status" role="status">
        {state === "listening"
          ? spaceHeld.current
            ? "Listening · release Space to send"
            : "Listening · tap to send"
          : speaking
            ? "Speaking · tap to stop"
            : running
              ? "Working…"
              : state === "connecting"
                ? "Connecting…"
                : "Hold Space to speak · or tap"}
      </span>
      <button
        className="icon-button"
        aria-label={savedReply ? "Hear latest reply" : "Test speaker"}
        title={savedReply ? "Hear latest reply" : "Test speaker"}
        disabled={
          !configured ||
          state === "listening" ||
          state === "connecting" ||
          running
        }
        onClick={() => {
          setError("");
          void voice
            ?.speak(savedReply || "Pulse is ready. You can speak now.", true)
            .catch((e) => setError(e.message || "Could not play speech."));
        }}
      >
        <Volume2 size={17} />
      </button>
      {error && (
        <p className="voice-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
