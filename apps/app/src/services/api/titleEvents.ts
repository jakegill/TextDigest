import { fetchEventSource } from "@microsoft/fetch-event-source";

import { auth } from "@/lib/firebase";

export type TitleProgressStage =
	| "queued"
	| "cover"
	| "metadata"
	| "parsing"
	| "vectorizing"
	| "toc"
	| "writing"
	| "done"
	| "failed";

export type TitleProgressEvent = {
	stage: TitleProgressStage;
	titleId: string | null;
	title: string | null;
	author: string | null;
	coverUrl: string | null;
	error: string | null;
	updatedAt: string | null;
};

export async function subscribeToTitleProgress(
	taskId: string,
	onEvent: (e: TitleProgressEvent) => void,
	signal: AbortSignal,
): Promise<void> {
	const url = `${process.env.NEXT_PUBLIC_API_URL}/titles/processing/${encodeURIComponent(taskId)}/events`;
	console.log("[titleEvents] subscribe", { taskId, url });

	await auth.authStateReady();
	const token = await auth.currentUser?.getIdToken();
	if (!token) {
		console.error("[titleEvents] no firebase token; not subscribing");
		return;
	}

	console.log("[titleEvents] opening stream");
	await fetchEventSource(url, {
		headers: { Authorization: `Bearer ${token}` },
		signal,
		openWhenHidden: true,
		async onopen(res) {
			const ct = res.headers.get("content-type");
			console.log("[titleEvents] onopen", res.status, ct);
			if (!res.ok || !ct?.includes("text/event-stream")) {
				throw new Error(`bad sse response: ${res.status} ${ct}`);
			}
		},
		onmessage(msg) {
			if (!msg.data) return;
			try {
				onEvent(JSON.parse(msg.data) as TitleProgressEvent);
			} catch (e) {
				console.error("[titleEvents] malformed event", msg.data, e);
			}
		},
		onerror(err) {
			console.error("[titleEvents] stream error", err);
			// Re-throw so fetchEventSource doesn't auto-retry and the caller's
			// .catch() can see + stop.
			throw err;
		},
		onclose() {
			console.log("[titleEvents] stream closed");
		},
	});
}
