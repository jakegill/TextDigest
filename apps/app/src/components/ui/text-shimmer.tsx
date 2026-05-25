import { cn } from "@/lib/utils";

export function TextShimmer({
	children,
	className,
}: {
	children: React.ReactNode;
	className?: string;
}) {
	return (
		<span
			className={cn(
				"relative inline-block bg-clip-text text-transparent",
				"bg-[length:250%_100%]",
				"[--base-color:hsl(40,8%,55%)] [--base-gradient-color:hsl(37,11%,28%)]",
				"[background-image:linear-gradient(90deg,transparent_calc(50%-40px),var(--base-gradient-color),transparent_calc(50%+40px)),linear-gradient(var(--base-color),var(--base-color))]",
				"animate-[shimmer_2s_linear_infinite]",
				className,
			)}
		>
			{children}
		</span>
	);
}
