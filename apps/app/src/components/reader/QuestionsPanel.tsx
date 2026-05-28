"use client";
import { Menu } from "@base-ui/react/menu";
import {
	ArrowBendRightUpIcon,
	ArrowClockwiseIcon,
	ArrowUpIcon,
	ClockCounterClockwiseIcon,
	SparkleIcon,
	StopIcon,
	XIcon,
} from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import { Button } from "@/components/ui/button";
import { SideDrawer } from "@/components/ui/side-drawer";
import { TextShimmer } from "@/components/ui/text-shimmer";
import type { UseQuestionsReturn } from "@/hooks/useQuestions";

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

function formatElapsed(ms: number): string {
	const s = Math.round(ms / 1000);
	if (s < 1) return "<1s";
	if (s < 60) return `${s}s`;
	const m = Math.floor(s / 60);
	const rem = s % 60;
	return rem ? `${m}m ${rem}s` : `${m}m`;
}

function ThoughtSignature({ thinkMs }: { thinkMs: number }) {
	return (
		<div className="mb-1 flex items-center gap-1.5 text-xs typeface-diatype text-neutral-500">
			<SparkleIcon size={12} className="shrink-0" />
			<span>Thought for {formatElapsed(thinkMs)}</span>
		</div>
	);
}

const STARTERS = ["Examples of this", "Explain the highlighted text", "How does this work"];

const MD_REMARK = [remarkGfm, remarkMath];
const MD_REHYPE = [rehypeKatex, rehypeRaw, [rehypeHighlight, { ignoreMissing: true }] as const];

function AssistantMarkdown({ text }: { text: string }) {
	return (
		<ReactMarkdown
			remarkPlugins={MD_REMARK}
			rehypePlugins={MD_REHYPE as any}
			components={{
				p: ({ children }) => <p className="my-2 text-sm typeface-arizona text-neutral-800">{children}</p>,
				li: ({ children }) => <li className="my-1 text-sm typeface-arizona text-neutral-800">{children}</li>,
				code: (props: { inline?: boolean; className?: string; children?: React.ReactNode }) => {
					const { inline, className, children } = props;
					if (inline) {
						return <code className="rounded bg-neutral-100 px-1 py-0.5 text-xs">{children}</code>;
					}
					return (
						<pre className="my-2 overflow-x-auto rounded-md bg-neutral-100 p-2 text-xs">
							<code className={className}>{children}</code>
						</pre>
					);
				},
			}}
		>
			{text}
		</ReactMarkdown>
	);
}

export function QuestionsPanel({
	questions,
	titleId,
	title,
	author,
	pageContent,
}: {
	questions: UseQuestionsReturn;
	titleId: string;
	title: string;
	author: string;
	pageContent: string;
}) {
	const [message, setMessage] = useState("");
	const textareaRef = useRef<HTMLTextAreaElement>(null);
	const conversationRef = useRef<HTMLDivElement>(null);

	useEffect(() => {
		const el = conversationRef.current;
		if (el) el.scrollTop = el.scrollHeight;
	}, [questions.conversation, questions.streamingText, questions.isStreaming]);

	const ctx = { titleId, title, author, pageContent };

	const handleSend = (q: string) => {
		questions.send(q, ctx);
		setMessage("");
	};

	const showStarters = questions.conversation.length === 0 && !questions.isStreaming && !questions.streamingText;

	return (
		<div className="flex h-full w-full flex-col">
			<header className="flex flex-shrink-0 h-16 items-center justify-between border-b border-neutral-200 px-4 py-3">
				<div className="flex items-center gap-2">
					<span className=" font-medium typeface-diatype text-neutral-900">Understand</span>
				</div>
				<div className="flex items-center gap-1">
					<Menu.Root
						onOpenChange={(open) => {
							if (open) questions.refreshHistory();
						}}
					>
						<Menu.Trigger render={<Button variant="ghost" aria-label="Past conversations" />}>
							<ClockCounterClockwiseIcon className="size-6" />
						</Menu.Trigger>
						<Menu.Portal>
							<Menu.Positioner side="bottom" align="end" sideOffset={6} className="z-70">
								<Menu.Popup className="z-70 max-h-80 w-72 overflow-y-auto border border-neutral-200 bg-white py-1 text-sm typeface-diatype text-neutral-700 shadow-md outline-none">
									{questions.history.length === 0 ? (
										<div className="px-3 py-2 text-xs text-neutral-500">No past conversations</div>
									) : (
										questions.history.map((c) => (
											<Menu.Item
												key={c.conversationId}
												onClick={() => questions.loadConversation(c.conversationId)}
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
					<Button variant="ghost" onClick={questions.close} aria-label="Close">
						<XIcon className="size-6" />
					</Button>
				</div>
			</header>

			<main ref={conversationRef} className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 pt-4 pb-3">
				{questions.conversation.map((m, i) =>
					m.role === "user" ? (
						<div
							key={i}
							className="self-end max-w-[85%] rounded-md bg-neutral-100 px-3 py-2 text-sm typeface-diatype text-neutral-900 whitespace-pre-wrap"
						>
							{m.content}
						</div>
					) : (
						<div key={i} className="text-neutral-800">
							{m.thinkMs !== undefined && <ThoughtSignature thinkMs={m.thinkMs} />}
							<AssistantMarkdown text={m.content} />
						</div>
					),
				)}

				{questions.isStreaming && questions.streamingText && (
					<div className="text-neutral-800 text-lg">
						{questions.thinkMs !== undefined && <ThoughtSignature thinkMs={questions.thinkMs} />}
						<AssistantMarkdown text={questions.streamingText} />
					</div>
				)}

				{questions.isStreaming && !questions.streamingText && (
					<div className="flex items-center gap-2 text-neutral-700">
						<SparkleIcon size={16} className="flex-shrink-0" />
						<p className="min-w-0 text-sm typeface-diatype">
							<TextShimmer>Thinking</TextShimmer>
						</p>
					</div>
				)}

				{showStarters && (
					<div className="mt-auto flex w-full flex-col gap-2">
						{STARTERS.map((m) => (
							<button
								key={m}
								onClick={() => handleSend(m)}
								className="flex items-center justify-between gap-1 rounded-md bg-neutral-100 px-4 py-2 transition-colors hover:bg-neutral-200"
							>
								<p className="truncate text-sm typeface-diatype text-neutral-700">{m}</p>
								<ArrowBendRightUpIcon size={20} className="text-neutral-500" />
							</button>
						))}
					</div>
				)}
			</main>

			<footer className="flex flex-col">
				<form
					className="relative flex-shrink-0 p-3"
					onSubmit={(e) => {
						e.preventDefault();
						handleSend(message);
					}}
				>
					<div className="flex min-h-24 w-full flex-col rounded-md border border-neutral-200 bg-neutral-100">
						{questions.highlightedText && (
							<div className="max-h-12 overflow-hidden border-b border-neutral-200 p-2 text-xs typeface-diatype text-neutral-600">
								<span className="line-clamp-2">
									“
									{questions.highlightedText.length > 140
										? questions.highlightedText.slice(0, 140).trimEnd() + "…"
										: questions.highlightedText}
									”
								</span>
							</div>
						)}
						<textarea
							ref={textareaRef}
							value={message}
							onChange={(e) => setMessage(e.target.value)}
							onKeyDown={(e) => {
								if (e.key === "Enter" && !e.shiftKey) {
									e.preventDefault();
									handleSend(message);
								}
							}}
							placeholder="Ask anything about this book…"
							className="min-h-24 w-full flex-1 resize-none bg-transparent p-2 text-base typeface-diatype text-neutral-900 outline-none placeholder:text-sm placeholder:font-light placeholder:text-neutral-500"
						/>
					</div>

					<div className="absolute right-5 bottom-5 left-5 z-10 flex items-center justify-between gap-2">
						<button
							type="button"
							onClick={questions.reset}
							disabled={questions.isStreaming}
							className="flex cursor-pointer items-center gap-1 rounded-md border border-neutral-200 bg-neutral-50 px-2 py-1 text-sm typeface-diatype text-neutral-600 transition-colors duration-300 hover:bg-neutral-100 hover:text-neutral-900 active:scale-95 disabled:opacity-50"
						>
							<ArrowClockwiseIcon size={16} />
							Reset
						</button>

						{questions.isStreaming ? (
							<button
								type="button"
								onClick={questions.stop}
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
								Send
							</button>
						)}
					</div>
				</form>
			</footer>
		</div>
	);
}
