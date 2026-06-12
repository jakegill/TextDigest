import { Bitter, EB_Garamond, Inter, Jost, Libre_Baskerville, Literata } from "next/font/google";

const literata = Literata({ subsets: ["latin"], variable: "--font-literata", display: "swap", preload: false });
const bitter = Bitter({ subsets: ["latin"], variable: "--font-bitter", display: "swap", preload: false });
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap", preload: false });
const jost = Jost({ subsets: ["latin"], variable: "--font-jost", display: "swap", preload: false });
const ebGaramond = EB_Garamond({ subsets: ["latin"], variable: "--font-eb-garamond", display: "swap", preload: false });
const libreBaskerville = Libre_Baskerville({
	weight: ["400", "700"],
	subsets: ["latin"],
	variable: "--font-libre-baskerville",
	display: "swap",
	preload: false,
});

export const readerFontVariables = [literata, bitter, inter, jost, ebGaramond, libreBaskerville]
	.map((f) => f.variable)
	.join(" ");
