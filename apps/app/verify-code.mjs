import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import remarkRehype from "remark-rehype";
import rehypeRaw from "rehype-raw";
import katex from "katex";

const body =
  '<div class="mineru-algorithm" style="white-space: pre-wrap; font-family:monospace;">\n$\\ell =$ replenishment lead time (in days), assumed constant  \n$X =$ demand during replenishment lead time (in units)  \n</div>';

const lpBody =
  '<div class="mineru-algorithm" style="white-space: pre-wrap; font-family:monospace;">\nMAX      15 P1 + 8 P2 - 6 OT\nSUBJECT TO\n    2)   P1 - 10 A1 &lt;=   50\n    5)   2 P1 + P2 - RM &lt;=   0\nEND\n</div>';

// Option A: emit MinerU's raw HTML verbatim
async function renderA(md) {
  const processor = unified()
    .use(remarkParse)
    .use(remarkGfm)
    .use(remarkMath)
    .use(remarkRehype, { allowDangerousHtml: true })
    .use(rehypeRaw)
    .use(rehypeKatex);
  const tree = await processor.run(processor.parse(md));
  const found = { katex: 0, divs: 0, rawText: [] };
  (function walk(n) {
    if (n.type === "element" && n.tagName === "div") found.divs++;
    if (n.type === "element" && typeof n.properties?.className === "string") found.divs++;
    if (n.type === "element" && n.children) {
      for (const c of n.children) {
        if (c.type === "text") found.rawText.push(c.value);
      }
    }
    n.children?.forEach(walk);
  })(tree);
  return { ...found, tree };
}

// Option B: strip to text, emit fenced code block
function htmlToText(html) {
  return html
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(div|p|li|tr)>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

async function renderB(rawHtml, lang = "") {
  const text = htmlToText(rawHtml);
  const fence = text.includes("```") ? "````" : "```";
  const md = `${fence}${lang}\n${text}\n${fence}`;
  const processor = unified()
    .use(remarkParse)
    .use(remarkGfm)
    .use(remarkMath)
    .use(remarkRehype, { allowDangerousHtml: true })
    .use(rehypeRaw)
    .use(rehypeKatex);
  const tree = await processor.run(processor.parse(md));
  let codeText = null;
  (function walk(n) {
    if (n.type === "element" && n.tagName === "code") {
      codeText = (n.children || []).map((c) => c.value ?? "").join("");
    }
    n.children?.forEach(walk);
  })(tree);
  return { codeText, md };
}

console.log("### Option A — emit MinerU raw HTML (does the $math$ render?)");
const a = await renderA(body);
console.log("  div elements found:", a.divs);
console.log("  first text inside div:", JSON.stringify(a.rawText[0]?.slice(0, 60)));
const hasDollar = a.rawText.some((t) => t.includes("$\\ell"));
console.log("  => literal '$\\ell =$' left unrendered:", hasDollar);
console.log();

console.log("### Option B — strip HTML, emit fenced code block");
for (const [name, raw] of [["variable defs", body], ["LP formulation", lpBody]]) {
  const b = await renderB(raw);
  console.log(`  [${name}] code text:`);
  console.log("   ", JSON.stringify(b.codeText));
  console.log();
}
