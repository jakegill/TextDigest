export function fuzzyIncludes(text: string, pattern: string, maxDist = 1): boolean {
	if (!pattern) return true;
	const t = text.toLowerCase();
	const p = pattern.toLowerCase();
	if (t.includes(p)) return true;
	const m = p.length;
	const n = t.length;
	if (m > n + maxDist) return false;
	let prev = new Array(n + 1).fill(0);
	for (let i = 1; i <= m; i++) {
		const curr = new Array(n + 1);
		curr[0] = i;
		for (let j = 1; j <= n; j++) {
			const cost = p[i - 1] === t[j - 1] ? 0 : 1;
			curr[j] = Math.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost);
		}
		prev = curr;
	}
	return Math.min(...prev) <= maxDist;
}
