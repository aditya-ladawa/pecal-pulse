"use client";
import { useReducedMotion } from "motion/react";
import CountUp from "./react-bits/CountUp";
export function AnimatedNumber({ value }: { value: number }) {
  const reduced = useReducedMotion();
  return (
    <>
      <span aria-hidden="true">
        {reduced ? value : <CountUp to={value} duration={0.7} separator="," />}
      </span>
      <span className="sr-only">{value}</span>
    </>
  );
}
