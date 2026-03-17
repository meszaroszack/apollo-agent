"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useApolloStore } from "@/lib/store";

export default function Home() {
  const router = useRouter();
  const sessionId = useApolloStore((s) => s.sessionId);

  useEffect(() => {
    if (sessionId) {
      router.replace("/dashboard");
    } else {
      router.replace("/onboarding");
    }
  }, [sessionId, router]);

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--bg-base)" }}>
      <div style={{ color: "var(--accent-green)" }} className="font-mono text-sm">
        APOLLO-AGENT initializing...
      </div>
    </div>
  );
}
