"use client";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowLeftIcon, CircleNotchIcon, ListBulletsIcon } from "@phosphor-icons/react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeAutolinkHeadings from "rehype-autolink-headings";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import rehypeSlug from "rehype-slug";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import { QuestionsPanel } from "@/components/reader/QuestionsPanel";
import { SelectionBubble } from "@/components/reader/SelectionBubble";
import { TocPanel, type TocEntry } from "@/components/reader/TocPanel";
import { Button } from "@/components/ui/button";
import { SideDrawer } from "@/components/ui/side-drawer";
import { type Bbox, DEFAULT_BBOX, isCentered, unionBbox } from "@/hooks/useBbox";
import { useQuestions } from "@/hooks/useQuestions";
import { getContentList } from "@/services/api/getContentList";
import { getTitleById } from "@/services/api/getTitleById";
import { putTitle } from "@/services/api/putTitle";

export const dynamic = "force-dynamic";

type ContentBlock = {
	type: "text" | "image" | "list" | string;
	text?: string;
	text_level?: number;
	img_path?: string;
	image_caption?: string[];
	list_items?: string[];
	sub_type?: string;
	bbox?: Bbox;
	page_idx: number;
};

type Item = { md: string; centered: boolean };
type Page = Item[];

const KEEP_TYPES = new Set(["text", "image", "list"]);

function blockToMd(b: ContentBlock): string {
	if (b.type === "text") {
		if (b.text_level && b.text_level > 0) {
			const level = Math.min(6, b.text_level);
			return `${"#".repeat(level)} ${b.text ?? ""}`;
		}
		return b.text ?? "";
	}
	if (b.type === "image") {
		const cap = (b.image_caption ?? []).join(" ").replace(/"/g, '\\"');
		return `![](${b.img_path ?? ""} "${cap}")`;
	}
	if (b.type === "list") {
		const ordered = /ordered|ol/i.test(b.sub_type ?? "");
		return (b.list_items ?? []).map((t, i) => (ordered ? `${i + 1}. ${t}` : `- ${t}`)).join("\n");
	}
	return "";
}

function buildPage(blocks: ContentBlock[]): Page {
	const items = blocks.filter((b) => KEEP_TYPES.has(b.type));
	const built: Item[] = [];
	let i = 0;
	while (i < items.length) {
		const cur = items[i];
		if (cur.type === "text" && cur.text_level === 1) {
			const parts: string[] = [cur.text ?? ""];
			const bboxes: Bbox[] = [cur.bbox ?? DEFAULT_BBOX];
			i++;
			while (i < items.length) {
				const next = items[i];
				if (!(next.type === "text" && next.text_level === 1)) break;
				parts.push(next.text ?? "");
				bboxes.push(next.bbox ?? DEFAULT_BBOX);
				i++;
			}
			built.push({ md: `# ${parts.join(" ")}`, centered: isCentered(unionBbox(bboxes)) });
			continue;
		}
		const md = blockToMd(cur).trim();
		if (md) {
			const isImage = cur.type === "image";
			const isTitle = cur.type === "text" && (cur.text_level ?? 0) > 0;
			const centered = isImage || (isTitle && isCentered(cur.bbox ?? DEFAULT_BBOX));
			built.push({ md, centered });
		}
		i++;
	}
	return built;
}

function groupBlocksByPage(blocks: ContentBlock[]): Map<number, ContentBlock[]> {
	const map = new Map<number, ContentBlock[]>();
	for (const b of blocks) {
		const idx = b.page_idx ?? 0;
		const arr = map.get(idx);
		if (arr) arr.push(b);
		else map.set(idx, [b]);
	}
	return map;
}

const CHARS_PER_LINE = 60;
const LINE_PX = 28;
const BLOCK_MARGIN_PX = 16;
const IMAGE_RESERVE_PX = 600;
const HEADING_LINE_PX: Record<number, number> = { 1: 56, 2: 48, 3: 40, 4: 36 };
const HEADING_REGEX = /^(#{1,4})\s/;

function estimateItemHeight(item: Item): number {
	if (item.md.startsWith("![")) return IMAGE_RESERVE_PX + BLOCK_MARGIN_PX;
	const headingMatch = item.md.match(HEADING_REGEX);
	if (headingMatch) {
		const level = headingMatch[1].length;
		const lines = Math.max(1, Math.ceil(item.md.length / CHARS_PER_LINE));
		return lines * (HEADING_LINE_PX[level] ?? 32) + BLOCK_MARGIN_PX;
	}
	const lines = item.md.split("\n").reduce((sum, line) => sum + Math.max(1, Math.ceil(line.length / CHARS_PER_LINE)), 0);
	return lines * LINE_PX + BLOCK_MARGIN_PX;
}

const estimatePageHeight = (page: Page): number =>
	Math.max(
		200,
		page.reduce((sum, it) => sum + estimateItemHeight(it), 0),
	);

type MarkdownProps = React.ComponentProps<typeof ReactMarkdown>;

const MARKDOWN_REMARK_PLUGINS: MarkdownProps["remarkPlugins"] = [remarkGfm, remarkMath];
const MARKDOWN_REHYPE_PLUGINS: MarkdownProps["rehypePlugins"] = [
	rehypeKatex,
	rehypeRaw,
	rehypeSlug,
	rehypeAutolinkHeadings,
	[rehypeHighlight, { ignoreMissing: true }],
];

const MARKDOWN_COMPONENTS = {
	h1: ({ children }: { children?: React.ReactNode }) => (
		<h1 className="mb-2 break-inside-avoid text-2xl font-semibold typeface-arizona text-neutral-900">{children}</h1>
	),
	h2: ({ children }: { children?: React.ReactNode }) => (
		<h2 className="mb-2 break-inside-avoid text-xl font-semibold typeface-arizona text-neutral-900">{children}</h2>
	),
	h3: ({ children }: { children?: React.ReactNode }) => (
		<h3 className="mb-2 break-inside-avoid text-lg font-semibold typeface-arizona text-neutral-900">{children}</h3>
	),
	h4: ({ children }: { children?: React.ReactNode }) => (
		<h4 className="mb-2 break-inside-avoid text-base font-semibold typeface-arizona text-neutral-900">{children}</h4>
	),
	p: ({ children }: { children?: React.ReactNode }) => (
		<div className="my-2 text-lg typeface-arizona text-neutral-800">{children}</div>
	),
	li: ({ children }: { children?: React.ReactNode }) => (
		<div className="my-2 text-lg typeface-arizona text-neutral-800">{children}</div>
	),
	table: ({ children }: { children?: React.ReactNode }) => (
		<table className="my-4 w-full border-collapse break-inside-avoid text-sm">{children}</table>
	),
	thead: ({ children }: { children?: React.ReactNode }) => (
		<thead className="break-inside-avoid bg-neutral-100">{children}</thead>
	),
	tr: ({ children }: { children?: React.ReactNode }) => (
		<tr className="break-inside-avoid border-b border-neutral-200">{children}</tr>
	),
	th: ({ children }: { children?: React.ReactNode }) => (
		<th className="break-inside-avoid px-2 py-1 text-left font-semibold typeface-arizona text-neutral-900">{children}</th>
	),
	td: ({ children }: { children?: React.ReactNode }) => (
		<td className="break-inside-avoid px-2 py-1 align-top typeface-arizona text-neutral-800">{children}</td>
	),
	img: ({ src, title }: { src?: string | Blob; title?: string }) => (
		<span className="break-inside-avoid">
			<Figure src={src as string} caption={title as string} />
		</span>
	),
	code: (props: { inline?: boolean; className?: string; children?: React.ReactNode }) => {
		const { inline, className, children } = props;
		if (inline) {
			return <code className="break-inside-avoid rounded bg-neutral-100 px-1 py-0.5 text-sm">{children}</code>;
		}
		return (
			<pre className="my-4 break-inside-avoid overflow-x-auto rounded-md bg-neutral-100 p-3 text-xs whitespace-pre-wrap wrap-break-word">
				<code className={className}>{children}</code>
			</pre>
		);
	},
};

const LOADING_QUOTES: string[] = [
	'"Somewhere, something incredible is waiting to be known." — Carl Sagan',
	'"I have no special talent. I am only passionately curious." — Albert Einstein',
	'"The mind is not a vessel to be filled, but a fire to be kindled." — Plutarch',
	'"Curiosity and creativity are intelligence having fun." — Albert Einstein',
	"\"I would rather have questions that can't be answered than answers that can't be questioned.\" — Richard Feynman",
	'"Wonder is the seedbed of science; curiosity is its laborer." — Carl Sagan',
	'"Education is not the filling of a pail, but the lighting of a fire." — W. B. Yeats',
	'"Study hard what interests you the most in the most undisciplined, irreverent and original manner possible." — Richard Feynman',
	'"The cure for boredom is curiosity. There is no cure for curiosity." — Dorothy Parker',
	'"Let your curiosity be greater than your fear." — Pema Chödrön',
	'"Pay attention. Be astonished. Tell about it." — Mary Oliver',
	'"When you do things from your soul, you feel a river moving in you, a joy." — Rumi',
	'"Books are uniquely portable magic." — Stephen King',
	'"A book is a dream that you hold in your hand." — Neil Gaiman',
	'"I cannot remember the books I\'ve read any more than the meals I have eaten; even so, they have made me." — Ralph Waldo Emerson',
	'"Some books leave us free and some books make us free." — Ralph Waldo Emerson',
	'"Reading is to the mind what exercise is to the body." — Joseph Addison',
	'"We read to know we are not alone." — C. S. Lewis',
	'"A reader lives a thousand lives before he dies." — George R. R. Martin',
	'"Learning never exhausts the mind." — Leonardo da Vinci',
	'"What we learn with pleasure we never forget." — Alfred Mercier',
	'"The world is a book, and those who do not travel read only one page." — Augustine',
	'"Be curious, not judgmental." — Walt Whitman',
	'"There is no end to education. The whole of life is a process of learning." — Jiddu Krishnamurti',
	'"The important thing is not to stop questioning." — Albert Einstein',
];

let sessionQuote: string | null = null;
function getSessionQuote(): string {
	if (sessionQuote === null) {
		sessionQuote = LOADING_QUOTES[Math.floor(Math.random() * LOADING_QUOTES.length)];
	}
	return sessionQuote;
}

function LoadingOverlay() {
	const [quote, setQuote] = useState<string | null>(null);
	useEffect(() => {
		setQuote(getSessionQuote());
	}, []);
	const [body, attribution] = quote ? quote.split(" — ") : ["", ""];
	return (
		<div className="fixed inset-0 z-50 flex items-center justify-center bg-neutral-50/95 px-8">
			<div className="flex w-full flex-col items-start gap-2 max-w-2xl">
				<span className="typeface-arizona text-lg italic text-neutral-700 min-h-14">
					{quote && (
						<>
							{body}
							<br />— {attribution}
						</>
					)}
				</span>
				<div className="w-full italic gap-2 flex items-center">
					<CircleNotchIcon size={16} className="shrink-0 animate-spin text-neutral-500" />
					Preparing your content
				</div>
			</div>
		</div>
	);
}

type TitleData = NonNullable<Awaited<ReturnType<typeof getTitleById>>>;

function ReaderContent() {
	const searchParams = useSearchParams();
	const titleId = searchParams.get("titleId");

	const [title, setTitle] = useState<TitleData | null>(null);
	const [titleError, setTitleError] = useState(false);

	useEffect(() => {
		if (!titleId) return;

		let cancelled = false;

		(async () => {
			const t = await getTitleById(titleId);
			if (cancelled) return;
			if (!t) {
				setTitleError(true);
				return;
			}
			setTitle(t);
			putTitle(titleId, { lastViewed: new Date().toISOString() });
		})();

		return () => {
			cancelled = true;
		};
	}, []);

	if (!titleId) {
		return (
			<div className="h-screen w-screen flex items-center justify-center">
				<p className="typeface-diatype text-neutral-500">Missing titleId</p>
			</div>
		);
	}
	if (titleError) {
		return (
			<div className="h-screen w-screen flex items-center justify-center">
				<p className="typeface-diatype text-neutral-500">Title not found</p>
			</div>
		);
	}
	if (!title) return <LoadingOverlay />;

	return <ReaderShell titleId={titleId} title={title} />;
}

const FALLBACK_PAGE_HEIGHT = 1200;
const PREFETCH_AHEAD = 10;
const PREFETCH_BEHIND = 5;

function ReaderShell({ titleId, title }: { titleId: string; title: TitleData }) {
	const router = useRouter();
	const initialPageNumber = typeof title.pageNumber === "number" ? title.pageNumber : 0;
	const titleName = title.title;
	const titleAuthor = title.author ?? "";
	const toc: TocEntry[] = Array.isArray(title.toc) ? (title.toc as TocEntry[]) : [];
	const pageCount = typeof title.pageCount === "number" ? title.pageCount : 0;

	const [isLoading, setIsLoading] = useState(true);
	const [pages, setPages] = useState<(Page | undefined)[]>(() => Array(pageCount).fill(undefined));
	const [pageNumber, setPageNumber] = useState(initialPageNumber);
	const [tocOpen, setTocOpen] = useState(false);

	const parentRef = useRef<HTMLDivElement | null>(null);
	const hasInitializedSaveRef = useRef(false);
	const hasInitializedScrollRef = useRef(false);
	const inflightRef = useRef<Set<number>>(new Set());

	const questions = useQuestions();

	const estimateSize = useCallback(
		(index: number) => {
			const p = pages[index];
			return p ? estimatePageHeight(p) : FALLBACK_PAGE_HEIGHT;
		},
		[pages],
	);

	const virtualizer = useVirtualizer({
		count: pageCount,
		getScrollElement: () => parentRef.current,
		estimateSize,
		overscan: 4,
		getItemKey: (index) => index,
	});

	useLayoutEffect(() => {
		if (hasInitializedScrollRef.current) return;
		if (pageCount === 0) return;
		hasInitializedScrollRef.current = true;

		const target = Math.min(Math.max(0, initialPageNumber), pageCount - 1);
		if (target > 0) {
			virtualizer.scrollToIndex(target, { align: "start" });
		}
	}, [pageCount, initialPageNumber, virtualizer]);

	useEffect(() => {
		if (pageCount > 0 && pages[initialPageNumber]) setIsLoading(false);
	}, [pages, initialPageNumber, pageCount]);

	const virtualItems = virtualizer.getVirtualItems();
	useEffect(() => {
		if (pageCount === 0) return;
		const lo = virtualItems.length
			? Math.max(0, virtualItems[0].index - PREFETCH_BEHIND)
			: Math.max(0, initialPageNumber - PREFETCH_BEHIND);
		const hi = virtualItems.length
			? Math.min(pageCount - 1, virtualItems[virtualItems.length - 1].index + PREFETCH_AHEAD)
			: Math.min(pageCount - 1, initialPageNumber + PREFETCH_AHEAD);

		let i = lo;
		while (i <= hi) {
			while (i <= hi && (pages[i] !== undefined || inflightRef.current.has(i))) i++;
			if (i > hi) break;
			let j = i;
			while (j <= hi && pages[j] === undefined && !inflightRef.current.has(j)) j++;
			const start = i;
			const end = j - 1;
			for (let k = start; k <= end; k++) inflightRef.current.add(k);
			void getContentList(titleId, { startPage: start, endPage: end })
				.then((blocks: ContentBlock[] | undefined) => {
					if (!blocks) return;
					const byPage = groupBlocksByPage(blocks);
					setPages((prev) => {
						const next = prev.slice();
						for (let idx = start; idx <= end; idx++) {
							next[idx] = buildPage(byPage.get(idx) ?? []);
						}
						return next;
					});
				})
				.finally(() => {
					for (let k = start; k <= end; k++) inflightRef.current.delete(k);
				});
			i = j;
		}
	}, [virtualItems, pages, pageCount, initialPageNumber, titleId]);

	useEffect(() => {
		const el = parentRef.current;
		if (!el || pageCount === 0) return;
		const onScroll = () => {
			const items = virtualizer.getVirtualItems();
			if (items.length === 0) return;
			const center = el.scrollTop + el.clientHeight / 2;
			let closest = items[0];
			let dist = Math.abs(closest.start + (closest.end - closest.start) / 2 - center);
			for (const it of items) {
				const d = Math.abs(it.start + (it.end - it.start) / 2 - center);
				if (d < dist) {
					dist = d;
					closest = it;
				}
			}
			setPageNumber(closest.index);
		};
		el.addEventListener("scroll", onScroll, { passive: true });
		window.addEventListener("resize", onScroll);
		return () => {
			el.removeEventListener("scroll", onScroll);
			window.removeEventListener("resize", onScroll);
		};
	}, [pageCount, virtualizer]);

	useEffect(() => {
		if (!hasInitializedSaveRef.current) {
			hasInitializedSaveRef.current = true;
			return;
		}
		const t = setTimeout(() => {
			putTitle(titleId, { pageNumber });
		}, 500);
		return () => clearTimeout(t);
	}, [titleId, pageNumber]);

	return (
		<div className="relative flex h-svh w-svw flex-col overflow-hidden bg-neutral-50">
			<nav className="z-50 flex typeface-arizona h-10 xl:h-16 w-full items-center justify-between border-b border-neutral-200 bg-neutral-50 px-4">
				<Button onClick={() => router.push("/library")} variant="ghost">
					<ArrowLeftIcon className="size-4 xl:size-6" />
					<span className="hidden lg:block">Return</span>
				</Button>

				<h1 className="uppercase text-sm xl:text-base typeface-arizona text-neutral-900 truncate max-w-[50%]">
					{titleName}
				</h1>

				<Button
					variant="ghost"
					onClick={() => {
						questions.close();
						setTocOpen(true);
					}}
					aria-label="Table of contents"
				>
					<ListBulletsIcon className="size-4 xl:size-6" />
					<span className="hidden lg:block">Contents</span>
				</Button>
			</nav>

			<main className="relative flex min-h-0 w-full flex-1 justify-center overflow-hidden">
				{isLoading && <LoadingOverlay />}
				<SelectionBubble contentRef={parentRef} onAskAI={questions.open} />

				<div
					ref={parentRef}
					className="h-full w-full overflow-x-hidden overflow-y-auto select-none px-4 md:px-32 lg:px-48 xl:px-96 2xl:px-[33svw]"
				>
					<div
						className="select-text"
						style={{
							height: `${virtualizer.getTotalSize()}px`,
							width: "100%",
							position: "relative",
						}}
					>
						{virtualizer.getVirtualItems().map((virtualItem) => (
							<div
								className="py-8"
								key={virtualItem.key}
								data-index={virtualItem.index}
								ref={virtualizer.measureElement}
								style={{
									position: "absolute",
									top: 0,
									left: 0,
									width: "100%",
									transform: `translateY(${virtualItem.start}px)`,
								}}
							>
								{pages[virtualItem.index] ? (
									pages[virtualItem.index]!.map((item, i) =>
										item.centered ? (
											<div key={i} className="flex w-full justify-center">
												<ReactMarkdown
													remarkPlugins={MARKDOWN_REMARK_PLUGINS}
													rehypePlugins={MARKDOWN_REHYPE_PLUGINS}
													components={MARKDOWN_COMPONENTS}
												>
													{item.md}
												</ReactMarkdown>
											</div>
										) : (
											<ReactMarkdown
												key={i}
												remarkPlugins={MARKDOWN_REMARK_PLUGINS}
												rehypePlugins={MARKDOWN_REHYPE_PLUGINS}
												components={MARKDOWN_COMPONENTS}
											>
												{item.md}
											</ReactMarkdown>
										),
									)
								) : (
									<div className="flex h-[1200px] w-full items-center justify-center text-neutral-400">
										<CircleNotchIcon size={24} className="animate-spin" />
									</div>
								)}
							</div>
						))}
					</div>
				</div>
			</main>

			<footer className="flex w-full flex-col items-center justify-center gap-4 px-32 py-1 lg:px-4 text-center text-xs typeface-diatype font-medium text-neutral-500">
				<p>
					Page {pageNumber + 1} of {pageCount} •{" "}
					{pageCount > 0 ? `${Math.round(((pageNumber + 1) / pageCount) * 100)}%` : "0%"}
				</p>
			</footer>

			<SideDrawer isOpen={questions.isOpen} onClose={questions.close} className="md:w-128">
				<QuestionsPanel
					questions={questions}
					titleId={titleId}
					title={titleName}
					author={titleAuthor}
					pageContent={(pages[pageNumber] ?? []).map((i) => i.md).join("\n\n")}
				/>
			</SideDrawer>

			<SideDrawer isOpen={tocOpen} onClose={() => setTocOpen(false)} className="md:w-128">
				<TocPanel
					onClose={() => setTocOpen(false)}
					entries={toc}
					onJump={(pdfPage) => {
						const idx = Math.max(0, Math.min(pageCount - 1, pdfPage - 1));
						virtualizer.scrollToIndex(idx, { align: "start" });
						setPageNumber(idx);
						setTocOpen(false);
					}}
				/>
			</SideDrawer>
		</div>
	);
}

function Figure({ src, caption }: { src: string; caption?: string }) {
	return (
		<span className="inline-block max-w-full">
			{/* eslint-disable-next-line @next/next/no-img-element */}
			<img src={src} alt="" className="h-auto max-w-full" />
			{caption && (
				<div className=" text-sm typeface-diatype text-neutral-800">
					<ReactMarkdown
						remarkPlugins={[remarkGfm, remarkMath]}
						rehypePlugins={[rehypeRaw, rehypeKatex]}
						components={{
							p: ({ children }) => <span className="text-sm lg:text-base typeface-diatype">{children}</span>,
						}}
					>
						{caption}
					</ReactMarkdown>
				</div>
			)}
		</span>
	);
}

export default function Page() {
	return (
		<Suspense fallback={<LoadingOverlay />}>
			<ReaderContent />
		</Suspense>
	);
}
