"use client";
import { useState } from "react";
import { Copy, Mail } from "lucide-react";
import type { Followup } from "@/types/sales";

export function FollowupEmail({
  draft,
}: {
  draft: NonNullable<Followup["email_draft"]>;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <details className="followup-email">
      <summary>
        <Mail size={16} /> Email draft · {draft.subject}
      </summary>
      <div className="followup-email-content">
        <div className="card-heading">
          <strong>{draft.subject}</strong>
          <button
            className="button"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(
                  `Subject: ${draft.subject}\n\n${draft.body}`,
                );
                setCopied(true);
              } catch {
                setCopied(false);
              }
            }}
          >
            <Copy size={14} />
            {copied ? "Copied" : "Copy email"}
          </button>
        </div>
        <p className="email-body">{draft.body}</p>
        <div className="email-review">
          <strong>Before sending</strong>
          <ul>
            {draft.review_notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </div>
      </div>
    </details>
  );
}
