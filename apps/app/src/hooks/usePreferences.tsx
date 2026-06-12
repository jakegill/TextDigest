"use client";
import { useCallback, useEffect, useRef, useState } from "react";

import { getPreferences } from "@/services/api/getPreferences";
import { putPreferences } from "@/services/api/putPreferences";

export const TYPEFACE_OPTIONS = [
	{ value: "arizona", label: "Arizona", cssVar: "--font-arizona" },
	{ value: "literata", label: "Literata", cssVar: "--font-literata" },
	{ value: "bitter", label: "Bitter", cssVar: "--font-bitter" },
	{ value: "inter", label: "Inter", cssVar: "--font-inter" },
	{ value: "jost", label: "Jost", cssVar: "--font-jost" },
	{ value: "eb-garamond", label: "EB Garamond", cssVar: "--font-eb-garamond" },
	{ value: "libre-baskerville", label: "Libre Baskerville", cssVar: "--font-libre-baskerville" },
] as const;

export type ReaderTypeface = (typeof TYPEFACE_OPTIONS)[number]["value"];

const DEFAULT_FONT_SIZE = 18;
const FONT_SIZE_MIN = 14;
const FONT_SIZE_MAX = 28;
const FONT_SIZE_STEP = 1;

export function usePreferences() {
	const [isOpen, setIsOpen] = useState(false);
	const [typeface, setTypeface] = useState<ReaderTypeface>("arizona");
	const [fontSize, setFontSize] = useState(DEFAULT_FONT_SIZE);
	const [isSpeedReaderMode, setIsSpeedReaderMode] = useState(false);
	const [isLoaded, setIsLoaded] = useState(false);
	const hasInitializedSaveRef = useRef(false);

	useEffect(() => {
		let cancelled = false;

		(async () => {
			const prefs = await getPreferences();
			if (cancelled) return;
			if (prefs) {
				if (TYPEFACE_OPTIONS.some((o) => o.value === prefs.typeface)) {
					setTypeface(prefs.typeface as ReaderTypeface);
				}
				if (typeof prefs.fontSize === "number") {
					setFontSize(Math.min(FONT_SIZE_MAX, Math.max(FONT_SIZE_MIN, prefs.fontSize)));
				}
				if (typeof prefs.isSpeedReaderMode === "boolean") {
					setIsSpeedReaderMode(prefs.isSpeedReaderMode);
				}
			}
			setIsLoaded(true);
		})();

		return () => {
			cancelled = true;
		};
	}, []);

	useEffect(() => {
		if (!isLoaded) return;
		if (!hasInitializedSaveRef.current) {
			hasInitializedSaveRef.current = true;
			return;
		}
		const t = setTimeout(() => {
			putPreferences({ typeface, fontSize, isSpeedReaderMode });
		}, 500);
		return () => clearTimeout(t);
	}, [isLoaded, typeface, fontSize, isSpeedReaderMode]);

	const open = useCallback(() => setIsOpen(true), []);
	const close = useCallback(() => setIsOpen(false), []);

	const increaseFontSize = useCallback(() => {
		setFontSize((s) => Math.min(FONT_SIZE_MAX, s + FONT_SIZE_STEP));
	}, []);

	const decreaseFontSize = useCallback(() => {
		setFontSize((s) => Math.max(FONT_SIZE_MIN, s - FONT_SIZE_STEP));
	}, []);

	const toggleSpeedReaderMode = useCallback(() => {
		setIsSpeedReaderMode((v) => !v);
	}, []);

	return {
		isOpen,
		typeface,
		fontSize,
		isSpeedReaderMode,
		canIncrease: fontSize < FONT_SIZE_MAX,
		canDecrease: fontSize > FONT_SIZE_MIN,
		open,
		close,
		setTypeface,
		increaseFontSize,
		decreaseFontSize,
		toggleSpeedReaderMode,
	};
}

export type Preferences = ReturnType<typeof usePreferences>;
