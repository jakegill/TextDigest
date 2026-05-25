"use client";
import { useEffect, useState, type RefObject } from "react";

export type SelectionPos = { top: number; left: number; text: string };

export type UseTextSelectionReturn = {
	pos: SelectionPos | null;
	clear: () => void;
};

const BUBBLE_OFFSET = 40;
const VIEWPORT_PAD_X = 24;
const VIEWPORT_PAD_Y = 8;
const BUBBLE_HEIGHT_RESERVE = 48;

export function useTextSelection(contentRef: RefObject<HTMLElement | null>): UseTextSelectionReturn {
	const [pos, setPos] = useState<SelectionPos | null>(null);

	useEffect(() => {
		const root = contentRef.current;
		if (!root) return;

		let pointerActive = false;
		let rafId: number | null = null;

		const measure = () => {
			rafId = null;
			if (pointerActive) return;
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
			const rects = range.getClientRects();
			const rect = rects.length ? rects[rects.length - 1] : range.getBoundingClientRect();
			if (rect.width === 0 && rect.height === 0) return;
			const rawTop = rect.top - BUBBLE_OFFSET;
			const rawLeft = rect.left + rect.width / 2;
			setPos({
				top: Math.min(Math.max(rawTop, VIEWPORT_PAD_Y), window.innerHeight - BUBBLE_HEIGHT_RESERVE),
				left: Math.min(Math.max(rawLeft, VIEWPORT_PAD_X), window.innerWidth - VIEWPORT_PAD_X),
				text,
			});
		};

		const schedule = () => {
			if (rafId !== null) return;
			rafId = requestAnimationFrame(measure);
		};

		const onPointerDown = (e: PointerEvent) => {
			pointerActive = true;
			const target = e.target as Node | null;
			if (target && !root.contains(target)) setPos(null);
		};
		const onPointerUp = () => {
			pointerActive = false;
			schedule();
		};
		const onPointerCancel = () => {
			pointerActive = false;
		};
		const onSelectionChange = () => schedule();
		const onScroll = () => setPos(null);
		const onResize = () => setPos(null);

		document.addEventListener("pointerdown", onPointerDown);
		document.addEventListener("pointerup", onPointerUp);
		document.addEventListener("pointercancel", onPointerCancel);
		document.addEventListener("selectionchange", onSelectionChange);
		root.addEventListener("scroll", onScroll, { passive: true });
		window.addEventListener("resize", onResize);

		return () => {
			if (rafId !== null) cancelAnimationFrame(rafId);
			document.removeEventListener("pointerdown", onPointerDown);
			document.removeEventListener("pointerup", onPointerUp);
			document.removeEventListener("pointercancel", onPointerCancel);
			document.removeEventListener("selectionchange", onSelectionChange);
			root.removeEventListener("scroll", onScroll);
			window.removeEventListener("resize", onResize);
		};
	}, [contentRef]);

	return {
		pos,
		clear: () => setPos(null),
	};
}
