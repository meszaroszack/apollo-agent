"use client";

import { useMemo } from "react";
import dynamic from "next/dynamic";

const Chart = dynamic(() => import("react-apexcharts"), { ssr: false });

export default function DivergenceChart({ decisions }: { decisions: any[] }) {
  const series = useMemo(() => {
    const points = decisions
      .filter((d) => d.p_true != null && d.p_market != null)
      .slice(-40)
      .map((d, i) => ({
        x: i,
        y: parseFloat(((d.p_market - d.p_true) * 100).toFixed(2)),
      }));
    return [{ name: "P_market - P_true (%)", data: points }];
  }, [decisions]);

  const options: ApexCharts.ApexOptions = {
    chart: {
      type: "bar",
      background: "transparent",
      toolbar: { show: false },
    },
    plotOptions: {
      bar: {
        colors: {
          ranges: [
            { from: 5, to: 100, color: "#ef4444" },   // >5% = NO-side opportunity
            { from: -100, to: -5, color: "#00d084" },  // <-5% = YES underpriced
            { from: -5, to: 5, color: "#52525a" },     // neutral
          ],
        },
        columnWidth: "70%",
      },
    },
    annotations: {
      yaxis: [
        { y: 5, borderColor: "#ef4444", strokeDashArray: 4, label: { text: "NO-side threshold", style: { color: "#ef4444", fontSize: "10px", fontFamily: "monospace", background: "transparent" } } },
        { y: -5, borderColor: "#00d084", strokeDashArray: 4, label: { text: "YES threshold", style: { color: "#00d084", fontSize: "10px", fontFamily: "monospace", background: "transparent" } } },
      ],
    },
    xaxis: {
      labels: { show: false },
      axisBorder: { color: "#2a2a2e" },
    },
    yaxis: {
      labels: {
        style: { colors: "#52525a", fontSize: "10px", fontFamily: "monospace" },
        formatter: (v) => `${v.toFixed(1)}%`,
      },
    },
    grid: { borderColor: "#1f1f23", strokeDashArray: 4 },
    tooltip: {
      theme: "dark",
      style: { fontFamily: "monospace", fontSize: "11px" },
      y: { formatter: (v) => `${v.toFixed(2)}% divergence` },
    },
  };

  return (
    <div className="panel" style={{ padding: "12px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
        <div className="text-xs font-mono" style={{ color: "var(--accent-amber)", letterSpacing: "0.1em" }}>
          BRACKET DIVERGENCE (P_market − P_true)
        </div>
        <div style={{ display: "flex", gap: "12px", fontSize: "10px" }}>
          <span style={{ color: "var(--accent-red)" }}>■ NO-side</span>
          <span style={{ color: "var(--accent-green)" }}>■ YES-side</span>
          <span style={{ color: "var(--text-muted)" }}>■ Neutral</span>
        </div>
      </div>
      {series[0].data.length > 0 ? (
        <Chart type="bar" series={series} options={options} height={160} width="100%" />
      ) : (
        <div style={{ height: 160, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)", fontSize: "11px" }}>
          No divergence data yet
        </div>
      )}
    </div>
  );
}
