import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { Info } from "lucide-react";
import { actionLabels } from "@/modules/sales/store";
import type { ActionType } from "@/types/sales";
export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "green" | "orange" | "purple";
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function ActionBadge({ action }: { action: ActionType }) {
  return (
    <Badge
      tone={
        action === "upcoming"
          ? "green"
          : action === "inactivity"
            ? "orange"
            : "purple"
      }
    >
      {actionLabels[action]}
    </Badge>
  );
}
export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={`card ${className}`}>{children}</section>;
}
export function InfoHint({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{
    top: number;
    left: number;
  } | null>(null);

  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const anchor = triggerRef.current?.getBoundingClientRect();
      const panel = panelRef.current;
      if (!anchor || !panel) return;
      const width = panel.offsetWidth;
      const height = panel.offsetHeight;
      const left = Math.max(
        8,
        Math.min(anchor.right - width, window.innerWidth - width - 8),
      );
      const below = anchor.bottom + 8;
      const top =
        below + height <= window.innerHeight - 8
          ? below
          : Math.max(8, anchor.top - height - 8);
      setPosition({ top, left });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (
        target instanceof Node &&
        !triggerRef.current?.contains(target) &&
        !panelRef.current?.contains(target)
      )
        setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <span className="info-hint">
      <button
        ref={triggerRef}
        type="button"
        className="info-hint-trigger"
        aria-label={`About ${label}`}
        aria-expanded={open}
        onClick={() => {
          setPosition(null);
          setOpen((value) => !value);
        }}
      >
        <Info size={16} />
      </button>
      {open &&
        createPortal(
          <div
            ref={panelRef}
            className="info-hint-popover"
            role="note"
            style={{
              top: position?.top ?? 0,
              left: position?.left ?? 0,
              visibility: position ? "visible" : "hidden",
            }}
          >
            {children}
          </div>,
          document.body,
        )}
    </span>
  );
}
export function Avatar({
  initials,
  index = 0,
  large = false,
}: {
  initials: string;
  index?: number;
  large?: boolean;
}) {
  return (
    <span
      className={`avatar color-${index % 4} ${large ? "large" : ""}`}
      aria-hidden="true"
    >
      {initials}
    </span>
  );
}
