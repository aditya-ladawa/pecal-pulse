"use client";
import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { EChartsOption } from "echarts";
import type { ChartArtifact } from "@/types/sales";
const colors = ["#72966a", "#edb482", "#a9bad8", "#c6b5d7", "#a8c6b6"];
/**
 * Axis tick labels: at most two decimals with trailing zeros trimmed, so
 * ticks read 12.5 / 12.34 / 12 instead of 12.5000000001 or 12.00.
 */
export function axisNumber(value: number): string {
  if (!Number.isFinite(value)) return "";
  return Number(value.toFixed(2)).toLocaleString(undefined, {
    maximumFractionDigits: 2,
  });
}
/** Fraction 0–1 as a percent label with at most two decimals: 0.48 → 48%. */
export function axisPercent(value: number): string {
  if (!Number.isFinite(value)) return "";
  return `${Number((value * 100).toFixed(2))}%`;
}
/** ECharts lifecycle adapted from the template's ArtifactView; no arbitrary JS. */
export function Chart({
  option,
  label,
  height = 260,
  onClick,
}: {
  option: EChartsOption;
  label: string;
  height?: number;
  onClick?: (params: { data?: unknown; seriesName?: string }) => void;
}) {
  const element = useRef<HTMLDivElement>(null),
    instance = useRef<echarts.ECharts | null>(null);
  useEffect(() => {
    if (!element.current) return;
    const chart = echarts.init(element.current);
    instance.current = chart;
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(element.current);
    return () => {
      observer.disconnect();
      chart.dispose();
      instance.current = null;
    };
  }, []);
  useEffect(() => {
    instance.current?.setOption(
      {
        color: colors,
        textStyle: { fontFamily: "inherit", color: "#778073" },
        animationDuration: 500,
        ...option,
      },
      { notMerge: true },
    );
  }, [option]);
  useEffect(() => {
    const chart = instance.current;
    if (!chart || !onClick) return;
    chart.on("click", onClick);
    return () => {
      chart.off("click", onClick);
    };
  }, [onClick]);
  return (
    <div
      role="img"
      aria-label={label}
      ref={element}
      className="chart"
      style={{ height }}
    />
  );
}
export function ArtifactChart({
  artifact,
  compact = false,
}: {
  artifact: ChartArtifact;
  compact?: boolean;
}) {
  if (artifact.kind === "heatmap")
    return (
      <Chart
        label={artifact.title + ". Descriptive correlation, not causation."}
        height={compact ? 250 : 450}
        option={{
          tooltip: { trigger: "item" },
          grid: { left: 125, right: 25, top: 20, bottom: 120 },
          xAxis: {
            type: "category",
            data: artifact.labels,
            axisLabel: { rotate: 55, fontSize: 9 },
          },
          yAxis: {
            type: "category",
            data: artifact.datasets.map((d) => d.name),
            axisLabel: { fontSize: 9 },
          },
          visualMap: {
            min: -1,
            max: 1,
            show: false,
            inRange: { color: ["#edb482", "#f5f5ec", "#72966a"] },
          },
          series: [
            {
              type: "heatmap",
              data: artifact.datasets.flatMap((d, y) =>
                d.values.flatMap((v, x) => (v == null ? [] : [[x, y, v]])),
              ),
            },
          ],
        }}
      />
    );
  const option: EChartsOption = {
    tooltip: {
      trigger: "axis",
      valueFormatter: (value) => `${value} ${artifact.unit}`,
    },
    grid: { left: 42, right: 15, top: 25, bottom: 55 },
    xAxis: {
      type: "category",
      data: artifact.labels,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        fontSize: 10,
        interval: 0,
        formatter: (v: string) => {
          const limit = compact ? 6 : 13;
          return v.length > limit ? v.slice(0, limit - 1) + "…" : v;
        },
      },
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: "#edf0e9" } },
      axisLabel: { fontSize: 10, formatter: axisNumber },
    },
    series: artifact.datasets.map((d) => ({
      name: d.name,
      type: artifact.kind === "bar" ? ("bar" as const) : ("line" as const),
      data: d.values,
      ...(artifact.kind === "bar"
        ? { barMaxWidth: 34, itemStyle: { borderRadius: [8, 8, 0, 0] } }
        : { smooth: true }),
    })),
  };
  return (
    <Chart
      option={option}
      label={`${artifact.title}. ${artifact.source === "historical" ? "Historical observed" : "Synthetic"} ${artifact.unit}.`}
      height={compact ? 170 : 250}
    />
  );
}
