"use client";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowLeftIcon, CircleNotchIcon, ListBulletsIcon } from "@phosphor-icons/react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
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
import { useQuestions } from "@/hooks/useQuestions";
import { getContentList } from "@/services/api/getContentList";
import { getTitleById } from "@/services/api/getTitleById";
import { putTitle } from "@/services/api/putTitle";

export const dynamic = "force-dynamic";

type Bbox = [number, number, number, number];

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

const PAGE_NORM = 1000;
const WIDE_FRAC = 0.7;
const Y_OVERLAP_MIN = 0.5;
const CENTER_TOL = 80;
const DEFAULT_BBOX: Bbox = [0, 0, PAGE_NORM, PAGE_NORM];

type Justify = "start" | "center" | "end";
type Item = { md: string; bbox: Bbox };
type Row = { items: Item[]; justify: Justify };
type Page = Row[];

const JUSTIFY_CLASS: Record<Justify, string> = {
	start: "justify-start",
	center: "justify-center",
	end: "justify-end",
};

const unionBbox = (boxes: Bbox[]): Bbox => [
	Math.min(...boxes.map((b) => b[0])),
	Math.min(...boxes.map((b) => b[1])),
	Math.max(...boxes.map((b) => b[2])),
	Math.max(...boxes.map((b) => b[3])),
];

const isWide = (b: Bbox) => b[2] - b[0] > WIDE_FRAC * PAGE_NORM;

const yOverlapFrac = (a: Bbox, b: Bbox) => {
	const top = Math.max(a[1], b[1]);
	const bottom = Math.min(a[3], b[3]);
	const inter = Math.max(0, bottom - top);
	const minH = Math.min(a[3] - a[1], b[3] - b[1]);
	return minH > 0 ? inter / minH : 0;
};

const justifyFor = (left: number, right: number): Justify => {
	const mid = (left + right) / 2;
	if (Math.abs(mid - PAGE_NORM / 2) < CENTER_TOL) return "center";
	return mid < PAGE_NORM / 2 ? "start" : "end";
};

function buildPages(blocks: ContentBlock[]): Page[] {
	if (!blocks.length) return [];
	const max = blocks.reduce((m, b) => Math.max(m, b.page_idx ?? 0), 0);
	const grouped: ContentBlock[][] = Array.from({ length: max + 1 }, () => []);
	for (const b of blocks) grouped[b.page_idx ?? 0].push(b);

	const toMd = (b: ContentBlock) => {
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
	};

	const KEEP = new Set(["text", "image", "list"]);

	return grouped.map((rawItems) => {
		const items = rawItems.filter((b) => KEEP.has(b.type));

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
				built.push({ md: `# ${parts.join(" ")}`, bbox: unionBbox(bboxes) });
				continue;
			}
			const md = toMd(cur).trim();
			if (md) built.push({ md, bbox: cur.bbox ?? DEFAULT_BBOX });
			i++;
		}

		const rows: Item[][] = [];
		for (const it of built) {
			const last = rows[rows.length - 1];
			const lastItem = last?.[last.length - 1];
			const canAppend =
				!!lastItem &&
				!isWide(it.bbox) &&
				!isWide(lastItem.bbox) &&
				yOverlapFrac(lastItem.bbox, it.bbox) > Y_OVERLAP_MIN;
			if (canAppend) {
				last!.push(it);
			} else {
				rows.push([it]);
			}
		}

		return rows.map((rowItems): Row => {
			const left = Math.min(...rowItems.map((it) => it.bbox[0]));
			const right = Math.max(...rowItems.map((it) => it.bbox[2]));
			return { items: rowItems, justify: justifyFor(left, right) };
		});
	});
}

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

function ReaderShell({ titleId, title }: { titleId: string; title: TitleData }) {
	const router = useRouter();
	const initialPageNumber = typeof title.pageNumber === "number" ? title.pageNumber : 0;
	const titleName = title.title;
	const titleAuthor = title.author ?? "";
	const toc: TocEntry[] = Array.isArray(title.toc) ? (title.toc as TocEntry[]) : [];

	const [isLoading, setIsLoading] = useState(true);
	const [pages, setPages] = useState<Page[]>([]);
	const [pageNumber, setPageNumber] = useState(initialPageNumber);
	const [tocOpen, setTocOpen] = useState(false);

	const parentRef = useRef<HTMLDivElement | null>(null);
	const hasInitializedSaveRef = useRef(false);

	const setSentinel = useCallback((el: HTMLDivElement | null) => {
		if (!el || !parentRef.current) return;
		const obs = new IntersectionObserver(
			(entries) => {
				if (entries.some((e) => e.isIntersecting)) {
					requestAnimationFrame(() => {
						setIsLoading(false);
						obs.disconnect();
					});
				}
			},
			{ root: parentRef.current, threshold: 0 },
		);
		obs.observe(el);
	}, []);

	const questions = useQuestions();

	const virtualizer = useVirtualizer({
		count: pages.length,
		getScrollElement: () => parentRef.current,
		estimateSize: () => 1000,
		overscan: 8,
		initialOffset: initialPageNumber * 1000,
	});

	useEffect(() => {
		let cancelled = false;
		(async () => {
			const blocks: ContentBlock[] | undefined = await getContentList(titleId);
			if (cancelled || !blocks) return;
			setPages(buildPages(blocks));
		})();
		return () => {
			cancelled = true;
		};
	}, [titleId]);

	useEffect(() => {
		const el = parentRef.current;
		if (!el || pages.length === 0) return;
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
	}, [pages.length, virtualizer]);

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
			<nav className="z-50 flex h-16 w-full items-center justify-between border-b border-neutral-200 bg-neutral-50 px-4">
				<Button onClick={() => router.push("/library")} variant="ghost">
					<ArrowLeftIcon />
					Return
				</Button>

				<h1 className="uppercase typeface-arizona text-neutral-900 truncate max-w-[50%]">{titleName}</h1>

				<Button
					variant="ghost"
					onClick={() => {
						questions.close();
						setTocOpen(true);
					}}
					aria-label="Table of contents"
				>
					<ListBulletsIcon />
					Contents
				</Button>
			</nav>

			<main className="relative flex min-h-0 w-full flex-1 justify-center overflow-hidden">
				{isLoading && <LoadingOverlay />}
				<SelectionBubble contentRef={parentRef} onAskAI={questions.open} />

				<div
					ref={parentRef}
					className="h-full w-full overflow-x-hidden overflow-y-auto px-4 md:px-32 lg:px-48 xl:px-96 2xl:px-[33svw]"
				>
					<div
						style={{
							height: `${virtualizer.getTotalSize()}px`,
							width: "100%",
							position: "relative",
						}}
					>
						{virtualizer.getVirtualItems().map((virtualItem) => (
							<div
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
								{virtualItem.index === initialPageNumber && <div ref={setSentinel} className="h-px w-px" />}
								{pages[virtualItem.index]?.map((row, i) => {
									const lonelyWide = row.items.length === 1 && isWide(row.items[0].bbox);
									if (lonelyWide) {
										return (
											<ReactMarkdown
												key={i}
												remarkPlugins={MARKDOWN_REMARK_PLUGINS}
												rehypePlugins={MARKDOWN_REHYPE_PLUGINS}
												components={MARKDOWN_COMPONENTS}
											>
												{row.items[0].md}
											</ReactMarkdown>
										);
									}
									if (row.items.length === 1) {
										return (
											<div key={i} className={`flex w-full ${JUSTIFY_CLASS[row.justify]}`}>
												<ReactMarkdown
													remarkPlugins={MARKDOWN_REMARK_PLUGINS}
													rehypePlugins={MARKDOWN_REHYPE_PLUGINS}
													components={MARKDOWN_COMPONENTS}
												>
													{row.items[0].md}
												</ReactMarkdown>
											</div>
										);
									}
									const left = Math.min(...row.items.map((it) => it.bbox[0]));
									const right = Math.max(...row.items.map((it) => it.bbox[2]));
									const widthPct = ((right - left) / PAGE_NORM) * 100;
									const cols = row.items.map((it) => `${it.bbox[2] - it.bbox[0]}fr`).join(" ");
									return (
										<div key={i} className={`flex w-full ${JUSTIFY_CLASS[row.justify]}`}>
											<div
												className="grid items-end gap-4"
												style={{ gridTemplateColumns: cols, width: `${widthPct}%` }}
											>
												{row.items.map((item, j) => (
													<div key={j} className="min-w-0">
														<ReactMarkdown
															remarkPlugins={MARKDOWN_REMARK_PLUGINS}
															rehypePlugins={MARKDOWN_REHYPE_PLUGINS}
															components={MARKDOWN_COMPONENTS}
														>
															{item.md}
														</ReactMarkdown>
													</div>
												))}
											</div>
										</div>
									);
								})}
							</div>
						))}
					</div>
				</div>
			</main>

			<footer className="flex w-full flex-col items-center justify-center gap-4 px-32 pt-4 pb-4 text-center text-xs typeface-diatype font-medium text-neutral-500">
				<p>
					Page {pageNumber + 1} of {pages.length} •{" "}
					{pages.length > 0 ? `${Math.round(((pageNumber + 1) / pages.length) * 100)}%` : "0%"}
				</p>
			</footer>

			<QuestionsPanel
				questions={questions}
				titleId={titleId}
				title={titleName}
				author={titleAuthor}
				pageContent={(pages[pageNumber] ?? []).flatMap((r) => r.items.map((i) => i.md)).join("\n\n")}
			/>

			<TocPanel
				isOpen={tocOpen}
				onClose={() => setTocOpen(false)}
				entries={toc}
				onJump={(pdfPage) => {
					const idx = Math.max(0, Math.min(pages.length - 1, pdfPage - 1));
					virtualizer.scrollToIndex(idx, { align: "start" });
					setPageNumber(idx);
					setTocOpen(false);
				}}
			/>
		</div>
	);
}

function Figure({ src, caption }: { src: string; caption?: string }) {
	return (
		<span className="inline-block max-w-full">
			{/* eslint-disable-next-line @next/next/no-img-element */}
			<img src={src} alt="" className="h-auto max-w-full" />
			{caption && (
				<div className="text-center text-sm typeface-diatype text-neutral-800">
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
