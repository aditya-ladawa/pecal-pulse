"use client";
import { useEffect, useRef, useState } from "react";
import { ChartColumn, Maximize2, Minimize2 } from "lucide-react";
import { ArtifactChart } from "@/modules/artifacts/Chart";
import type { ChartArtifact } from "@/types/sales";

export function ChatArtifact({ artifact }: { artifact: ChartArtifact }) {
  const [expanded, setExpanded] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const maximize = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (expanded) dialog.current?.showModal();
  }, [expanded]);
  const minimize = () => {
    dialog.current?.close();
    setExpanded(false);
    maximize.current?.focus();
  };
  const source = `${artifact.source === "historical" ? "Historical observed" : "Synthetic"} ${artifact.unit}`;
  return (
    <div className="chat-artifact">
      <div className="chat-artifact-header">
        <ChartColumn size={14} />
        <strong>{artifact.title}</strong>
        <button
          ref={maximize}
          className="icon-button"
          type="button"
          aria-label={`Maximize ${artifact.title}`}
          title="Maximize chart"
          aria-haspopup="dialog"
          aria-expanded={expanded}
          onClick={() => setExpanded(true)}
        >
          <Maximize2 size={16} />
        </button>
      </div>
      <ArtifactChart artifact={artifact} compact />
      <small>{source}</small>
      {expanded && (
        <dialog
          ref={dialog}
          className="chat-chart-dialog"
          aria-label={artifact.title}
          onCancel={(event) => {
            event.preventDefault();
            minimize();
          }}
        >
          <div className="chat-chart-dialog-header">
            <div>
              <ChartColumn size={18} />
              <strong>{artifact.title}</strong>
            </div>
            <button
              type="button"
              className="icon-button"
              autoFocus
              aria-label={`Minimize ${artifact.title}`}
              title="Minimize chart"
              onClick={minimize}
            >
              <Minimize2 size={19} />
            </button>
          </div>
          <ArtifactChart artifact={artifact} />
          <small>{source}</small>
        </dialog>
      )}
    </div>
  );
}
