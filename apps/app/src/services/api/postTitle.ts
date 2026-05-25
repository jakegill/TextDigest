import { auth } from "@/lib/firebase";

export async function postTitle(file: File) {
	try {
		await auth.authStateReady();
		const token = await auth.currentUser?.getIdToken();
		const fd = new FormData();
		fd.append("file", file);

		const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/titles`, {
			method: "POST",
			headers: { Authorization: `Bearer ${token}` },
			body: fd,
		});

		if (res.ok) {
			const data = await res.json();
			return data;
		}
	} catch (e) {
		console.error("[postTitle]: ", e);
	}
}
