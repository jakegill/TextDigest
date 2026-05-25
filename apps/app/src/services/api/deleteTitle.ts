import { auth } from "@/lib/firebase";

export async function deleteTitle(titleId: string) {
	try {
		await auth.authStateReady();
		const token = await auth.currentUser?.getIdToken();

		const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/titles/${encodeURIComponent(titleId)}`, {
			method: "DELETE",
			headers: { Authorization: `Bearer ${token}` },
		});

		return res.ok;
	} catch (e) {
		console.error("[deleteTitle]: ", e);
	}
}
