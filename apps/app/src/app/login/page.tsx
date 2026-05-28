"use client";

import { GoogleAuthProvider, onAuthStateChanged, signInWithPopup } from "firebase/auth";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { GoogleIcon } from "@/components/icons/google-icon";
import { Button } from "@/components/ui/button";
import { auth } from "@/lib/firebase";

export default function LoginPage() {
	const router = useRouter();

	useEffect(() => {
		return onAuthStateChanged(auth, (u) => {
			if (u) router.replace("/library");
		});
	}, [router]);

	return (
		<main className="bg-linear-to-t from-neutral-200 to-neutral-50 to-40% flex h-[100svh] w-full flex-col items-center justify-center gap-8 px-6">
			<div className="space-y-6">
				<h1 className="typeface-arizona text-3xl font-semibold italic text-neutral-800 lg:text-5xl">Text Digest</h1>
				<p className="typeface-arizona lg:max-w-96 max-w-full text-lg italic text-neutral-700">
					&ldquo;We have a hunger of the mind which asks for knowledge of all around us, and the more we gain, the
					more is our desire.&rdquo;
					<br />— Maria Mitchell
				</p>
				<Button
					size="lg"
					variant="secondary"
					onClick={() => signInWithPopup(auth, new GoogleAuthProvider())}
					className="typeface-diatype cursor-pointer border border-neutral-200 bg-white py-4 px-4 text-base transition-colors duration-300 hover:bg-neutral-50 md:py-6 md:text-lg"
				>
					<GoogleIcon className="size-7" />
					<span className="text-xl typeface-arizona">Log in</span>
				</Button>
			</div>
		</main>
	);
}
