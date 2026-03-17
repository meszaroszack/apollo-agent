"use client";

import { useMemo } from "react";
import dynamic from "next/dynamic";

const Chart = dynamic(() => import("react-apexcharts"), { ssr: false });

export default function PnLChart({ decisions }: { decisions: any[] }) {
  const series = useMemo(() => {
    let cumulative = 0;
    const data = decisions
      .filter((d) => d.executed && d.position_dollars)
      .map((d, i) => {
        const pnl = d.abort_reason ? -d.position_dollars * 0.1 : d.position_dollars * (d.edge || 0);
        cumulative += pnl;
        return { x: new Date(d.timestamp).getTime(), y: parseFloat(cumulative.toFixed(2)) };
      });
    return [{ name: "Cumulative P&L", data }];
  }, [decisions]);

  const options: ApexCharts.ApexOptions = {
    chart: {
      type: "area",
      background: "transparent",
      toolbar: { show: false },
      zoom: { enabled: false },
      animations: { enabled: true, speed: 300 },
    },
    stroke: { curve: "stepline", width: 2, colors: ["#00d084"] },
    fill: {
      type: "gradient",
      gradient: {
        shadeIntensity: 1,
        opacityFrom: 0.3,
        opacityTo: 0.02,
        stops: [0, 100],
        colorStops: [{ offset: 0, color: "#00d084", opacity: 0.3 }, { offset: 100, color: "#00d084", opacity: 0 }],
      },
    },
    xaxis: {
      type: "datetime",
      labels: { style: { colors: "#52525a", fontSize: "10px", fontFamily: "monospace" } },
      axisBorder: { color: "#2a2a2e" },
      axisTicks: { color: "#2a2a2e" },
    },
    yaxis: {
      labels: {
        style: { colors: "#52525a", fontSize: "10px", fontFamily: "monospace" },
        formatter: (v) => `$${v.toFixed(2)}`,
      },
    },
    grid: { borderColor: "#1f1f23", strokeDashArray: 4 },
    tooltip: {
      theme: "dark",
      x: { format: "MMM dd HH:mm" },
      style: { fontFamily: "monospace", fontSize: "11px" },
    },
    markers: { size: 0 },
  };

  return (
    <div className="panel" style={{ padding: "12px" }}>
      <div className="text-xs font-mono mb-2" style={{ color: "var(--accent-green)", letterSpacing: "0.1em" }}>
        CUMULATIVE P&L
      </div>
      {series[0].data.length > 0 ? (
        <Chart type="area" series={series} options={options} height={180} width="100%" />
      ) : (
        <div style={{ height: 180, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)", fontSize: "11px" }}>
          No trade history yet
        </div>
      )}
    </div>
  );
}
