import { auth } from "@/lib/firebase";

export type ConversationDoc = {
	conversationId: string;
	title: string;
	titleId: string;
	titleName: string;
	author: string;
	messages: { role: "user" | "assistant"; content: string; ts?: string }[];
	createdAt: string | null;
	updatedAt: string | null;
};

export async function getConversation(conversationId: string) {
	try {
		await auth.authStateReady();
		const token = await auth.currentUser?.getIdToken();

		const res = await fetch(
			`${process.env.NEXT_PUBLIC_API_URL}/agents/questions/conversations/${encodeURIComponent(conversationId)}`,
			{ headers: { Authorization: `Bearer ${token}` } },
		);

		if (res.ok) {
			const data = (await res.json()) as ConversationDoc;
			return data;
		}
	} catch (e) {
		console.error("[getConversation]: ", e);
	}
}
