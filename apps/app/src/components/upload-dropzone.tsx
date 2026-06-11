"use client";

import { CircleNotchIcon } from "@phosphor-icons/react/dist/csr/CircleNotch";
import { useState } from "react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { postTitle } from "@/services/api/postTitle";
import { subscribeToTitleProgress, type TitleProgressEvent } from "@/services/api/titleEvents";

export type UploadedTitle = {
	titleId: string;
	title: string;
	author: string;
	coverUrl: string;
	isProcessing: boolean;
	processingError?: string | null;
};

export function UploadDropzone({
	children,
	onUploaded,
	onProgress,
}: {
	children: React.ReactElement;
	onUploaded?: (title: UploadedTitle) => void;
	onProgress?: (e: TitleProgressEvent) => void;
}) {
	const [open, setOpen] = useState(false);
	const [isLoading, setIsLoading] = useState(false);
	const [statusText, setStatusText] = useState("Uploading…");

	const { getRootProps, getInputProps, isDragActive } = useDropzone({
		accept: { "application/pdf": [".pdf"] },
		multiple: false,
		disabled: isLoading,
		onDrop: async (files) => {
			const file = files[0];
			if (!file) return;
			setIsLoading(true);
			setStatusText("Uploading…");

			const res = await postTitle(file);
			if (!res?.taskId) {
				setIsLoading(false);
				toast.error("Upload failed", {
					description: "Something went wrong uploading the PDF. Please try again.",
				});
				return;
			}

			const ac = new AbortController();
			let cardSurfaced = false;

			subscribeToTitleProgress(
				res.taskId,
				(e) => {
					onProgress?.(e);
					setStatusText(stageLabel(e));

					// Surface the new title to the parent as soon as we have
					// enough to render a card (titleId + title + author + cover),
					// then close the modal. SSE stream keeps running so the
					// parent can flip the processing badge on stage=done.
					if (!cardSurfaced && e.titleId && e.title && e.author && e.coverUrl) {
						cardSurfaced = true;
						onUploaded?.({
							titleId: e.titleId,
							title: e.title,
							author: e.author,
							coverUrl: e.coverUrl,
							isProcessing: e.stage !== "done" && e.stage !== "failed",
							processingError: e.stage === "failed" ? e.error : null,
						});
						setOpen(false);
						setIsLoading(false);
						toast.success("Upload successful", {
							description: `${e.title} is now processing.`,
						});
					}

					if (e.stage === "done") {
						toast.success("Processing complete", {
							description: `${e.title ?? "Your title"} is ready to read.`,
						});
						ac.abort();
					} else if (e.stage === "failed") {
						setIsLoading(false);
						toast.error("Processing failed", {
							description: e.error ?? "Something went wrong processing the PDF.",
						});
						ac.abort();
					}
				},
				ac.signal,
			).catch((err) => {
				// AbortError fires when we close the stream ourselves; ignore.
				if (err?.name !== "AbortError") {
					console.error("[upload-dropzone] sse failed", err);
				}
			});
		},
	});

	return (
		<Dialog open={open} onOpenChange={setOpen}>
			<DialogTrigger render={children} />
			<DialogContent className="sm:max-w-lg rounded-none">
				<DialogHeader>
					<DialogTitle className="text-2xl text-neutral-700 font-medium typeface-arizona">Upload a Title</DialogTitle>
					<DialogDescription className="text-base text-neutral-600 typeface-diatype">
						Convert any PDF into an ebook
					</DialogDescription>
				</DialogHeader>
				<div
					{...getRootProps()}
					className={cn(
						"flex h-64 typeface-diatype rounded-none bg-white cursor-pointer flex-col items-center justify-center gap-3 border-2 border-dashed border-neutral-200 hover:bg-neutral-100 text-neutral-700 transition-colors",
						isDragActive && "border-primary-400 bg-primary-50",
						isLoading && "cursor-not-allowed opacity-60",
					)}
				>
					<input {...getInputProps()} />
					{isLoading ? (
						<>
							<CircleNotchIcon className="size-8 animate-spin" />
							<p className="text-sm">{statusText}</p>
						</>
					) : (
						<>
							<p className="text-base">Click to Upload</p>
							<p className="text-xs text-neutral-500">— or —</p>
							<p className="text-base">Drag and Drop</p>
						</>
					)}
				</div>
			</DialogContent>
		</Dialog>
	);
}

function stageLabel(e: TitleProgressEvent): string {
	switch (e.stage) {
		case "queued":
			return "Queued…";
		case "cover":
			return "Rendering cover…";
		case "metadata":
			return "Reading cover…";
		case "parsing":
			return "Parsing…";
		case "vectorizing":
			return "Vectorizing…";
		case "toc":
			return "Extracting TOC…";
		case "writing":
			return "Finalizing…";
		case "done":
			return "Done";
		case "failed":
			return e.error ?? "Failed";
	}
}
