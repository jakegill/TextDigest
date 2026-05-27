import { auth } from "@/lib/firebase";

export async function getContentList(
	titleId: string,
	range: { startPage: number; endPage: number },
) {
	try {
		await auth.authStateReady();
		const token = await auth.currentUser?.getIdToken();

		const url = new URL(
			`${process.env.NEXT_PUBLIC_API_URL}/titles/${encodeURIComponent(titleId)}/content_list`,
		);
		url.searchParams.set("startPage", String(range.startPage));
		url.searchParams.set("endPage", String(range.endPage));

		const res = await fetch(url.toString(), {
			headers: { Authorization: `Bearer ${token}` },
		});

		if (res.ok) {
			const data = await res.json();
			return data;
		}
	} catch (e) {
		console.error("[getContentList]: ", e);
	}
}
