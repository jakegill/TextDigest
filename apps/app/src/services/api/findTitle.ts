import { fetchEventSource } from "@microsoft/fetch-event-source";

import { auth } from "@/lib/firebase";

export type TitleCandidate = {
	title: string;
	author: string;
	sourceUrl: string;
	snippet: string;
	coverUrl: string;
	taskId?: string;
	sourceKey?: string;
	filename?: string;
};

export type LibraryItem = { title: string; author: string };

export type FindTurn = { role: "user" | "assistant"; content: string };

export type SubagentName = "research" | "search" | "verify";

export type AgentAction =
	| { kind: "research"; topic: string }
	| { kind: "search"; query: string }
	| { kind: "verify"; url: string }
	| { kind: "browse"; url: string }
	| { kind: "browser_search"; query: string };

export type FindTitleEvent =
	| { event: "start" }
	| { event: "thinking"; body: string }
	| { event: "subagent_call"; body: { agent: SubagentName; input: Record<string, unknown> } }
	| { event: "browser_action"; body: { action: string; args: Record<string, unknown> } }
	| { event: "search_result"; body: { query: string; count: number; urls: { title: string; url: string }[] } }
	| { event: "research_chunk"; body: string }
	| { event: "candidates"; body: TitleCandidate[] }
	| { event: "done" }
	| { event: "error"; body: string };

export async function findTitle(
	conversationId: string,
	query: string,
	existingTitles: LibraryItem[],
	history: FindTurn[],
	onEvent: (e: FindTitleEvent) => void,
	signal: AbortSignal,
): Promise<void> {
	const url = `${process.env.NEXT_PUBLIC_API_URL}/agents/title-finder`;

	await auth.authStateReady();
	const token = await auth.currentUser?.getIdToken();
	if (!token) {
		console.error("[findTitle] no firebase token; not sending");
		return;
	}

	await fetchEventSource(url, {
		method: "POST",
		headers: {
			Authorization: `Bearer ${token}`,
			"Content-Type": "application/json",
			Accept: "text/event-stream",
		},
		body: JSON.stringify({ conversationId, query, existingTitles, history }),
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
				onEvent(JSON.parse(msg.data) as FindTitleEvent);
			} catch (e) {
				console.error("[findTitle] malformed event", msg.data, e);
			}
		},
		onerror(err) {
			console.error("[findTitle] stream error", err);
			throw err;
		},
	});
}
