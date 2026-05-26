import http from "node:http";
import { Readable } from "node:stream";

const BUCKET = process.env.BUCKET;
if (!BUCKET) throw new Error("BUCKET env var required");
const PORT = Number(process.env.PORT ?? 8080);

function candidates(p) {
	const t = p.replace(/^\/+/, "").replace(/\/+$/, "");
	if (t === "") return ["index.html"];
	if (/\.[a-z0-9]+$/i.test(t)) return [t];
	return [`${t}/index.html`, `${t}.html`, t];
}

const FORWARD_HEADERS = ["content-type", "cache-control", "etag", "last-modified"];

http.createServer(async (req, res) => {
	if (req.method !== "GET" && req.method !== "HEAD") {
		res.writeHead(405, { Allow: "GET, HEAD" });
		res.end();
		return;
	}

	const pathname = new URL(req.url ?? "/", "http://x").pathname;

	for (const name of candidates(pathname)) {
		const upstream = await fetch(
			`https://storage.googleapis.com/${BUCKET}/${encodeURI(name)}`,
			{ method: req.method },
		);
		if (upstream.status !== 200) continue;
		for (const h of FORWARD_HEADERS) {
			const v = upstream.headers.get(h);
			if (v) res.setHeader(h, v);
		}
		res.writeHead(200);
		if (upstream.body) Readable.fromWeb(upstream.body).pipe(res);
		else res.end();
		return;
	}

	res.writeHead(404, { "content-type": "text/plain" });
	res.end("Not Found");
}).listen(PORT, () => {
	console.log(`web-router listening on ${PORT}, bucket=${BUCKET}`);
});
