"use client";
import { useCallback, useRef, useState } from "react";

import {
	findTitle,
	type FindTurn,
	type LibraryItem,
	type SubagentName,
	type TitleCandidate,
} from "@/services/api/findTitle";
import { getFindTitleConversation } from "@/services/api/getFindTitleConversation";
import {
	getFindTitleConversations,
	type FindTitleConversationSummary,
} from "@/services/api/getFindTitleConversations";
import { postFindTitleConversation } from "@/services/api/postFindTitleConversation";
import { putFindTitleConversation } from "@/services/api/putFindTitleConversation";

export type FindTitleContext = { library: LibraryItem[] };

export type FindTitleTurn = {
	role: "user" | "assistant";
	content: string;
	candidates?: TitleCandidate[];
};

function stripSentinel(text: string): string {
	return text.replace(/<\/?candidates>[\s\S]*?(<\/candidates>|$)/g, "").trim();
}

export function useFindTitle() {
	const [isOpen, setIsOpen] = useState(false);
	const [conversationId, setConversationId] = useState(() => crypto.randomUUID());
	const [conversation, setConversation] = useState<FindTitleTurn[]>([]);
	const [streamingText, setStreamingText] = useState("");
	const [streamingCandidates, setStreamingCandidates] = useState<TitleCandidate[]>([]);
	const [isStreaming, setIsStreaming] = useState(false);
	const [activeSubagent, setActiveSubagent] = useState<SubagentName | null>(null);
	const [currentTitle, setCurrentTitle] = useState("");
	const [history, setHistory] = useState<FindTitleConversationSummary[]>([]);
	const abortRef = useRef<AbortController | null>(null);
	const initializedIdsRef = useRef<Set<string>>(new Set());

	const open = useCallback(() => {
		setIsOpen(true);
	}, []);

	const stop = useCallback(() => {
		abortRef.current?.abort();
		abortRef.current = null;
		setIsStreaming(false);
		setActiveSubagent(null);
	}, []);

	const close = useCallback(() => {
		setIsOpen(false);
		abortRef.current?.abort();
		abortRef.current = null;
		setIsStreaming(false);
		setActiveSubagent(null);
	}, []);

	const reset = useCallback(() => {
		abortRef.current?.abort();
		abortRef.current = null;
		setIsStreaming(false);
		setActiveSubagent(null);
		setStreamingText("");
		setStreamingCandidates([]);
		setConversation([]);
		setCurrentTitle("");
		setConversationId(crypto.randomUUID());
	}, []);

	const refreshHistory = useCallback(async () => {
		const list = await getFindTitleConversations();
		if (list) setHistory(list);
	}, []);

	const loadConversation = useCallback(async (id: string) => {
		abortRef.current?.abort();
		abortRef.current = null;
		const doc = await getFindTitleConversation(id);
		if (!doc) return;
		setIsStreaming(false);
		setActiveSubagent(null);
		setStreamingText("");
		setStreamingCandidates([]);
		setConversation(
			doc.messages.map((m) => ({
				role: m.role,
				content: m.content,
				candidates: m.candidates,
			})),
		);
		setConversationId(doc.conversationId);
		setCurrentTitle(doc.title);
		initializedIdsRef.current.add(doc.conversationId);
	}, []);

	const search = useCallback(
		async (q: string, ctx: FindTitleContext) => {
			const trimmed = q.trim();
			if (!trimmed || isStreaming) return;

			const historyAtSend: FindTurn[] = conversation.map((t) => ({
				role: t.role,
				content: t.content,
			}));
			setConversation((c) => [...c, { role: "user", content: trimmed }]);
			setStreamingText("");
			setStreamingCandidates([]);
			setActiveSubagent(null);
			setIsStreaming(true);

			if (!initializedIdsRef.current.has(conversationId)) {
				initializedIdsRef.current.add(conversationId);
				postFindTitleConversation(conversationId, { firstMessage: trimmed }).then((r) => {
					if (r?.title) setCurrentTitle(r.title);
				});
			}

			const ac = new AbortController();
			abortRef.current = ac;

			let textAcc = "";
			let candAcc: TitleCandidate[] = [];
			try {
				await findTitle(
					conversationId,
					trimmed,
					ctx.library,
					historyAtSend,
					(e) => {
						if (e.event === "thinking") {
							textAcc += e.body;
							setStreamingText(textAcc);
						} else if (e.event === "research_chunk") {
							textAcc += e.body;
							setStreamingText(textAcc);
						} else if (e.event === "subagent_call") {
							setActiveSubagent(e.body.agent);
						} else if (e.event === "candidates") {
							candAcc = e.body;
							setStreamingCandidates(candAcc);
							setActiveSubagent(null);
						} else if (e.event === "done") {
							setConversation((c) => [
								...c,
								{
									role: "assistant",
									content: stripSentinel(textAcc),
									candidates: candAcc,
								},
							]);
							setStreamingText("");
							setStreamingCandidates([]);
							setActiveSubagent(null);
							setIsStreaming(false);
							putFindTitleConversation(conversationId);
						} else if (e.event === "error") {
							console.error("[useFindTitle] stream error event", e.body);
							setActiveSubagent(null);
							setIsStreaming(false);
						}
					},
					ac.signal,
				);
			} catch (e) {
				if (!ac.signal.aborted) console.error("[useFindTitle] search failed", e);
				setIsStreaming(false);
				setActiveSubagent(null);
			}
		},
		[conversation, conversationId, isStreaming],
	);

	return {
		isOpen,
		conversationId,
		conversation,
		streamingText,
		streamingCandidates,
		isStreaming,
		activeSubagent,
		currentTitle,
		history,
		open,
		close,
		stop,
		reset,
		search,
		refreshHistory,
		loadConversation,
	};
}

export type UseFindTitleReturn = ReturnType<typeof useFindTitle>;
