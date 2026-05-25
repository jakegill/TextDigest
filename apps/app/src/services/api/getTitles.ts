import { auth } from "@/lib/firebase";

export async function getTitles() {
	try {
		await auth.authStateReady();
		const token = await auth.currentUser?.getIdToken();

		const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/titles`, {
			headers: { Authorization: `Bearer ${token}` },
		});

		if (res.ok) {
			const data = await res.json();
			return data;
		}
	} catch (e) {
		console.error("[getTitles]: ", e);
	}
}
