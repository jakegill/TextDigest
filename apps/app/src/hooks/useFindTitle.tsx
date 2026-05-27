"use client";
import { useCallback, useRef, useState } from "react";

import {
	findTitle,
	type AgentAction,
	type FindTurn,
	type LibraryItem,
	type SubagentName,
	type TitleCandidate,
} from "@/services/api/findTitle";
import { getFindTitleConversation } from "@/services/api/getFindTitleConversation";
import { getFindTitleConversations, type FindTitleConversationSummary } from "@/services/api/getFindTitleConversations";
import { postFindTitleConversation } from "@/services/api/postFindTitleConversation";
import { putFindTitleConversation } from "@/services/api/putFindTitleConversation";
import { v4 as uuid } from "uuid";

export type FindTitleContext = { library: LibraryItem[] };

export type FindTitleTurn = {
	role: "user" | "assistant";
	content: string;
	candidates?: TitleCandidate[];
	actions?: AgentAction[];
};

function stripSentinel(text: string): string {
	return text.replace(/<\/?candidates>[\s\S]*?(<\/candidates>|$)/g, "").trim();
}

export function useFindTitle() {
	const [isOpen, setIsOpen] = useState(false);
	const [conversationId, setConversationId] = useState(() => uuid());
	const [conversation, setConversation] = useState<FindTitleTurn[]>([]);
	const [streamingText, setStreamingText] = useState("");
	const [streamingCandidates, setStreamingCandidates] = useState<TitleCandidate[]>([]);
	const [actions, setActions] = useState<AgentAction[]>([]);
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
	}, []);

	const reset = useCallback(() => {
		abortRef.current?.abort();
		abortRef.current = null;
		setIsStreaming(false);
		setActiveSubagent(null);
		setStreamingText("");
		setStreamingCandidates([]);
		setActions([]);
		setConversation([]);
		setCurrentTitle("");
		setConversationId(uuid());
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
		setActions([]);
		setConversation(
			doc.messages.map((m) => ({
				role: m.role,
				content: m.content,
				candidates: m.candidates,
				actions: m.actions,
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
			setActions([]);
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
			const actionsAcc: AgentAction[] = [];
			const pushAction = (a: AgentAction) => {
				actionsAcc.push(a);
				setActions([...actionsAcc]);
			};
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
							const inp = e.body.input;
							if (e.body.agent === "research" && typeof inp.topic === "string") {
								pushAction({ kind: "research", topic: inp.topic });
							} else if (e.body.agent === "search" && typeof inp.query === "string") {
								pushAction({ kind: "search", query: inp.query });
							} else if (e.body.agent === "verify" && typeof inp.url === "string") {
								pushAction({ kind: "verify", url: inp.url });
							}
						} else if (e.event === "browser_action") {
							const args = e.body.args;
							if (e.body.action === "navigate" && typeof args.url === "string") {
								pushAction({ kind: "browse", url: args.url });
							} else if (e.body.action === "search" && typeof args.query === "string") {
								pushAction({ kind: "browser_search", query: args.query });
							}
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
									actions: actionsAcc.length ? [...actionsAcc] : undefined,
								},
							]);
							setStreamingText("");
							setStreamingCandidates([]);
							setActions([]);
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
		actions,
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
