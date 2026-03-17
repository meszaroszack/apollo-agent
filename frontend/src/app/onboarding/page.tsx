"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { createSession, SessionCreatePayload } from "@/lib/api";
import { useApolloStore } from "@/lib/store";

export default function OnboardingPage() {
  const router = useRouter();
  const setSession = useApolloStore((s) => s.setSession);
  const [loading, setLoading] = useState(false);

  const [form, setForm] = useState<SessionCreatePayload & { enablePerplexity: boolean }>({
    kalshi_key_id: "",
    kalshi_private_key: "",
    perplexity_api_key: "",
    balldontlie_api_key: "",
    bankroll_usd: 1000,
    dry_run: true,
    enablePerplexity: false,
  });

  const update = (k: string, v: string | number | boolean) =>
    setForm((f) => ({ ...f, [k]: v }));

  const handleKeyFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (evt) => {
      update("kalshi_private_key", evt.target?.result as string);
    };
    reader.readAsText(file);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.kalshi_key_id || !form.kalshi_private_key) {
      toast.error("Kalshi Key ID and Private Key are required");
      return;
    }

    setLoading(true);
    try {
      const payload: SessionCreatePayload = {
        kalshi_key_id: form.kalshi_key_id.trim(),
        kalshi_private_key: form.kalshi_private_key.trim(),
        balldontlie_api_key: form.balldontlie_api_key ? form.balldontlie_api_key.trim() : undefined,
        bankroll_usd: Number(form.bankroll_usd),
        dry_run: form.dry_run,
        perplexity_api_key: form.enablePerplexity ? form.perplexity_api_key : undefined,
      };

      const result = await createSession(payload);
      setSession({
        sessionId: result.session_id,
        dryRun: result.dry_run,
        sentimentEnabled: result.sentiment_enabled,
        bankrollUsd: payload.bankroll_usd,
      });
      toast.success("Session established — routing to dashboard");
      router.replace("/dashboard");
    } catch (err: any) {
      toast.error(`Session failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6"
         style={{ background: "var(--bg-base)" }}>
      <div className="w-full max-w-2xl">
        {/* Header */}
        <div className="mb-8 text-center">
          <div style={{ color: "var(--accent-green)" }} className="font-mono text-xs tracking-widest mb-2">
            ◆ APOLLO-AGENT BRACKET EDITION
          </div>
          <h1 className="text-xl font-mono" style={{ color: "var(--text-primary)" }}>
            Secure Credential Onboarding
          </h1>
          <p className="text-xs mt-2" style={{ color: "var(--text-secondary)" }}>
            Keys are stored in memory only — never persisted to disk or database
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="space-y-4">

            {/* Kalshi Key ID */}
            <div className="panel p-4">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xs font-mono" style={{ color: "var(--accent-amber)" }}>
                  KALSHI
                </span>
                <div style={{ background: "var(--border)", height: "1px", flex: 1 }} />
              </div>

              <div className="space-y-3">
                <div>
                  <label className="block text-xs mb-1" style={{ color: "var(--text-secondary)" }}>
                    ACCESS KEY ID (UUID)
                  </label>
                  <input
                    type="text"
                    placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                    value={form.kalshi_key_id}
                    onChange={(e) => update("kalshi_key_id", e.target.value)}
                    className="w-full p-2 text-xs font-mono rounded"
                    style={{
                      background: "var(--bg-elevated)",
                      border: "1px solid var(--border)",
                      color: "var(--text-primary)",
                      outline: "none",
                    }}
                  />
                </div>

                <div>
                  <label className="block text-xs mb-1" style={{ color: "var(--text-secondary)" }}>
                    PRIVATE KEY (.key file) — Upload or paste PEM
                  </label>
                  <div className="flex gap-2">
                    <input
                      type="file"
                      accept=".key,.pem"
                      onChange={handleKeyFile}
                      className="hidden"
                      id="key-file"
                    />
                    <label
                      htmlFor="key-file"
                      className="px-3 py-2 text-xs font-mono cursor-pointer rounded"
                      style={{
                        background: "var(--bg-elevated)",
                        border: "1px solid var(--border)",
                        color: "var(--accent-green)",
                        whiteSpace: "nowrap",
                      }}
                    >
                      Upload .key
                    </label>
                    <textarea
                      rows={4}
                      placeholder="-----BEGIN RSA PRIVATE KEY-----&#10;...&#10;-----END RSA PRIVATE KEY-----"
                      value={form.kalshi_private_key}
                      onChange={(e) => update("kalshi_private_key", e.target.value)}
                      className="flex-1 p-2 text-xs font-mono rounded resize-none"
                      style={{
                        background: "var(--bg-elevated)",
                        border: form.kalshi_private_key ? "1px solid var(--accent-green-dim)" : "1px solid var(--border)",
                        color: "var(--text-primary)",
                        outline: "none",
                      }}
                    />
                  </div>
                  {form.kalshi_private_key && (
                    <div className="mt-1 text-xs" style={{ color: "var(--accent-green)" }}>
                      ✓ Key loaded ({form.kalshi_private_key.split("\n").length} lines)
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* BALLDONTLIE */}
            <div className="panel p-4">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xs font-mono" style={{ color: "var(--accent-blue)" }}>
                  BALLDONTLIE
                </span>
                <div style={{ background: "var(--border)", height: "1px", flex: 1 }} />
                <span className="text-xs" style={{ color: "var(--text-muted)" }}>OPTIONAL — enhances rebound signal</span>
              </div>
              <input
                type="text"
                placeholder="bdl_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                value={form.balldontlie_api_key}
                onChange={(e) => update("balldontlie_api_key", e.target.value)}
                className="w-full p-2 text-xs font-mono rounded"
                style={{
                  background: "var(--bg-elevated)",
                  border: "1px solid var(--border)",
                  color: "var(--text-primary)",
                  outline: "none",
                }}
              />
            </div>

            {/* Perplexity toggle */}
            <div className="panel p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono" style={{ color: "var(--accent-purple)" }}>
                    PERPLEXITY SENTIMENT GUARDRAIL
                  </span>
                  <span className="text-xs px-1.5 py-0.5 rounded" style={{
                    background: "rgba(168,85,247,0.15)",
                    color: "var(--accent-purple)",
                    border: "1px solid rgba(168,85,247,0.3)"
                  }}>OPTIONAL</span>
                </div>
                {/* Toggle switch */}
                <button
                  type="button"
                  onClick={() => update("enablePerplexity", !form.enablePerplexity)}
                  className="relative w-10 h-5 rounded-full transition-colors"
                  style={{
                    background: form.enablePerplexity ? "var(--accent-green)" : "var(--border)",
                  }}
                >
                  <span
                    className="absolute top-0.5 w-4 h-4 rounded-full transition-all"
                    style={{
                      background: "var(--text-primary)",
                      left: form.enablePerplexity ? "calc(100% - 18px)" : "2px",
                    }}
                  />
                </button>
              </div>

              {form.enablePerplexity && (
                <div>
                  <p className="text-xs mb-2" style={{ color: "var(--text-secondary)" }}>
                    Aborts trade if sentiment score &lt; -0.4 (injury reports, locker-room issues)
                  </p>
                  <input
                    type="text"
                    placeholder="pplx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                    value={form.perplexity_api_key}
                    onChange={(e) => update("perplexity_api_key", e.target.value)}
                    className="w-full p-2 text-xs font-mono rounded"
                    style={{
                      background: "var(--bg-elevated)",
                      border: "1px solid var(--border)",
                      color: "var(--text-primary)",
                      outline: "none",
                    }}
                  />
                </div>
              )}
            </div>

            {/* Risk config */}
            <div className="panel p-4">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xs font-mono" style={{ color: "var(--accent-amber)" }}>
                  RISK CONFIGURATION
                </span>
                <div style={{ background: "var(--border)", height: "1px", flex: 1 }} />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs mb-1" style={{ color: "var(--text-secondary)" }}>
                    BANKROLL (USD)
                  </label>
                  <input
                    type="number"
                    min="10"
                    step="100"
                    value={form.bankroll_usd}
                    onChange={(e) => update("bankroll_usd", Number(e.target.value))}
                    className="w-full p-2 text-xs font-mono rounded"
                    style={{
                      background: "var(--bg-elevated)",
                      border: "1px solid var(--border)",
                      color: "var(--text-primary)",
                      outline: "none",
                    }}
                  />
                  <div className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                    Max per trade: ${(form.bankroll_usd * 0.03).toFixed(2)} (3%)
                  </div>
                </div>

                <div>
                  <label className="block text-xs mb-1" style={{ color: "var(--text-secondary)" }}>
                    EXECUTION MODE
                  </label>
                  <div className="flex gap-2">
                    {[true, false].map((isDry) => (
                      <button
                        key={String(isDry)}
                        type="button"
                        onClick={() => update("dry_run", isDry)}
                        className="flex-1 py-2 text-xs font-mono rounded transition-colors"
                        style={{
                          background: form.dry_run === isDry ? (isDry ? "rgba(59,130,246,0.2)" : "rgba(239,68,68,0.2)") : "var(--bg-elevated)",
                          border: form.dry_run === isDry
                            ? `1px solid ${isDry ? "var(--accent-blue)" : "var(--accent-red)"}`
                            : "1px solid var(--border)",
                          color: form.dry_run === isDry ? (isDry ? "var(--accent-blue)" : "var(--accent-red)") : "var(--text-muted)",
                        }}
                      >
                        {isDry ? "SIM" : "LIVE"}
                      </button>
                    ))}
                  </div>
                  {!form.dry_run && (
                    <div className="text-xs mt-1" style={{ color: "var(--accent-red)" }}>
                      ⚠ Real orders will be submitted
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 text-sm font-mono rounded transition-all"
              style={{
                background: loading ? "var(--bg-elevated)" : "var(--accent-green)",
                color: loading ? "var(--text-muted)" : "var(--text-inverse)",
                border: "none",
                cursor: loading ? "not-allowed" : "pointer",
                fontWeight: "700",
                letterSpacing: "0.1em",
              }}
            >
              {loading ? "ESTABLISHING SESSION..." : "LAUNCH APOLLO-AGENT →"}
            </button>
          </div>
        </form>

        <div className="mt-6 text-center text-xs" style={{ color: "var(--text-muted)" }}>
          Quarter-Kelly (0.25x) · 3% max per contract · 0.1% halt threshold · RSA-PSS signed
        </div>
      </div>
    </div>
  );
}
