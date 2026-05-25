"use client";
import { useCallback, useRef, useState } from "react";

import { getConversation } from "@/services/api/getConversation";
import { getConversations, type ConversationSummary } from "@/services/api/getConversations";
import { postConversation } from "@/services/api/postConversation";
import { postQuestion, type QuestionTurn } from "@/services/api/postQuestion";
import { putConversation } from "@/services/api/putConversation";

export type QuestionsContext = {
	titleId: string;
	title: string;
	author: string;
	pageContent: string;
};

export function useQuestions() {
	const [isOpen, setIsOpen] = useState(false);
	const [conversationId, setConversationId] = useState(() => crypto.randomUUID());
	const [conversation, setConversation] = useState<QuestionTurn[]>([]);
	const [highlightedText, setHighlightedText] = useState("");
	const [streamingText, setStreamingText] = useState("");
	const [isStreaming, setIsStreaming] = useState(false);
	const [currentTitle, setCurrentTitle] = useState("");
	const [history, setHistory] = useState<ConversationSummary[]>([]);
	const abortRef = useRef<AbortController | null>(null);
	const initializedIdsRef = useRef<Set<string>>(new Set());

	const open = useCallback((highlighted?: string) => {
		setIsOpen(true);
		if (highlighted !== undefined) setHighlightedText(highlighted);
	}, []);

	const stop = useCallback(() => {
		abortRef.current?.abort();
		abortRef.current = null;
		setIsStreaming(false);
	}, []);

	const close = useCallback(() => {
		setIsOpen(false);
		abortRef.current?.abort();
		abortRef.current = null;
		setIsStreaming(false);
	}, []);

	const reset = useCallback(() => {
		abortRef.current?.abort();
		abortRef.current = null;
		setIsStreaming(false);
		setStreamingText("");
		setConversation([]);
		setCurrentTitle("");
		setConversationId(crypto.randomUUID());
	}, []);

	const refreshHistory = useCallback(async () => {
		const list = await getConversations();
		if (list) setHistory(list);
	}, []);

	const loadConversation = useCallback(async (id: string) => {
		abortRef.current?.abort();
		abortRef.current = null;
		const doc = await getConversation(id);
		if (!doc) return;
		setIsStreaming(false);
		setStreamingText("");
		setConversation(
			doc.messages.map((m) => ({ role: m.role, content: m.content })),
		);
		setConversationId(doc.conversationId);
		setCurrentTitle(doc.title);
		initializedIdsRef.current.add(doc.conversationId);
	}, []);

	const send = useCallback(
		async (query: string, ctx: QuestionsContext) => {
			const trimmed = query.trim();
			if (!trimmed || isStreaming) return;

			const historyAtSend = conversation;
			setConversation((c) => [...c, { role: "user", content: trimmed }]);
			setStreamingText("");
			setIsStreaming(true);

			if (!initializedIdsRef.current.has(conversationId)) {
				initializedIdsRef.current.add(conversationId);
				postConversation(conversationId, {
					firstMessage: trimmed,
					titleId: ctx.titleId,
					titleName: ctx.title,
					author: ctx.author,
				}).then((r) => {
					if (r?.title) setCurrentTitle(r.title);
				});
			}

			const ac = new AbortController();
			abortRef.current = ac;

			let acc = "";
			try {
				await postQuestion(
					{
						conversationId,
						titleId: ctx.titleId,
						title: ctx.title,
						author: ctx.author,
						query: trimmed,
						highlightedText,
						pageContent: ctx.pageContent,
						history: historyAtSend,
					},
					(e) => {
						if (e.event === "chunk") {
							acc += e.body;
							setStreamingText(acc);
						} else if (e.event === "turn-over") {
							setConversation((c) => [...c, { role: "assistant", content: acc }]);
							setStreamingText("");
							setIsStreaming(false);
							putConversation(conversationId);
						} else if (e.event === "error") {
							console.error("[useQuestions] stream error event", e.body);
							setIsStreaming(false);
						}
					},
					ac.signal,
				);
			} catch (e) {
				if (!ac.signal.aborted) console.error("[useQuestions] send failed", e);
				setIsStreaming(false);
			}
		},
		[conversation, conversationId, highlightedText, isStreaming],
	);

	return {
		isOpen,
		conversationId,
		conversation,
		highlightedText,
		streamingText,
		isStreaming,
		currentTitle,
		history,
		open,
		close,
		stop,
		reset,
		send,
		refreshHistory,
		loadConversation,
	};
}

export type UseQuestionsReturn = ReturnType<typeof useQuestions>;
