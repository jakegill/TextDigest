import type { TitleCandidate } from "@/services/api/findTitle";
import { auth } from "@/lib/firebase";

export type FindTitleMessage = {
	role: "user" | "assistant";
	content: string;
	ts?: string;
	candidates?: TitleCandidate[];
};

export type FindTitleConversationDoc = {
	conversationId: string;
	title: string;
	messages: FindTitleMessage[];
	createdAt: string | null;
	updatedAt: string | null;
};

export async function getFindTitleConversation(conversationId: string) {
	try {
		await auth.authStateReady();
		const token = await auth.currentUser?.getIdToken();

		const res = await fetch(
			`${process.env.NEXT_PUBLIC_API_URL}/agents/title-finder/conversations/${encodeURIComponent(conversationId)}`,
			{ headers: { Authorization: `Bearer ${token}` } },
		);

		if (res.ok) {
			const data = (await res.json()) as FindTitleConversationDoc;
			return data;
		}
	} catch (e) {
		console.error("[getFindTitleConversation]: ", e);
	}
}
