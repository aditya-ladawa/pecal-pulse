import { ConnectionState, Room, RoomEvent, Track } from "livekit-client";

// livekit-client measures responseTimeout in milliseconds (default 15000,
// floored at 8000). A seconds-scale value here times out every RPC instantly.
const RPC_TIMEOUT_MS = 15000;
// end_turn waits on cloud transcription, so it carries a longer budget.
const END_TURN_TIMEOUT_MS = 30000;

/** One warm WebRTC session; audio is streamed while Space is held. */
export class LiveKitVoice {
  readonly room = new Room({
    audioCaptureDefaults: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
    publishDefaults: { stopMicTrackOnMute: true },
  });
  readonly sessionId = crypto.randomUUID();
  private connecting: Promise<void> | null = null;
  private agentIdentity = "pulse-voice";
  private epoch = 0;
  private turnId: string | undefined;
  private closed = false;
  private recording = false;

  constructor(
    private callbacks: {
      onSpeaking: (speaking: boolean) => void;
      onError: (message: string) => void;
    },
  ) {
    this.room.on(RoomEvent.ParticipantAttributesChanged, (attributes) => {
      if ("lk.agent.state" in attributes)
        callbacks.onSpeaking(attributes["lk.agent.state"] === "speaking");
    });
    this.room.on(RoomEvent.DataReceived, (data, participant) => {
      if (participant?.identity !== this.agentIdentity) return;
      try {
        const event = JSON.parse(new TextDecoder().decode(data));
        if (event.type === "voice.error") callbacks.onError(event.message);
      } catch {
        /* unrelated room data */
      }
    });
    this.room.on(RoomEvent.Disconnected, () => {
      if (!this.closed)
        callbacks.onError("Voice disconnected. Tap the orb to reconnect.");
    });
  }

  private rpc(method: string, payload = "", responseTimeout = RPC_TIMEOUT_MS) {
    return this.room.localParticipant.performRpc({
      destinationIdentity: this.agentIdentity,
      method,
      payload,
      responseTimeout,
    });
  }

  async connect() {
    if (this.room.state === ConnectionState.Connected) return;
    if (!this.connecting) {
      this.connecting = (async () => {
        const response = await fetch("/api/sales/voice/connect", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: this.sessionId }),
        });
        const body = await response.json();
        if (!response.ok)
          throw new Error(body.detail || "Could not connect voice.");
        if (this.closed) return;
        this.agentIdentity = body.agent_identity;
        await this.room.connect(body.server_url, body.token);
        if (this.closed) await this.room.disconnect();
      })().finally(() => {
        this.connecting = null;
      });
    }
    await this.connecting;
  }

  async start(deviceId: string) {
    const epoch = ++this.epoch;
    // Called synchronously from the user's gesture, before network awaits.
    void this.room.startAudio().catch(() => {});
    await this.connect();
    if (this.closed || epoch !== this.epoch) return false;
    await this.rpc("start_turn");
    if (this.closed || epoch !== this.epoch) {
      await this.rpc("interrupt").catch(() => {});
      return false;
    }
    await this.room.localParticipant.setMicrophoneEnabled(
      true,
      deviceId ? { deviceId: { exact: deviceId } } : undefined,
    );
    if (this.closed || epoch !== this.epoch) {
      await this.room.localParticipant.setMicrophoneEnabled(false);
      await this.rpc("interrupt").catch(() => {});
      return false;
    }
    this.recording = true;
    return true;
  }

  async finish() {
    if (!this.recording) return null;
    this.recording = false;
    const epoch = this.epoch;
    await this.room.localParticipant.setMicrophoneEnabled(false);
    const response = JSON.parse(
      await this.rpc("end_turn", "", END_TURN_TIMEOUT_MS),
    ) as {
      text: string;
      turn_id: string;
    };
    if (this.closed || epoch !== this.epoch) return null;
    this.turnId = response.turn_id;
    return response.text;
  }

  async speak(text: string, replay = false) {
    void this.room.startAudio().catch(() => {});
    await this.connect();
    if (!this.closed)
      await this.rpc(
        "speak",
        JSON.stringify({
          text: text.slice(0, 12000),
          turn_id: replay ? undefined : this.turnId,
        }),
      );
  }

  async cancel() {
    this.epoch++;
    this.recording = false;
    this.turnId = undefined;
    if (this.room.state === ConnectionState.Connected) {
      await this.room.localParticipant.setMicrophoneEnabled(false);
      await this.rpc("interrupt").catch(() => {});
    }
  }

  microphone() {
    return this.room.localParticipant.getTrackPublication(
      Track.Source.Microphone,
    );
  }

  close() {
    this.closed = true;
    this.epoch++;
    void this.room.disconnect();
    // Works on normal unmount and page dismissal; no secrets in the body.
    void fetch("/api/sales/voice/stop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: this.sessionId }),
      keepalive: true,
    }).catch(() => {});
  }
}
