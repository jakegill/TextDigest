"use client";
import {
	ArrowBendRightUpIcon,
	ArrowClockwiseIcon,
	ArrowSquareOutIcon,
	ArrowUpIcon,
	CheckIcon,
	CircleNotchIcon,
	MagnifyingGlassIcon,
	PlusIcon,
	SparkleIcon,
	StopIcon,
	XCircleIcon,
	XIcon,
} from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import { TextShimmer } from "@/components/ui/text-shimmer";
import type { UploadedTitle } from "@/components/upload-dropzone";
import type { UseFindTitleReturn } from "@/hooks/useFindTitle";
import type { LibraryItem, SubagentName, TitleCandidate } from "@/services/api/findTitle";
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

function statusLabel(active: SubagentName | null): string {
	if (active === "research") return "Researching the topic";
	if (active === "search") return "Searching the web";
	if (active === "verify") return "Browsing sites";
	return "Thinking";
}

function hostname(url: string): string {
	try {
		return new URL(url).hostname.replace(/^www\./, "");
	} catch {
		return url;
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
			className={`flex items-center gap-1 rounded-md px-2 py-1 text-xs typeface-diatype transition-colors duration-300 ${v.className} ${v.disabled || disabled ? "" : "cursor-pointer"}`}
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
		<div className="flex flex-col gap-1 rounded-md border border-neutral-200 bg-white px-3 py-2">
			<span className="truncate text-sm typeface-diatype text-neutral-900">{c.title}</span>
			{c.author && <span className="truncate text-xs typeface-diatype text-neutral-500">{c.author}</span>}
			{c.snippet && <span className="line-clamp-2 text-xs typeface-diatype text-neutral-600">{c.snippet}</span>}
			<div className="mt-1 flex items-center justify-between gap-2">
				<a
					href={c.sourceUrl}
					target="_blank"
					rel="noopener noreferrer"
					className="flex items-center gap-1 text-xs typeface-diatype text-primary-700 transition-colors duration-300 hover:text-primary-900"
				>
					<ArrowSquareOutIcon size={12} />
					{hostname(c.sourceUrl)}
				</a>
				{canAdd && <AddToLibraryButton state={ingestState} onClick={() => onAdd(c)} />}
			</div>
		</div>
	);
}

function AssistantTurn({
	content,
	candidates,
	ingestStates,
	onAdd,
}: {
	content: string;
	candidates?: TitleCandidate[];
	ingestStates: Record<string, IngestState>;
	onAdd: (c: TitleCandidate) => void;
}) {
	return (
		<div className="flex flex-col gap-2">
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
	const showStarters = findTitle.conversation.length === 0 && !findTitle.isStreaming;

	return (
		<div
			ref={panelRef}
			data-open={findTitle.isOpen}
			className="fixed right-0 top-0 z-60 flex h-svh w-full flex-col border-l border-neutral-200 bg-neutral-50 shadow-xl transition-transform translate-x-full data-[open=true]:translate-x-0 md:w-128"
		>
			<div className="flex h-16 items-center justify-between border-b border-neutral-200 px-4 py-3">
				<div className="flex items-center gap-2">
					<MagnifyingGlassIcon size={16} className="text-neutral-700" />
					<span className="font-medium typeface-diatype text-neutral-900">Find a Title</span>
				</div>
				<Button variant="ghost" size="icon-sm" onClick={findTitle.close} aria-label="Close">
					<XIcon size={16} />
				</Button>
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
							ingestStates={ingestStates}
							onAdd={handleAdd}
						/>
					),
				)}

				{findTitle.isStreaming && (liveNarration || findTitle.streamingCandidates.length > 0) && (
					<AssistantTurn
						content={liveNarration}
						candidates={findTitle.streamingCandidates}
						ingestStates={ingestStates}
						onAdd={handleAdd}
					/>
				)}

				{findTitle.isStreaming && findTitle.streamingCandidates.length === 0 && (
					<div className="flex items-center gap-2 text-neutral-700">
						<SparkleIcon size={16} className="shrink-0" />
						<p className="min-w-0 text-sm typeface-diatype">
							<TextShimmer>{statusLabel(findTitle.activeSubagent)}</TextShimmer>
						</p>
					</div>
				)}

				{showStarters && (
					<div className="mt-auto flex w-full flex-col gap-2">
						{STARTERS.map((m) => (
							<button
								key={m}
								onClick={() => handleSearch(m)}
								className="flex cursor-pointer items-center justify-between gap-1 rounded-md bg-neutral-100 px-4 py-2 transition-colors duration-300 hover:bg-neutral-200"
							>
								<p className="truncate text-sm typeface-diatype text-neutral-700">{m}</p>
								<ArrowBendRightUpIcon size={20} className="text-neutral-500" />
							</button>
						))}
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
						className="min-h-24 w-full flex-1 resize-none bg-transparent p-2 text-sm typeface-diatype text-neutral-900 outline-none placeholder:text-sm placeholder:font-light placeholder:text-neutral-500"
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
