"use client";
import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

const IGNORE_OUTSIDE_CLICK = '[role="menu"],[role="menuitem"],[data-base-ui-popup],[data-selection-bubble]';

export function SideDrawer({
	isOpen,
	onClose,
	className,
	children,
}: {
	isOpen: boolean;
	onClose: () => void;
	className?: string;
	children: React.ReactNode;
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
			if (target.closest(IGNORE_OUTSIDE_CLICK)) return;
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
			className={cn(
				"fixed right-0 top-0 z-60 flex h-svh w-full flex-col border-l border-neutral-200 bg-neutral-50 shadow-xl transition-transform translate-x-full data-[open=true]:translate-x-0",
				className,
			)}
		>
			{children}
		</div>
	);
}
