import { auth } from "@/lib/firebase";

export async function postFindTitleConversation(
	conversationId: string,
	body: { firstMessage: string },
) {
	try {
		await auth.authStateReady();
		const token = await auth.currentUser?.getIdToken();

		const res = await fetch(
			`${process.env.NEXT_PUBLIC_API_URL}/agents/title-finder/conversations/${encodeURIComponent(conversationId)}`,
			{
				method: "POST",
				headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
				body: JSON.stringify(body),
			},
		);

		if (res.ok) {
			const data = (await res.json()) as { title: string };
			return data;
		}
	} catch (e) {
		console.error("[postFindTitleConversation]: ", e);
	}
}
