"use client";
import { SparkleIcon } from "@phosphor-icons/react";
import { useEffect, useState, type RefObject } from "react";

type Pos = { top: number; left: number; text: string } | null;

export function SelectionBubble({
	contentRef,
	onAskAI,
}: {
	contentRef: RefObject<HTMLDivElement | null>;
	onAskAI: (text: string) => void;
}) {
	const [pos, setPos] = useState<Pos>(null);

	useEffect(() => {
		const root = contentRef.current;
		if (!root) return;

		const measure = () => {
			const sel = window.getSelection();
			if (!sel || sel.isCollapsed || sel.rangeCount === 0) {
				setPos(null);
				return;
			}
			const text = sel.toString().trim();
			if (!text) {
				setPos(null);
				return;
			}
			const range = sel.getRangeAt(0);
			if (!root.contains(range.commonAncestorContainer)) {
				setPos(null);
				return;
			}
			const rect = range.getBoundingClientRect();
			if (rect.width === 0 && rect.height === 0) return;
			setPos({
				top: rect.top + window.scrollY - 40,
				left: rect.left + window.scrollX + rect.width / 2,
				text,
			});
		};

		const hideOnOutsideMousedown = (e: MouseEvent) => {
			const target = e.target as Node | null;
			if (target && root.contains(target)) return;
			setPos(null);
		};

		document.addEventListener("mouseup", measure);
		document.addEventListener("selectionchange", measure);
		document.addEventListener("mousedown", hideOnOutsideMousedown);
		root.addEventListener("scroll", () => setPos(null), { passive: true });
		window.addEventListener("resize", () => setPos(null));
		return () => {
			document.removeEventListener("mouseup", measure);
			document.removeEventListener("selectionchange", measure);
			document.removeEventListener("mousedown", hideOnOutsideMousedown);
		};
	}, [contentRef]);

	if (!pos) return null;

	return (
		<button
			type="button"
			data-selection-bubble
			onMouseDown={(e) => {
				e.preventDefault();
				onAskAI(pos.text);
				setPos(null);
				window.getSelection()?.removeAllRanges();
			}}
			style={{ top: pos.top, left: pos.left, transform: "translateX(-50%)" }}
			className="fixed z-50 flex cursor-pointer items-center gap-1 rounded-md border bg-neutral-100 border-neutral-200  px-2 py-1 typeface-diatype shadow-md transition-colors duration-300 active:scale-95"
		>
			<SparkleIcon size={14} />
			Ask AI
		</button>
	);
}
