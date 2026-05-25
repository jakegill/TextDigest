import { auth } from "@/lib/firebase";

export type ConversationSummary = {
	conversationId: string;
	title: string;
	titleId: string;
	titleName: string;
	updatedAt: string | null;
};

export async function getConversations() {
	try {
		await auth.authStateReady();
		const token = await auth.currentUser?.getIdToken();

		const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/agents/questions/conversations`, {
			headers: { Authorization: `Bearer ${token}` },
		});

		if (res.ok) {
			const data = (await res.json()) as ConversationSummary[];
			return data;
		}
	} catch (e) {
		console.error("[getConversations]: ", e);
	}
}
