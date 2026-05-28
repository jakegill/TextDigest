import { auth } from "@/lib/firebase";

export async function postTitle(file: File) {
	try {
		await auth.authStateReady();
		const token = await auth.currentUser?.getIdToken();
		const apiUrl = process.env.NEXT_PUBLIC_API_URL;

		const presign = await fetch(`${apiUrl}/titles/upload-url`, {
			method: "POST",
			headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
			body: JSON.stringify({ filename: file.name, contentType: "application/pdf" }),
		});
		if (!presign.ok) return;
		const { taskId, sourceKey, uploadUrl } = await presign.json();

		const put = await fetch(uploadUrl, {
			method: "PUT",
			headers: { "Content-Type": "application/pdf" },
			body: file,
		});
		if (!put.ok) return;

		const start = await fetch(`${apiUrl}/titles`, {
			method: "POST",
			headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
			body: JSON.stringify({ taskId, sourceKey, filename: file.name }),
		});
		if (!start.ok) return;
		return await start.json();
	} catch (e) {
		console.error("[postTitle]: ", e);
	}
}
