"use client";
import { SparkleIcon } from "@phosphor-icons/react";
import { type RefObject } from "react";

import { useTextSelection } from "@/hooks/useTextSelection";

export function SelectionBubble({
	contentRef,
	onAskAI,
}: {
	contentRef: RefObject<HTMLDivElement | null>;
	onAskAI: (text: string) => void;
}) {
	const { pos, clear } = useTextSelection(contentRef);
	if (!pos) return null;
	return (
		<button
			type="button"
			data-selection-bubble
			onPointerDown={(e) => {
				e.preventDefault();
				e.stopPropagation();
				onAskAI(pos.text);
				clear();
				window.getSelection()?.removeAllRanges();
			}}
			style={{ top: pos.top, left: pos.left, transform: "translateX(-50%)" }}
			className="fixed z-50 flex cursor-pointer items-center gap-1 rounded-md border bg-neutral-100 border-neutral-200 px-2 py-1 typeface-diatype shadow-md transition-colors duration-300 active:scale-95"
		>
			<SparkleIcon size={14} />
			Ask AI
		</button>
	);
}
