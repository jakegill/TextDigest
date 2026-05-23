"use client";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

export default function TitlesPage() {
  return (
    <input
      type="file"
      accept="application/pdf"
      onChange={async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        const fd = new FormData();
        fd.append("file", file);
        const res = await fetch(`${API_URL}/titles`, {
          method: "POST",
          body: fd,
        });
        console.log(await res.json());
      }}
    />
  );
}
