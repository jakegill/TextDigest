import { auth } from "@/lib/firebase";

export async function ingestFoundTitle(body: {
	taskId: string;
	sourceKey: string;
	filename?: string;
}) {
	try {
		await auth.authStateReady();
		const token = await auth.currentUser?.getIdToken();
		const res = await fetch(
			`${process.env.NEXT_PUBLIC_API_URL}/agents/title-finder/ingest`,
			{
				method: "POST",
				headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
				body: JSON.stringify(body),
			},
		);
		if (res.ok) {
			return (await res.json()) as { taskId: string };
		}
	} catch (e) {
		console.error("[ingestFoundTitle]: ", e);
	}
}
