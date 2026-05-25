import { fetchEventSource } from "@microsoft/fetch-event-source";

import { auth } from "@/lib/firebase";

export type QuestionTurn = { role: "user" | "assistant"; content: string };

export type QuestionEvent =
	| { event: "turn-start" }
	| { event: "chunk"; body: string }
	| { event: "turn-over" }
	| { event: "error"; body: string };

export async function postQuestion(
	body: {
		conversationId: string;
		titleId: string;
		title: string;
		author: string;
		query: string;
		highlightedText: string;
		pageContent: string;
		history: QuestionTurn[];
	},
	onEvent: (e: QuestionEvent) => void,
	signal: AbortSignal,
): Promise<void> {
	const url = `${process.env.NEXT_PUBLIC_API_URL}/agents/questions`;

	await auth.authStateReady();
	const token = await auth.currentUser?.getIdToken();
	if (!token) {
		console.error("[postQuestion] no firebase token; not sending");
		return;
	}

	await fetchEventSource(url, {
		method: "POST",
		headers: {
			Authorization: `Bearer ${token}`,
			"Content-Type": "application/json",
			Accept: "text/event-stream",
		},
		body: JSON.stringify(body),
		signal,
		openWhenHidden: true,
		async onopen(res) {
			const ct = res.headers.get("content-type");
			if (!res.ok || !ct?.includes("text/event-stream")) {
				throw new Error(`bad sse response: ${res.status} ${ct}`);
			}
		},
		onmessage(msg) {
			if (!msg.data) return;
			try {
				onEvent(JSON.parse(msg.data) as QuestionEvent);
			} catch (e) {
				console.error("[postQuestion] malformed event", msg.data, e);
			}
		},
		onerror(err) {
			console.error("[postQuestion] stream error", err);
			throw err;
		},
	});
}
