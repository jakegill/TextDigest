import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

import { readerFontVariables } from "@/lib/fonts";

const arizona = localFont({
	src: "../../public/typefaces/ABC Arizona/ABC Arizona Superfamily Variable/ABCArizonaSuperfamilyVariable-Trial.woff",
	variable: "--font-arizona",
	weight: "100 900",
	display: "swap",
});

const diatype = localFont({
	src: "../../public/typefaces/ABC Diatype/ABC Diatype Variable/ABCDiatypeVariable-Trial.woff2",
	variable: "--font-diatype",
	weight: "100 900",
	display: "swap",
});

export const metadata: Metadata = {
	title: "Text Digest",
	description: "",
};

export default function RootLayout({
	children,
}: Readonly<{
	children: React.ReactNode;
}>) {
	return (
		<html lang="en" className={`${arizona.variable} ${diatype.variable} ${readerFontVariables} h-full antialiased`}>
			<body className="min-h-full flex flex-col">{children}</body>
		</html>
	);
}
