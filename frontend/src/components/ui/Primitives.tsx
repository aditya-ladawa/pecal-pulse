import type { ReactNode } from "react";
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
