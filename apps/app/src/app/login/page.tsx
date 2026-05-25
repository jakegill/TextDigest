"use client";

import { CheckIcon } from "@phosphor-icons/react/dist/csr/Check";
import { GoogleAuthProvider, onAuthStateChanged, signInWithPopup } from "firebase/auth";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { GoogleIcon } from "@/components/icons/google-icon";
import { Button } from "@/components/ui/button";
import { auth } from "@/lib/firebase";

const FEATURES = ["Higher Comprehension", "Read Faster", "Enjoy Reading", "Deeper Understanding"];

export default function LoginPage() {
	const router = useRouter();
	const [showCard, setShowCard] = useState(false);

	useEffect(() => {
		return onAuthStateChanged(auth, (u) => {
			if (u) {
				router.replace("/library");
			} else {
				setShowCard(true);
			}
		});
	}, [router]);

	return (
		<main className="relative min-h-screen typeface-arizona w-full px-4">
			<div className="pointer-events-none absolute inset-0 -z-10">
				<svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none" className="h-full w-full">
					<polygon points="0,100 100,0 100,100" className="fill-neutral-100" />
				</svg>
			</div>

			<div className="flex min-h-screen w-full flex-col items-center pt-24 lg:justify-center lg:py-0">
				<div className="flex flex-col gap-16 lg:flex-row lg:gap-36">
					<AuthCopy />
					{showCard ? <SignInCard /> : <SignInCardSkeleton />}
				</div>
			</div>
		</main>
	);
}

function AuthCopy() {
	return (
		<div className="w-96 max-w-full space-y-4 p-2 lg:space-y-8 lg:p-6">
			<div className="space-y-2">
				<h1 className="from-primary-400 to-primary-800 bg-linear-to-r bg-clip-text text-3xl font-bold text-transparent lg:text-4xl">
					TextDigest<span>.</span>
				</h1>
				<p className="text-neutral-700 typeface-diatype lg:text-lg">
					The <span className="font-semibold text-neutral-800">AI integrated, UI optimized</span> reading platform for
					your <span className="font-semibold text-neutral-800">textbooks</span>
				</p>
			</div>
			<ul className="hidden lg:flex typeface-diatype lg:flex-col lg:gap-1">
				{FEATURES.map((label) => (
					<li key={label} className="flex  items-center gap-2">
						<CheckIcon weight="bold" className="size-8 text-accent-teal-500" />
						<p className="text-xl text-neutral-700">{label}</p>
					</li>
				))}
			</ul>
		</div>
	);
}

function SignInCard() {
	return (
		<div className="w-96 max-w-full space-y-4 rounded-md border border-neutral-200 bg-neutral-100 p-4 shadow-lg lg:space-y-10 lg:p-6">
			<div className="space-y-2">
				<h1 className="from-primary-400 to-primary-800 bg-linear-to-r bg-clip-text text-3xl font-bold text-transparent lg:text-4xl">
					Sign in<span>.</span>
				</h1>
				<p className="text-lg text-neutral-600 typeface-diatype">Use your Google account to sign in.</p>
			</div>
			<Button
				size="lg"
				variant="secondary"
				onClick={() => signInWithPopup(auth, new GoogleAuthProvider())}
				className="w-full typeface-diatype transition-colors duration-300 hover:bg-neutral-50 bg-white border cursor-pointer border-neutral-200 py-4 text-base md:py-6 md:text-lg"
			>
				<GoogleIcon className="size-6" />
				Sign in with Google
			</Button>
		</div>
	);
}

function SignInCardSkeleton() {
	return (
		<div className="w-96 max-w-full space-y-4 rounded-md border border-neutral-200 bg-neutral-100 p-4 shadow-lg lg:space-y-10 lg:p-6">
			<div className="space-y-2">
				<div className="h-9 w-32 animate-pulse rounded bg-neutral-200 lg:h-10" />
				<div className="h-6 w-64 animate-pulse rounded bg-neutral-200" />
			</div>
			<div className="h-12 w-full animate-pulse rounded bg-neutral-200 md:h-14" />
		</div>
	);
}
