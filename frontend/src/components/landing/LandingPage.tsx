"use client";
import Link from "next/link";
import PredictiveArcSignal from "./PredictiveArcSignal";

export function LandingPage() {
  return (
    <div className="landing-shell">
      <div className="landing-accent" aria-hidden="true" />
      <div className="landing-canvas" aria-hidden="true">
        <PredictiveArcSignal
          background="#20384a"
          baseColor="#274c67"
          accentColor="#2c5d81"
          highlight="#ff6f00"
          density={140}
          dotSize={90}
          speed={45}
          hover={100}
        />
      </div>
      <div className="landing-content">
        <div className="landing-title-block">
          <h1>Perschmann Hack</h1>
          <p>
            Know which customer to contact next, why now, and what to ask.
          </p>
        </div>
        <div className="landing-action">
          <Link href="/dashboard" className="landing-dashboard-button">
            Dashboard
          </Link>
        </div>
      </div>
    </div>
  );
}