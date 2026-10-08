"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAui, useAuiState } from "@assistant-ui/react";
import { RoomAudioRenderer, RoomContext } from "@livekit/components-react";
import { Square, Volume2 } from "lucide-react";
import { ParticlesOrb } from "@/components/voiceorb/particles-orb";
import { createLiveKitAdapter } from "@/components/voiceorb/create-livekit-adapter";
import type { OrbState } from "@/components/voiceorb/orb-state";
import { useSalesStore } from "@/modules/sales/store";
import { pickAudioDevice } from "./audio-devices";
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
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [outputs, setOutputs] = useState<MediaDeviceInfo[]>([]);
  const [outputId, setOutputId] = useState("");
  // Speaker routing needs setSinkId (Chromium); Safari/Firefox follow the OS default.
  const outputSupported =
    typeof HTMLAudioElement !== "undefined" &&
    "setSinkId" in HTMLAudioElement.prototype;
  const [microphone, setMicrophone] = useState("");
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

  const refreshDevices = useCallback(async () => {
    try {
      const all = await navigator.mediaDevices?.enumerateDevices();
      if (!all)
        return { inputs: [], outputs: [], mic: "", spk: "" };
      const inputs = all.filter((d) => d.kind === "audioinput");
      const outs = all.filter((d) => d.kind === "audiooutput");
      setDevices(inputs);
      setOutputs(outs);
      // An explicit choice wins while plugged in; otherwise earphones
      // (e.g. OnePlus Buds 3) are picked automatically by label.
      const mic = pickAudioDevice(
        inputs.map((d) => ({ deviceId: d.deviceId, label: d.label || "" })),
        localStorage.getItem("pecal-voice-mic") || "",
      );
      const spk = pickAudioDevice(
        outs.map((d) => ({ deviceId: d.deviceId, label: d.label || "" })),
        localStorage.getItem("pecal-voice-speaker") || "",
      );
      setDeviceId(mic);
      setOutputId(spk);
      return { inputs, outputs: outs, mic, spk };
    } catch {
      return { inputs: [], outputs: [], mic: "", spk: "" };
    }
  }, []);

  useEffect(() => {
    void refreshDevices();
    const update = () => void refreshDevices();
    navigator.mediaDevices?.addEventListener("devicechange", update);
    return () =>
      navigator.mediaDevices?.removeEventListener("devicechange", update);
  }, [refreshDevices]);

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
    if (!voice || !outputId || !outputSupported) return;
    void voice
      .setOutput(outputId)
      .then((ok) => {
        if (!ok && mounted.current)
          setError(
            "This browser kept the system speaker. Use Chrome or Edge to route Pulse elsewhere.",
          );
      })
      .catch(() => {
        if (mounted.current) setError("Could not switch speaker output.");
      });
  }, [voice, outputId, outputSupported]);

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
      const { mic, spk } = await refreshDevices();
      if (
        !(await voice.start(mic)) ||
        !mounted.current ||
        epoch !== generation.current
      )
        return;
      if (spk && outputSupported)
        await voice.setOutput(spk).catch(() => {});
      listening.current = true;
      setState("listening");
      adapter?.setTrack({ publication: voice.microphone() });
      setMicrophone(
        voice.microphone()?.track?.mediaStreamTrack.label || "Microphone",
      );
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
      {microphone &&
        (devices.length > 1 ? (
          <select
            className="voice-input-select"
            aria-label="Microphone input"
            title="Microphone for the next voice turn"
            value={deviceId}
            disabled={active}
            onChange={(e) => {
              const id = e.target.value;
              setDeviceId(id);
              if (id) localStorage.setItem("pecal-voice-mic", id);
              else localStorage.removeItem("pecal-voice-mic");
            }}
          >
            <option value="">Default · {microphone}</option>
            {devices
              .filter((d) => d.deviceId !== "default")
              .map((d) => (
                <option key={d.deviceId} value={d.deviceId}>
                  {d.label || "Microphone"}
                </option>
              ))}
          </select>
        ) : (
          <span className="voice-input-name">{microphone}</span>
        ))}
      {outputSupported &&
        (outputs.length > 1 ? (
          <select
            className="voice-input-select"
            aria-label="Speaker output"
            title="Where Pulse's speech plays"
            value={outputId}
            disabled={active}
            onChange={(e) => {
              const id = e.target.value;
              setOutputId(id);
              if (id) localStorage.setItem("pecal-voice-speaker", id);
              else localStorage.removeItem("pecal-voice-speaker");
            }}
          >
            <option value="">Speakers · System default</option>
            {outputs
              .filter((d) => d.deviceId)
              .map((d) => (
                <option key={d.deviceId} value={d.deviceId}>
                  {d.label || "Speaker"}
                </option>
              ))}
          </select>
        ) : null)}
      {error && (
        <p className="voice-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
