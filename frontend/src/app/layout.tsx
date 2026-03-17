import type { Metadata } from "next";
import "./globals.css";
import { Toaster } from "sonner";

export const metadata: Metadata = {
  title: "Apollo-Agent | NCAAB Prediction Market HFT",
  description: "Institutional-grade quantitative trading for Kalshi NCAAB bracket contracts",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {children}
        <Toaster
          theme="dark"
          position="bottom-right"
          toastOptions={{
            style: {
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              color: "var(--text-primary)",
              fontFamily: "monospace",
              fontSize: "12px",
            },
          }}
        />
      </body>
    </html>
  );
}
