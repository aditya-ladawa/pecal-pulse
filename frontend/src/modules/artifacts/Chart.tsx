"use client";
import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { EChartsOption } from "echarts";
import type { ChartArtifact } from "@/types/sales";
const colors = ["#72966a", "#edb482", "#a9bad8", "#c6b5d7", "#a8c6b6"];
/** ECharts lifecycle adapted from the template's ArtifactView; no arbitrary JS. */
export function Chart({
  option,
  label,
  height = 260,
}: {
  option: EChartsOption;
  label: string;
  height?: number;
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
      axisLabel: { fontSize: 10 },
    },
    series: artifact.datasets.map((d) => ({
      name: d.name,
      type: artifact.kind,
      data: d.values,
      ...(artifact.kind === "bar"
        ? { barMaxWidth: 34, itemStyle: { borderRadius: [8, 8, 0, 0] } }
        : { smooth: true }),
    })),
  };
  return (
    <Chart
      option={option}
      label={`${artifact.title}. Synthetic ${artifact.unit}.`}
      height={compact ? 170 : 250}
    />
  );
}
