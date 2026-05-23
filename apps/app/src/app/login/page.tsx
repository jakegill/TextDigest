"use client";

import { GoogleAuthProvider, onAuthStateChanged, signInWithPopup, signOut, type User } from "firebase/auth";

import { useEffect, useState } from "react";

import { auth } from "@/lib/firebase";

export default function LoginPage() {
	const [user, setUser] = useState<User | null>(null);
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		return onAuthStateChanged(auth, (u) => {
			setUser(u);
			setLoading(false);
		});
	}, []);

	if (loading) return <main>loading…</main>;

	if (user) {
		return (
			<main>
				<p>signed in as {user.displayName ?? user.email}</p>
				<button onClick={() => signOut(auth)}>sign out</button>
			</main>
		);
	}

	return (
		<main>
			<button onClick={() => signInWithPopup(auth, new GoogleAuthProvider())}>sign in with google</button>
		</main>
	);
}
