import { auth } from "@/lib/firebase";

export async function getPreferences() {
	try {
		await auth.authStateReady();
		const token = await auth.currentUser?.getIdToken();

		const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/preferences`, {
			headers: { Authorization: `Bearer ${token}` },
		});

		if (res.ok) {
			const data = await res.json();
			return data as { typeface: string; fontSize: number; isSpeedReaderMode: boolean };
		}
	} catch (e) {
		console.error("[getPreferences]: ", e);
	}
}
