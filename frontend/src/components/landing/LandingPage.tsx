"use client";
import Link from "next/link";
import PredictiveArcSignal from "./PredictiveArcSignal";

export function LandingPage() {
  return (
    <div className="landing-shell">
      <div className="landing-accent" aria-hidden="true" />
      <div className="landing-canvas" aria-hidden="true">
        <PredictiveArcSignal
          background="#ffffff"
          baseColor="#274c67"
          accentColor="#2a5c80"
          highlight="#ff6f00"
          density={110}
          dotSize={130}
          speed={45}
          hover={100}
          signal={{
            level: 50,
            amplitude: 30,
            thickness: 95,
            wavelength: 72,
          }}
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