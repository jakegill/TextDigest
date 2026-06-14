"use client";
import { Menu } from "@base-ui/react/menu";
import { UploadSimpleIcon, BooksIcon, MagnifyingGlassIcon, DotsThreeIcon, FileXIcon } from "@phosphor-icons/react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { FindTitlePanel } from "@/components/library/FindTitlePanel";
import { Button } from "@/components/ui/button";
import { SideDrawer } from "@/components/ui/side-drawer";
import { UploadDropzone, type UploadedTitle } from "@/components/upload-dropzone";
import { useFindTitle } from "@/hooks/useFindTitle";
import { deleteTitle } from "@/services/api/deleteTitle";
import { getTitleById } from "@/services/api/getTitleById";
import { getTitles } from "@/services/api/getTitles";
import type { TitleProgressEvent } from "@/services/api/titleEvents";
import { fuzzyIncludes } from "@/lib/fuzzy";

type TitleCard = {
	titleId: string;
	title: string;
	author: string;
	coverUrl: string;
	isProcessing: boolean;
	processingError?: string | null;
	lastViewed?: string;
};

const PROCESSING_POLL_MS = 3000;

export default function Page() {
	const [titles, setTitles] = useState<TitleCard[]>([]);
	const [isLoading, setIsLoading] = useState(true);
	const [query, setQuery] = useState("");
	const findTitle = useFindTitle();

	useEffect(() => {
		getTitles()
			.then((rows) => {
				if (!rows) return;
				setTitles(
					rows.map((r: TitleCard) => ({
						titleId: r.titleId,
						title: r.title,
						author: r.author,
						coverUrl: r.coverUrl,
						isProcessing: r.isProcessing,
						processingError: r.processingError ?? null,
						lastViewed: r.lastViewed,
					})),
				);
			})
			.finally(() => setIsLoading(false));
	}, []);

	// Background safety net: while any card shows isProcessing, poll the
	// title doc every few seconds. Covers the case where the SSE stream was
	// never opened, was killed by a server restart, or was abandoned by a
	// remount/page refresh. Exits as soon as no cards are processing.
	useEffect(() => {
		const processing = titles.filter((t) => t.isProcessing);
		if (processing.length === 0) return;

		const tick = async () => {
			const results = await Promise.all(
				processing.map((t) =>
					getTitleById(t.titleId).then(
						(d) =>
							d
								? {
										titleId: t.titleId,
										isProcessing: !!d.isProcessing,
										coverUrl: d.coverUrl as string,
										processingError: (d.processingError as string | null) ?? null,
									}
								: null,
						() => null,
					),
				),
			);
			setTitles((prev) =>
				prev.map((p) => {
					const hit = results.find((r) => r && r.titleId === p.titleId);
					if (!hit) return p;
					return {
						...p,
						isProcessing: hit.isProcessing,
						coverUrl: hit.coverUrl || p.coverUrl,
						processingError: hit.processingError,
					};
				}),
			);
		};

		const id = setInterval(tick, PROCESSING_POLL_MS);
		return () => clearInterval(id);
	}, [titles]);

	const handleUploaded = (t: UploadedTitle) => {
		setTitles((prev) => [
			{
				titleId: t.titleId,
				title: t.title,
				author: t.author,
				coverUrl: t.coverUrl,
				isProcessing: t.isProcessing,
				processingError: t.processingError ?? null,
			},
			...prev.filter((p) => p.titleId !== t.titleId),
		]);
	};

	const handleProgress = (e: TitleProgressEvent) => {
		if (!e.titleId) return;
		setTitles((prev) =>
			prev.map((p) =>
				p.titleId === e.titleId
					? {
							...p,
							isProcessing: e.stage !== "done" && e.stage !== "failed",
							processingError: e.stage === "failed" ? (e.error ?? "Processing failed") : p.processingError,
						}
					: p,
			),
		);
	};

	const handleDelete = async (titleId: string) => {
		setTitles((prev) => prev.filter((p) => p.titleId !== titleId));
		await deleteTitle(titleId);
	};

	const filtered = query ? titles.filter((t) => fuzzyIncludes(t.title, query) || fuzzyIncludes(t.author, query)) : titles;

	const recent = filtered
		.filter((t) => t.lastViewed)
		.sort((a, b) => (b.lastViewed ?? "").localeCompare(a.lastViewed ?? ""))
		.slice(0, 9);

	return (
		<div className="h-[100svh] w-[100svw] flex justify-center">
			<main className="max-w-full px-4 py-8 xl:max-w-3xl xl:py-16 w-full space-y-4 xl:space-y-8">
				<div className="flex items-center justify-between">
					<h1 className="text-xl xl:text-3xl underline items-center typeface-arizona flex gap-1">
						<BooksIcon className="text-neutral-600 size-6 xl:size-8" />
						My Library
					</h1>
					<div className="flex items-center gap-2">
						<Button
							size="lg"
							variant="outline"
							onClick={() => findTitle.open()}
							className="w-fi text-sm t typeface-diatype rounded-none transition-colors duration-300 border cursor-pointer xltext-base md:py-4"
						>
							<MagnifyingGlassIcon className="hidden xl:block" />
							Find title
						</Button>
						<UploadDropzone onUploaded={handleUploaded} onProgress={handleProgress}>
							<Button
								size="lg"
								variant="default"
								className="w-fit typeface-diatype text-sm rounded-none hover:bg-primary-700 transition-colors duration-300 border cursor-pointer  xl:text-base md:py-4"
							>
								<UploadSimpleIcon className="hidden xl:block" />
								Upload title
							</Button>
						</UploadDropzone>
					</div>
				</div>

				<div className="relative">
					<MagnifyingGlassIcon className="absolute size-3 xl:size-4 left-3 top-1/2 -translate-y-1/2 text-neutral-500" />
					<input
						type="search"
						value={query}
						onChange={(e) => setQuery(e.target.value)}
						placeholder="Search titles…"
						className="w-full typeface-diatype border bg-white border-neutral-200 py-1 xl:py-2 pl-9 pr-3 text-base xl:placeholder:text-base placeholder:text-sm placeholder:text-neutral-500 focus:border-neutral-400 focus:outline-none transition-colors"
					/>
				</div>

				{recent.length > 0 && (
					<section className="space-y-3">
						<h2 className="text-xl typeface-arizona text-neutral-600 font-medium">Recent titles</h2>
						<ul className="grid grid-cols-3 gap-4 sm:grid-cols-3 md:grid-cols-4 md:gap-6 md:[&>li:nth-child(9)]:hidden">
							{recent.map((t) => (
								<TitleCardView key={t.titleId} title={t} onDelete={handleDelete} />
							))}
						</ul>
					</section>
				)}

				<section className="space-y-2">
					<h2 className="text-xl typeface-arizona text-neutral-600 font-medium">All titles</h2>
					{isLoading ? (
						<SkeletonGrid />
					) : filtered.length === 0 ? (
						<div className="space-y-2">
							<p className="text-sm xl:text-base text-neutral-500 flex flex-col typeface-diatype">
								{titles.length === 0 ? "No titles yet — upload one to get started." : "No matches."}
							</p>
							{titles.length === 0 && (
								<Button
									size="lg"
									variant="outline"
									onClick={() => findTitle.open()}
									className="w-fi text-sm t typeface-diatype bg-neutral-100 rounded-none transition-colors duration-300 border cursor-pointer xltext-base md:py-4"
								>
									<MagnifyingGlassIcon className="hidden xl:block" />
									Find title
								</Button>
							)}
						</div>
					) : (
						<ul className="grid grid-cols-3 sm:grid-cols-3 md:grid-cols-4 gap-6">
							{filtered
								.sort((a, b) => a.title.localeCompare(b.title))
								.map((t) => (
									<TitleCardView key={t.titleId} title={t} onDelete={handleDelete} />
								))}
						</ul>
					)}
				</section>
			</main>
			<SideDrawer isOpen={findTitle.isOpen} onClose={findTitle.close} className="lg:w-128">
				<FindTitlePanel
					findTitle={findTitle}
					library={titles.map((t) => ({ title: t.title, author: t.author }))}
					onUploaded={handleUploaded}
					onProgress={handleProgress}
				/>
			</SideDrawer>
		</div>
	);
}

function TitleCardView({ title, onDelete }: { title: TitleCard; onDelete: (titleId: string) => void }) {
	const failed = !title.isProcessing && !!title.processingError;
	const blockIfUnready = (e: React.MouseEvent) => {
		if (failed) {
			e.preventDefault();
			toast.error("Processing failed", {
				description: title.processingError ?? undefined,
			});
			return;
		}
		if (!title.isProcessing) return;
		e.preventDefault();
		toast.warning("Still processing", {
			description: "Processing takes ~3-10 minutes, depending on how large the content is.",
		});
	};
	const linkClass = title.isProcessing || failed ? "cursor-not-allowed" : "cursor-pointer";

	return (
		<li className="flex flex-col gap-2">
			<Link
				href={`/e-reader?titleId=${title.titleId}`}
				aria-disabled={title.isProcessing || failed}
				onClick={blockIfUnready}
				className={`${linkClass} relative aspect-3/4 bg-neutral-100 overflow-hidden block`}
			>
				<Image
					src={title.coverUrl}
					alt={title.title}
					fill
					sizes="(min-width: 768px) 200px, 45vw"
					className="object-cover group hover:border-primary-400 transition-colors duration-300 border"
				/>
				{title.isProcessing && (
					<div className="absolute inset-x-0 bottom-0 bg-black/60 text-white text-[10px] typeface-diatype uppercase tracking-wide py-1 text-center pointer-events-none">
						processing
					</div>
				)}
				{failed && (
					<div className="absolute inset-x-0 bottom-0 bg-accent-red-800/80 text-white text-[10px] typeface-diatype uppercase tracking-wide py-1 text-center pointer-events-none">
						failed
					</div>
				)}
			</Link>
			<div className="relative group flex flex-col gap-1">
				<Link
					href={`/e-reader?titleId=${title.titleId}`}
					aria-disabled={title.isProcessing || failed}
					onClick={blockIfUnready}
					className={`flex flex-col gap-1 ${linkClass}`}
				>
					<p className="text-sm typeface-diatype text-neutral-800 line-clamp-2 capitalize">{title.title}</p>
					<p className="text-xs typeface-diatype text-neutral-500 line-clamp-1 capitalize">{title.author}</p>
				</Link>

				<Menu.Root>
					<Menu.Trigger
						aria-label="Title actions"
						className="absolute bottom-0 right-0 border border-neutral-200 bg-neutral-50 text-neutral-700 cursor-pointer opacity-0 group-hover:opacity-100 data-popup-open:opacity-100 transition-opacity"
					>
						<DotsThreeIcon size={20} />
					</Menu.Trigger>
					<Menu.Portal>
						<Menu.Positioner side="bottom" align="end" sideOffset={4}>
							<Menu.Popup className="border border-neutral-200 bg-white text-sm typeface-diatype text-neutral-700 shadow-md outline-none min-w-32 py-1">
								<Menu.Item
									onClick={() => onDelete(title.titleId)}
									className="flex text-red-600 items-center gap-2 px-3 py-1.5 cursor-pointer outline-none data-highlighted:bg-neutral-100"
								>
									<FileXIcon size={16} />
									Delete
								</Menu.Item>
							</Menu.Popup>
						</Menu.Positioner>
					</Menu.Portal>
				</Menu.Root>
			</div>
		</li>
	);
}

function SkeletonGrid() {
	return (
		<ul
			className="grid grid-cols-3 sm:grid-cols-3 md:grid-cols-4 gap-6 md:[&>li:nth-child(9)]:hidden"
			aria-busy="true"
			aria-label="Loading titles"
		>
			{Array.from({ length: 9 }).map((_, i) => (
				<li key={i} className="flex flex-col gap-2">
					<div className="relative aspect-3/4 bg-neutral-200 animate-pulse" />
					<div className="h-3 w-3/4 bg-neutral-200 animate-pulse" />
					<div className="h-2.5 w-1/2 bg-neutral-200 animate-pulse" />
				</li>
			))}
		</ul>
	);
}
