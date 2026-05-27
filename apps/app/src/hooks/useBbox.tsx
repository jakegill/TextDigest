export type Bbox = [number, number, number, number];

const PAGE_NORM = 1000;
const CENTER_TOL = 80;

export const DEFAULT_BBOX: Bbox = [0, 0, PAGE_NORM, PAGE_NORM];

export const unionBbox = (boxes: Bbox[]): Bbox => [
	Math.min(...boxes.map((b) => b[0])),
	Math.min(...boxes.map((b) => b[1])),
	Math.max(...boxes.map((b) => b[2])),
	Math.max(...boxes.map((b) => b[3])),
];

export const isCentered = (b: Bbox): boolean => {
	const mid = (b[0] + b[2]) / 2;
	return Math.abs(mid - PAGE_NORM / 2) < CENTER_TOL;
};
