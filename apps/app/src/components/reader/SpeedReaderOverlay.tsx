export function SpeedReaderOverlay() {
	return (
		<div aria-hidden className="pointer-events-none absolute inset-0 z-40 px-4 md:px-32 lg:px-48 xl:px-96 2xl:px-[33svw]">
			<div className="relative h-full">
				<div className="absolute inset-y-0 left-1/3 w-px bg-neutral-900/20" />
				<div className="absolute inset-y-0 left-2/3 w-px bg-neutral-900/20" />
			</div>
		</div>
	);
}
