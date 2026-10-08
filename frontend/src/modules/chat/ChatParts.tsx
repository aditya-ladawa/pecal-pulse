"use client";
import { memo } from "react";
import remarkGfm from "remark-gfm";
import {
  MessagePrimitive,
  groupPartByType,
  type ToolCallMessagePartProps,
} from "@assistant-ui/react";
import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";
import {
  Check,
  LoaderCircle,
  Wrench,
  AlertCircle,
  ChevronRight,
} from "lucide-react";

// assistant-ui GroupedParts recipe: use its part scopes/statuses and Markdown renderer.
// Native disclosures fit this project's CSS without installing another design system.
const ToolTrace = memo(function ToolTrace({
  toolName,
  argsText,
  result,
  status,
  isError,
}: Pick<
  ToolCallMessagePartProps,
  "toolName" | "argsText" | "result" | "status" | "isError"
>) {
  const running = status.type === "running";
  const failed = isError || status.type === "incomplete";
  return (
    <details className="tool-trace">
      <summary>
        {running ? (
          <LoaderCircle size={14} className="spin" />
        ) : failed ? (
          <AlertCircle size={14} />
        ) : (
          <Check size={14} />
        )}
        <span>
          {running ? "Running" : failed ? "Stopped" : "Used"} ·{" "}
          {toolName.replaceAll("_", " ")}
        </span>
        <ChevronRight size={13} className="disclosure-chevron" />
      </summary>
      <div className="trace-content">
        <small>Arguments</small>
        <pre>{argsText || "{}"}</pre>
        {result !== undefined && (
          <>
            <small>{isError ? "Error" : "Result"}</small>
            <pre>
              {typeof result === "string"
                ? result
                : JSON.stringify(result, null, 2)}
            </pre>
          </>
        )}
      </div>
    </details>
  );
});
const grouping = groupPartByType({
  "tool-call": ["group-tools"],
});
export function ChatParts() {
  return (
    <MessagePrimitive.GroupedParts groupBy={grouping}>
      {({ part, children }) => {
        // Reasoning is hidden by design; only tool calls are shown.
        if (part.type === "reasoning") return null;
        if (part.type === "group-tools")
          return (
            <div className="tool-group" aria-label="Tool calls">
              <div className="trace-heading">
                <Wrench size={13} /> Workspace tools
              </div>
              {children}
            </div>
          );
        if (part.type === "text")
          return (
            <MarkdownTextPrimitive
              className="markdown"
              remarkPlugins={[remarkGfm]}
            />
          );
        if (part.type === "tool-call")
          return part.toolUI ?? <ToolTrace {...part} />;
        return null;
      }}
    </MessagePrimitive.GroupedParts>
  );
}
