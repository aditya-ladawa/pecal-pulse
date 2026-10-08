"use client";

import { useEffect } from "react";
import {
  animate,
  AnimatePresence,
  motion,
  useReducedMotion,
} from "motion/react";
import { Sparkles } from "lucide-react";
import { useSalesStore } from "@/modules/sales/store";

const targets = {
  navigation: ".workspace-topnav .nav-link.active",
  filters: ".opportunity-filters, .integrated-filters",
  customer: ".opportunity-drawer-header, .integrated-account.selected",
  controls:
    ".customer-tabs, .opportunity-map .card-heading, .opportunity-filters",
  workflow: ".page-content .followup-email",
};

export function AgentFeedback() {
  const feedback = useSalesStore((s) => s.agentFeedback);
  const set = useSalesStore((s) => s.set);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (!feedback) return;
    // Wait for the same-frame store updates to paint; never animate chart points.
    const frame = requestAnimationFrame(() => {
      if (reduced) return;
      document
        .querySelectorAll<HTMLElement>(targets[feedback.target])
        .forEach((element) => {
          animate(
            element,
            {
              boxShadow: [
                "0 0 0 0 rgba(200,106,48,0)",
                "0 0 0 4px rgba(200,106,48,0.24)",
                "0 0 0 0 rgba(200,106,48,0)",
              ],
            },
            { duration: 1.1 },
          );
        });
    });
    const timer = setTimeout(() => {
      if (useSalesStore.getState().agentFeedback?.id === feedback.id)
        set({ agentFeedback: null });
    }, 3500);
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(timer);
    };
  }, [feedback, reduced, set]);
  return (
    <AnimatePresence>
      {feedback && (
        <motion.div
          key={feedback.id}
          className="agent-action-feedback"
          role="status"
          initial={reduced ? false : { opacity: 0, marginTop: -6 }}
          animate={{ opacity: 1, marginTop: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: reduced ? 0 : 0.2 }}
        >
          <Sparkles size={15} />
          {feedback.label}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
