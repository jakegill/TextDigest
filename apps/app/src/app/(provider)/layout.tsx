"use client";

import { onIdTokenChanged } from "firebase/auth";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { auth } from "@/lib/firebase";

export default function Layout({ children }: { children: React.ReactNode }) {
	const router = useRouter();

	useEffect(() => {
		return onIdTokenChanged(auth, (user) => {
			console.log(user);

			if (!user) {
				router.replace("/login");
			}
		});
	}, [router]);

	return <>{children}</>;
}
