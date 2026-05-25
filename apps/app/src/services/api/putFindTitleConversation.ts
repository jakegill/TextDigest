import { auth } from "@/lib/firebase";

export async function putFindTitleConversation(conversationId: string) {
	try {
		await auth.authStateReady();
		const token = await auth.currentUser?.getIdToken();

		const res = await fetch(
			`${process.env.NEXT_PUBLIC_API_URL}/agents/title-finder/conversations/${encodeURIComponent(conversationId)}`,
			{
				method: "PUT",
				headers: { Authorization: `Bearer ${token}` },
			},
		);

		if (res.ok) {
			return true;
		}
	} catch (e) {
		console.error("[putFindTitleConversation]: ", e);
	}
}
