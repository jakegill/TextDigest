import { auth } from "@/lib/firebase";

export type FindTitleConversationSummary = {
	conversationId: string;
	title: string;
	updatedAt: string | null;
};

export async function getFindTitleConversations() {
	try {
		await auth.authStateReady();
		const token = await auth.currentUser?.getIdToken();

		const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/agents/title-finder/conversations`, {
			headers: { Authorization: `Bearer ${token}` },
		});

		if (res.ok) {
			const data = (await res.json()) as FindTitleConversationSummary[];
			return data;
		}
	} catch (e) {
		console.error("[getFindTitleConversations]: ", e);
	}
}
