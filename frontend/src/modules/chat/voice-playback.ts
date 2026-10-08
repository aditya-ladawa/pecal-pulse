export type SpeechJob = { text: string; kind?: "progress" | "final" | "error" };

/** Serialize speech: new tool progress must not abort audio already playing. */
export class VoicePlayback {
  private context: AudioContext | null = null;
  private queue: SpeechJob[] = [];
  private abort: AbortController | null = null;
  private epoch = 0;
  private pumping: number | null = null;

  constructor(
    private options: {
      synthesize: (text: string, signal: AbortSignal) => Promise<ArrayBuffer>;
      onState: (state: "connecting" | "speaking" | "idle") => void;
      onError: (message: string) => void;
      createContext?: () => AudioContext;
    },
  ) {}

  async unlock() {
    if (!this.context || this.context.state === "closed")
      this.context = this.options.createContext?.() ?? new AudioContext();
    await this.context.resume();
    if (this.context.state !== "running")
      throw new Error(
        "Browser audio is paused. Tap Hear latest reply to enable sound.",
      );
  }

  enqueue(job: SpeechJob) {
    if (!job.text.trim()) return;
    // Keep one pending progress summary; a final/error reply replaces stale progress.
    if (job.kind === "progress") {
      this.queue = this.queue.filter((item) => item.kind !== "progress");
      this.queue.push(job);
    } else this.queue = [job];
    void this.drain();
  }

  cancel() {
    this.epoch++;
    this.queue = [];
    this.abort?.abort();
    this.abort = null;
    this.pumping = null;
  }

  close() {
    this.cancel();
    void this.context?.close();
    this.context = null;
  }

  private async drain() {
    const epoch = this.epoch;
    if (this.pumping === epoch) return;
    this.pumping = epoch;
    try {
      while (this.queue.length && epoch === this.epoch) {
        const job = this.queue.shift()!;
        const abort = new AbortController();
        this.abort = abort;
        try {
          this.options.onState("connecting");
          const data = await this.options.synthesize(
            job.text.slice(0, 12000),
            abort.signal,
          );
          if (abort.signal.aborted || epoch !== this.epoch) return;
          await this.unlock();
          if (abort.signal.aborted || epoch !== this.epoch || !this.context)
            return;
          const buffer = await this.context.decodeAudioData(data);
          if (abort.signal.aborted || epoch !== this.epoch) return;
          const audio = this.context.createBufferSource();
          audio.buffer = buffer;
          audio.connect(this.context.destination);
          this.options.onState("speaking");
          await new Promise<void>((resolve) => {
            audio.onended = () => resolve();
            abort.signal.addEventListener(
              "abort",
              () => {
                try {
                  audio.stop();
                } catch {
                  /* already ended */
                }
                resolve();
              },
              { once: true },
            );
            audio.start();
          });
        } catch (error) {
          if (!abort.signal.aborted && epoch === this.epoch) {
            this.options.onError(
              error instanceof Error
                ? error.message
                : "Could not play speech. Tap Hear reply to try again.",
            );
          }
        }
      }
    } finally {
      if (this.pumping === epoch) {
        this.pumping = null;
        this.abort = null;
        this.options.onState("idle");
      }
    }
  }
}
