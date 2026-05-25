import { auth } from "@/lib/firebase";

export async function putTitle(titleId: string, body: { pageNumber?: number; lastViewed?: string }) {
	try {
		await auth.authStateReady();
		const token = await auth.currentUser?.getIdToken();

		const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/titles/${encodeURIComponent(titleId)}`, {
			method: "PUT",
			headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
			body: JSON.stringify(body),
		});

		if (res.ok) {
			return true;
		}
	} catch (e) {
		console.error("[putTitle]: ", e);
	}
}
