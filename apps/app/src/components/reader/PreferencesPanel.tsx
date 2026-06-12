"use client";
import { CheckIcon, MinusIcon, PlusIcon, XIcon } from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";
import { TYPEFACE_OPTIONS, type Preferences } from "@/hooks/usePreferences";

export function PreferencesPanel({
	preferences,
	onClose,
}: {
	preferences: Preferences;
	onClose: () => void;
}) {
	return (
		<div className="flex h-full w-full flex-col">
			<header className="flex shrink-0 h-16 items-center justify-between border-b border-neutral-200 px-4 py-3">
				<span className="font-medium typeface-diatype text-neutral-900">Preferences</span>
				<Button variant="ghost" onClick={onClose} aria-label="Close">
					<XIcon className="size-6" />
				</Button>
			</header>

			<main className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-4 py-4">
				<section className="flex flex-col gap-2">
					<span className="text-xs uppercase typeface-diatype text-neutral-500">Typeface</span>
					<div className="flex flex-col">
						{TYPEFACE_OPTIONS.map((o) => (
							<button
								key={o.value}
								onClick={() => preferences.setTypeface(o.value)}
								className={`flex cursor-pointer w-full items-center justify-between rounded-md px-4 py-2 text-left transition-colors hover:bg-neutral-100 ${
									preferences.typeface === o.value ? "bg-neutral-100" : ""
								}`}
							>
								<span
									className="text-base text-neutral-900"
									style={{ fontFamily: `var(${o.cssVar}), serif` }}
								>
									{o.label}
								</span>
								{preferences.typeface === o.value && <CheckIcon className="size-4 text-neutral-900" />}
							</button>
						))}
					</div>
				</section>

				<section className="flex items-center justify-between">
					<span className="text-xs uppercase typeface-diatype text-neutral-500">Font size</span>
					<div className="flex items-center gap-2">
						<Button
							variant="ghost"
							onClick={preferences.decreaseFontSize}
							disabled={!preferences.canDecrease}
							aria-label="Decrease font size"
						>
							<MinusIcon className="size-4" />
						</Button>
						<span className="w-8 text-center text-sm typeface-diatype text-neutral-900 tabular-nums">
							{preferences.fontSize}
						</span>
						<Button
							variant="ghost"
							onClick={preferences.increaseFontSize}
							disabled={!preferences.canIncrease}
							aria-label="Increase font size"
						>
							<PlusIcon className="size-4" />
						</Button>
					</div>
				</section>

				<section className="flex items-center justify-between">
					<span className="text-xs uppercase typeface-diatype text-neutral-500">Speed reader</span>
					<button
						role="switch"
						aria-checked={preferences.isSpeedReaderMode}
						onClick={preferences.toggleSpeedReaderMode}
						className={`relative h-6 w-11 cursor-pointer rounded-full transition-colors ${
							preferences.isSpeedReaderMode ? "bg-neutral-900" : "bg-neutral-300"
						}`}
					>
						<span
							className={`absolute top-0.5 left-0.5 size-5 rounded-full bg-neutral-50 transition-transform ${
								preferences.isSpeedReaderMode ? "translate-x-5" : ""
							}`}
						/>
					</button>
				</section>
			</main>
		</div>
	);
}
