"use client";

import { onAuthStateChanged } from "firebase/auth";
import { useEffect, useState } from "react";

import { auth } from "@/lib/firebase";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

export default function Home() {
  const [status, setStatus] = useState<string>("loading…");

  useEffect(() => {
    return onAuthStateChanged(auth, async (user) => {
      try {
        const headers: HeadersInit = {};
        if (user) {
          const token = await user.getIdToken();
          headers.Authorization = `Bearer ${token}`;
        }
        const res = await fetch(`${API_URL}/health`, { headers });
        setStatus(JSON.stringify(await res.json()));
      } catch (err) {
        setStatus(`error: ${String(err)}`);
      }
    });
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
