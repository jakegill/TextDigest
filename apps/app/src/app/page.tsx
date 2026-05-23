"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

export default function Home() {
  const [status, setStatus] = useState<string>("loading…");

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((r) => r.json())
      .then((data) => setStatus(JSON.stringify(data)))
      .catch((err) => setStatus(`error: ${String(err)}`));
  }, []);

  return (
    <main className="flex flex-1 items-center justify-center p-16 font-mono">
      <div>
        <h1 className="text-2xl font-semibold">text-digest-v2</h1>
        <p className="mt-4">
          api <code>{API_URL}/health</code> → <code>{status}</code>
        </p>
      </div>
    </main>
  );
}
