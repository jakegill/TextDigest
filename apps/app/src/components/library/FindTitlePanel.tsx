"use client";
import { Menu } from "@base-ui/react/menu";
import {
	ArrowBendRightUpIcon,
	ArrowClockwiseIcon,
	ArrowSquareOutIcon,
	ArrowUpIcon,
	CheckIcon,
	CircleNotchIcon,
	ClockCounterClockwiseIcon,
	MagnifyingGlassIcon,
	PlusIcon,
	SparkleIcon,
	StopIcon,
	XCircleIcon,
	XIcon,
} from "@phosphor-icons/react";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import { TextShimmer } from "@/components/ui/text-shimmer";
import type { UploadedTitle } from "@/components/upload-dropzone";
import type { UseFindTitleReturn } from "@/hooks/useFindTitle";
import type { AgentAction, LibraryItem, SubagentName, TitleCandidate } from "@/services/api/findTitle";
import { ingestFoundTitle } from "@/services/api/ingestFoundTitle";
import { subscribeToTitleProgress, type TitleProgressEvent } from "@/services/api/titleEvents";

const MD_REMARK = [remarkGfm];

function AssistantMarkdown({ text }: { text: string }) {
	return (
		<div className="text-sm typeface-diatype text-neutral-700">
			<ReactMarkdown
				remarkPlugins={MD_REMARK}
				components={{
					h2: ({ children }) => (
						<h2 className="mt-3 mb-1 text-base typeface-diatype font-medium text-neutral-900">{children}</h2>
					),
					h3: ({ children }) => (
						<h3 className="mt-3 mb-1 text-sm typeface-diatype font-medium text-neutral-800">{children}</h3>
					),
					p: ({ children }) => <p className="my-1 text-sm typeface-diatype text-neutral-700">{children}</p>,
					ul: ({ children }) => <ul className="my-1 ml-4 list-disc">{children}</ul>,
					ol: ({ children }) => <ol className="my-1 ml-4 list-decimal">{children}</ol>,
					li: ({ children }) => <li className="my-0.5 text-sm typeface-diatype text-neutral-700">{children}</li>,
					strong: ({ children }) => <span className="font-medium text-neutral-900">{children}</span>,
					a: ({ children, href }) => (
						<a
							href={href}
							target="_blank"
							rel="noopener noreferrer"
							className="text-primary-700 underline hover:text-primary-900"
						>
							{children}
						</a>
					),
				}}
			>
				{text}
			</ReactMarkdown>
		</div>
	);
}

type IngestState = "idle" | "adding" | "added" | "error";

const STARTERS = ["A classic stoicism book", "Recent deep learning textbook", "Project Gutenberg fiction"];

function stripSentinel(text: string): string {
	return text.replace(/<\/?candidates>[\s\S]*?(<\/candidates>|$)/g, "").trim();
}

function formatRelative(iso: string | null): string {
	if (!iso) return "";
	const t = new Date(iso).getTime();
	if (Number.isNaN(t)) return "";
	const diff = Date.now() - t;
	const s = Math.floor(diff / 1000);
	if (s < 60) return "just now";
	const m = Math.floor(s / 60);
	if (m < 60) return `${m}m ago`;
	const h = Math.floor(m / 60);
	if (h < 24) return `${h}h ago`;
	const d = Math.floor(h / 24);
	if (d < 7) return `${d}d ago`;
	return new Date(iso).toLocaleDateString();
}

function statusLabel(active: SubagentName | null): string {
	if (active === "research") return "Researching the topic";
	if (active === "search") return "Searching the web";
	if (active === "verify") return "Browsing sites";
	return "Thinking";
}

function prettyHost(url: string): string {
	try {
		return new URL(url).hostname.replace(/^www\./, "");
	} catch {
		return url;
	}
}

function actionLabel(a: AgentAction): string {
	switch (a.kind) {
		case "browse":
			return `Browsed ${prettyHost(a.url)}`;
		case "browser_search":
			return `Searched "${a.query}"`;
		case "verify":
			return `Verifying ${prettyHost(a.url)}`;
		case "search":
			return `Searching the web for "${a.query}"`;
		case "research":
			return `Researching ${a.topic}`;
	}
}

function AddToLibraryButton({ state, disabled, onClick }: { state: IngestState; disabled?: boolean; onClick: () => void }) {
	const variants: Record<IngestState, { label: string; icon: React.ReactNode; className: string; disabled: boolean }> = {
		idle: {
			label: "Add to library",
			icon: <PlusIcon size={14} />,
			className: "border border-primary-800 bg-primary-600 text-primary-50 hover:bg-primary-700 active:scale-95",
			disabled: false,
		},
		adding: {
			label: "Adding…",
			icon: <CircleNotchIcon size={14} className="animate-spin" />,
			className: "bg-neutral-200 text-neutral-600 cursor-not-allowed",
			disabled: true,
		},
		added: {
			label: "Added",
			icon: <CheckIcon size={14} />,
			className: "bg-accent-teal-100 text-accent-teal-800 cursor-default",
			disabled: true,
		},
		error: {
			label: "Failed — retry",
			icon: <XCircleIcon size={14} />,
			className: "bg-accent-red-100 text-accent-red-800 hover:bg-accent-red-200 active:scale-95",
			disabled: false,
		},
	};
	const v = variants[state];
	return (
		<button
			type="button"
			disabled={v.disabled || disabled}
			onClick={onClick}
			className={`flex items-center gap-1 rounded-md px-2 py-1 text-sm typeface-diatype transition-colors duration-300 ${v.className} ${v.disabled || disabled ? "" : "cursor-pointer"}`}
		>
			{v.icon}
			{v.label}
		</button>
	);
}

function CandidateCard({
	c,
	ingestState,
	onAdd,
}: {
	c: TitleCandidate;
	ingestState: IngestState;
	onAdd: (c: TitleCandidate) => void;
}) {
	const canAdd = Boolean(c.taskId && c.sourceKey);
	return (
		<div className="w-full py-4 flex items-center  flex-col gap-4">
			<div className="flex flex-col gap-4 w-64">
				<div className="relative aspect-3/4 overflow-hidden border border-neutral-200 bg-neutral-100">
					<Image src={c.coverUrl} alt={c.title} fill sizes="288px" className="object-cover" />
				</div>
				<div className="flex flex-col gap-1">
					<p className="text-sm typeface-diatype text-neutral-800 line-clamp-2 capitalize">{c.title}</p>
					<p className="text-xs typeface-diatype text-neutral-500 line-clamp-1 capitalize">{c.author}</p>
				</div>
			</div>
			<div className="flex items-center w-64 gap-4">
				{canAdd && <AddToLibraryButton state={ingestState} onClick={() => onAdd(c)} />}
				<a
					href={c.sourceUrl}
					target="_blank"
					rel="noopener noreferrer"
					className="flex items-center gap-1 rounded-md border border-neutral-200 bg-neutral-100 px-2 py-1 text-sm typeface-diatype text-neutral-700 transition-colors duration-300 hover:bg-neutral-100 hover:text-neutral-900 active:scale-95"
				>
					<ArrowSquareOutIcon size={14} />
					Preview
				</a>
			</div>
		</div>
	);
}

function AssistantTurn({
	content,
	candidates,
	actions,
	ingestStates,
	onAdd,
}: {
	content: string;
	candidates?: TitleCandidate[];
	actions?: AgentAction[];
	ingestStates: Record<string, IngestState>;
	onAdd: (c: TitleCandidate) => void;
}) {
	return (
		<div className="flex flex-col gap-2">
			{actions && actions.length > 0 && (
				<div className="flex flex-col gap-0.5">
					{actions.map((a, i) => (
						<div key={i} className="flex items-center gap-1.5 text-xs typeface-diatype text-neutral-500">
							<SparkleIcon size={12} className="shrink-0" />
							<span className="truncate">{actionLabel(a)}</span>
						</div>
					))}
				</div>
			)}
			{content && <AssistantMarkdown text={content} />}
			{candidates && candidates.length > 0 && (
				<div className="flex flex-col gap-2">
					{candidates.map((c) => (
						<CandidateCard
							key={c.taskId || c.sourceUrl}
							c={c}
							ingestState={(c.taskId && ingestStates[c.taskId]) || "idle"}
							onAdd={onAdd}
						/>
					))}
				</div>
			)}
		</div>
	);
}

export function FindTitlePanel({
	findTitle,
	library,
	onUploaded,
	onProgress,
}: {
	findTitle: UseFindTitleReturn;
	library: LibraryItem[];
	onUploaded?: (title: UploadedTitle) => void;
	onProgress?: (e: TitleProgressEvent) => void;
}) {
	const [message, setMessage] = useState("");
	const [ingestStates, setIngestStates] = useState<Record<string, IngestState>>({});
	const textareaRef = useRef<HTMLTextAreaElement>(null);
	const bodyRef = useRef<HTMLDivElement>(null);
	const panelRef = useRef<HTMLDivElement>(null);

	const handleAdd = async (c: TitleCandidate) => {
		if (!c.taskId || !c.sourceKey) return;
		const tid = c.taskId;
		setIngestStates((s) => ({ ...s, [tid]: "adding" }));
		const res = await ingestFoundTitle({
			taskId: c.taskId,
			sourceKey: c.sourceKey,
			filename: c.filename,
		});
		if (!res?.taskId) {
			setIngestStates((s) => ({ ...s, [tid]: "error" }));
			return;
		}
		setIngestStates((s) => ({ ...s, [tid]: "added" }));

		const ac = new AbortController();
		let cardSurfaced = false;
		subscribeToTitleProgress(
			res.taskId,
			(e) => {
				onProgress?.(e);
				if (!cardSurfaced && e.titleId && e.title && e.author && e.coverUrl) {
					cardSurfaced = true;
					onUploaded?.({
						titleId: e.titleId,
						title: e.title,
						author: e.author,
						coverUrl: e.coverUrl,
						isProcessing: e.stage !== "done" && e.stage !== "failed",
					});
				}
				if (e.stage === "done" || e.stage === "failed") ac.abort();
			},
			ac.signal,
		).catch((err) => {
			if (err?.name !== "AbortError") console.error("[find-title ingest] sse failed", err);
		});
	};

	useEffect(() => {
		if (findTitle.isOpen) textareaRef.current?.focus();
	}, [findTitle.isOpen]);

	useEffect(() => {
		if (!findTitle.isOpen) return;
		let active = false;
		const raf = requestAnimationFrame(() => {
			active = true;
		});
		const onPointerDown = (e: MouseEvent) => {
			if (!active) return;
			const target = e.target as HTMLElement | null;
			if (!target) return;
			if (panelRef.current?.contains(target)) return;
			if (target.closest('[role="menu"],[role="menuitem"],[data-base-ui-popup]')) return;
			findTitle.close();
		};
		document.addEventListener("mousedown", onPointerDown);
		return () => {
			cancelAnimationFrame(raf);
			document.removeEventListener("mousedown", onPointerDown);
		};
	}, [findTitle.isOpen, findTitle.close, findTitle]);

	useEffect(() => {
		const el = bodyRef.current;
		if (el) el.scrollTop = el.scrollHeight;
	}, [findTitle.conversation, findTitle.streamingText, findTitle.streamingCandidates, findTitle.isStreaming]);

	const handleSearch = (q: string) => {
		findTitle.search(q, { library });
		setMessage("");
	};

	const liveNarration = stripSentinel(findTitle.streamingText);

	return (
		<div
			ref={panelRef}
			data-open={findTitle.isOpen}
			className="fixed right-0 top-0 z-60 flex h-svh w-full max-w-full max-h-[100svh] flex-col border-l border-neutral-200 bg-neutral-50 shadow-xl transition-transform translate-x-full data-[open=true]:translate-x-0 lg:w-128"
		>
			<div className="flex h-16 items-center justify-between border-b border-neutral-200 px-4 py-3">
				<div className="flex items-center gap-2">
					<MagnifyingGlassIcon size={16} className="text-neutral-700" />
					<span className="font-medium typeface-diatype text-neutral-900">
						{findTitle.currentTitle || "Find a Title"}
					</span>
				</div>
				<div className="flex items-center gap-1">
					<Menu.Root
						onOpenChange={(open) => {
							if (open) findTitle.refreshHistory();
						}}
					>
						<Menu.Trigger render={<Button variant="ghost" size="icon-sm" aria-label="Past conversations" />}>
							<ClockCounterClockwiseIcon size={16} />
						</Menu.Trigger>
						<Menu.Portal>
							<Menu.Positioner side="bottom" align="end" sideOffset={6} className="z-70">
								<Menu.Popup className="z-70 max-h-80 w-72 overflow-y-auto border border-neutral-200 bg-white py-1 text-sm typeface-diatype text-neutral-700 shadow-md outline-none">
									{findTitle.history.length === 0 ? (
										<div className="px-3 py-2 text-xs text-neutral-500">No past conversations</div>
									) : (
										findTitle.history.map((c) => (
											<Menu.Item
												key={c.conversationId}
												onClick={() => findTitle.loadConversation(c.conversationId)}
												className="flex cursor-pointer flex-col gap-0.5 px-3 py-2 outline-none data-highlighted:bg-neutral-100"
											>
												<span className="truncate text-sm text-neutral-900">
													{c.title || "Untitled"}
												</span>
												<span className="text-xs text-neutral-500">{formatRelative(c.updatedAt)}</span>
											</Menu.Item>
										))
									)}
								</Menu.Popup>
							</Menu.Positioner>
						</Menu.Portal>
					</Menu.Root>
					<Button variant="ghost" size="icon-sm" onClick={findTitle.close} aria-label="Close">
						<XIcon size={16} />
					</Button>
				</div>
			</div>

			<div ref={bodyRef} className="flex flex-1 flex-col gap-4 py-4 overflow-y-auto px-4 ">
				{findTitle.conversation.map((t, i) =>
					t.role === "user" ? (
						<div
							key={i}
							className="self-end max-w-[85%] rounded-md bg-neutral-100 px-3 py-2 text-sm typeface-diatype text-neutral-900 whitespace-pre-wrap"
						>
							{t.content}
						</div>
					) : (
						<AssistantTurn
							key={i}
							content={t.content}
							candidates={t.candidates}
							actions={t.actions}
							ingestStates={ingestStates}
							onAdd={handleAdd}
						/>
					),
				)}

				{findTitle.isStreaming &&
					(liveNarration || findTitle.streamingCandidates.length > 0 || findTitle.actions.length > 0) && (
						<AssistantTurn
							content={liveNarration}
							candidates={findTitle.streamingCandidates}
							actions={findTitle.actions}
							ingestStates={ingestStates}
							onAdd={handleAdd}
						/>
					)}

				{findTitle.isStreaming && findTitle.streamingCandidates.length === 0 && (
					<div className="flex items-center gap-2 text-neutral-700">
						<SparkleIcon size={16} className="shrink-0" />
						<p className="min-w-0 text-sm line-clamp-1 typeface-diatype">
							<TextShimmer>
								{findTitle.actions.length > 0
									? actionLabel(findTitle.actions[findTitle.actions.length - 1])
									: statusLabel(findTitle.activeSubagent)}
							</TextShimmer>
						</p>
					</div>
				)}
			</div>

			<form
				className="relative flex-shrink-0 p-4"
				onSubmit={(e) => {
					e.preventDefault();
					handleSearch(message);
				}}
			>
				<div className="flex min-h-24 w-full flex-col rounded-md border border-neutral-200 bg-neutral-100">
					<textarea
						ref={textareaRef}
						value={message}
						onChange={(e) => setMessage(e.target.value)}
						onKeyDown={(e) => {
							if (e.key === "Enter" && !e.shiftKey) {
								e.preventDefault();
								handleSearch(message);
							}
						}}
						placeholder="Describe a book you're looking for…"
						className="min-h-24 w-full flex-1 resize-none bg-transparent p-2 typeface-diatype text-neutral-900 outline-none placeholder:text-sm placeholder:font-light placeholder:text-neutral-500"
					/>
				</div>

				<div className="absolute right-5 bottom-5 left-5 z-10 flex items-center justify-between gap-2">
					<button
						type="button"
						onClick={findTitle.reset}
						disabled={findTitle.isStreaming}
						className="flex cursor-pointer items-center gap-1 rounded-md border border-neutral-200 bg-neutral-50 px-2 py-1 text-sm typeface-diatype text-neutral-600 transition-colors duration-300 hover:bg-neutral-100 hover:text-neutral-900 active:scale-95 disabled:opacity-50"
					>
						<ArrowClockwiseIcon size={16} />
						Reset
					</button>

					{findTitle.isStreaming ? (
						<button
							type="button"
							onClick={findTitle.stop}
							className="flex cursor-pointer items-center gap-1 rounded-md bg-neutral-200 px-2 py-1 text-sm typeface-diatype text-neutral-800 transition-colors duration-300 hover:bg-neutral-300 active:scale-95"
						>
							<StopIcon size={16} weight="fill" className="text-neutral-600" />
							Stop
						</button>
					) : (
						<button
							type="submit"
							disabled={!message.trim()}
							className="flex cursor-pointer items-center gap-1 rounded-md border border-primary-800 bg-primary-600 px-2 py-1 text-sm typeface-diatype text-primary-50 transition-colors duration-300 hover:bg-primary-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-70"
						>
							<ArrowUpIcon size={16} />
							Search
						</button>
					)}
				</div>
			</form>
		</div>
	);
}
