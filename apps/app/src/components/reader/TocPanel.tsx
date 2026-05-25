"use client";
import { XIcon } from "@phosphor-icons/react";
import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";

export type TocEntry = {
	title: string;
	level: number;
	pdfPage: number;
	anchor: string;
};

const LEVEL_INDENT: Record<number, string> = {
	1: "pl-0",
	2: "pl-4",
	3: "pl-8",
	4: "pl-12",
};

const LEVEL_TEXT: Record<number, string> = {
	1: "text-base font-semibold text-neutral-900",
	2: "text-sm text-neutral-800",
	3: "text-sm text-neutral-600",
	4: "text-xs text-neutral-500",
};

export function TocPanel({
	isOpen,
	onClose,
	entries,
	onJump,
}: {
	isOpen: boolean;
	onClose: () => void;
	entries: TocEntry[];
	onJump: (pdfPage: number) => void;
}) {
	const panelRef = useRef<HTMLDivElement>(null);

	useEffect(() => {
		if (!isOpen) return;
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
			onClose();
		};
		document.addEventListener("mousedown", onPointerDown);
		return () => {
			cancelAnimationFrame(raf);
			document.removeEventListener("mousedown", onPointerDown);
		};
	}, [isOpen, onClose]);

	return (
		<div
			ref={panelRef}
			data-open={isOpen}
			className="fixed right-0 top-0 z-60 flex h-svh w-full flex-col border-l border-neutral-200 bg-neutral-50 shadow-xl transition-transform translate-x-full data-[open=true]:translate-x-0 md:w-105"
		>
			<div className="flex flex-shrink-0 h-16 items-center justify-between border-b border-neutral-200 px-4 py-3">
				<span className="font-medium typeface-diatype text-neutral-900">Contents</span>
				<Button variant="ghost" onClick={onClose} aria-label="Close">
					<XIcon className="size-6" />
				</Button>
			</div>

			<div className="flex flex-1 flex-col overflow-y-auto px-4 py-2">
				{entries.length === 0 ? (
					<div className="px-4 py-6 text-sm typeface-diatype text-neutral-500">
						No table of contents available for this title.
					</div>
				) : (
					entries.map((e, i) => {
						const lvl = Math.max(1, Math.min(4, e.level));
						return (
							<button
								key={i}
								onClick={() => onJump(e.pdfPage)}
								className={`flex cursor-pointer w-full items-baseline gap-3 rounded-md px-4 py-2 text-left transition-colors hover:bg-neutral-100 ${LEVEL_INDENT[lvl]}`}
							>
								<span className={`flex-1 truncate typeface-arizona ${LEVEL_TEXT[lvl]}`}>{e.title}</span>
								<span className="shrink-0 text-xs typeface-diatype text-neutral-500 tabular-nums">
									{e.pdfPage}
								</span>
							</button>
						);
					})
				)}
			</div>
		</div>
	);
}
