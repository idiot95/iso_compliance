// Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
// For license information, please see license.txt

// Drawing renderer shared by the template builder and the inspector screen.
// pdf.js (vendored legacy build, public/js/lib/pdfjs) is loaded on first use
// only, with dynamic import(); image drawings (png/jpg) need no library.

window.iso_qi_pdf = (() => {
	const BASE = "/assets/iso_compliance/js/lib/pdfjs/";
	let lib = null;

	async function load() {
		if (!lib) {
			lib = import(BASE + "pdf.min.js").then((m) => {
				const pdfjs = m.GlobalWorkerOptions ? m : window.pdfjsLib;
				pdfjs.GlobalWorkerOptions.workerSrc = BASE + "pdf.worker.min.js";
				return pdfjs;
			});
		}
		return lib;
	}

	const is_pdf = (url) => /\.pdf(\?|$)/i.test(url || "");

	// The render running on each canvas, whichever drawing started it.
	const canvas_tasks = new WeakMap();
	const canvas_latest = new WeakMap();

	// Open a drawing: returns {pages, render(pageNo, canvas, width) -> {w,h}, close()}.
	async function open(url) {
		if (!is_pdf(url)) {
			const img = await new Promise((resolve, reject) => {
				const i = new Image();
				i.onload = () => resolve(i);
				i.onerror = () => reject(new Error(__("Could not load the drawing image")));
				i.src = url;
			});
			return {
				pages: 1,
				async render(_page, canvas, width) {
					if (!(width > 0)) width = img.naturalWidth;
					const scale = width / img.naturalWidth;
					canvas.width = Math.round(img.naturalWidth * scale);
					canvas.height = Math.round(img.naturalHeight * scale);
					canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
					return { w: canvas.width, h: canvas.height };
				},
				close() {},
			};
		}
		const pdfjs = await load();
		const doc = await pdfjs.getDocument({ url, withCredentials: true }).promise;
		return {
			pages: doc.numPages,
			async render(pageNo, canvas, width) {
				// the newest call on a canvas wins; older ones step aside
				const token = {};
				canvas_latest.set(canvas, token);
				const page = await doc.getPage(pageNo);
				const base = page.getViewport({ scale: 1 });
				if (!(width > 0)) width = base.width; // hidden or not laid out yet
				const dpr = Math.min(window.devicePixelRatio || 1, 2);
				const vp = page.getViewport({ scale: (width / base.width) * dpr });
				// pdf.js frees a canvas only once a cancelled render has settled
				let running;
				while ((running = canvas_tasks.get(canvas))) {
					running.cancel();
					await running.promise.catch(() => {});
					if (canvas_tasks.get(canvas) === running) canvas_tasks.delete(canvas);
				}
				if (canvas_latest.get(canvas) !== token) return null;
				canvas.width = Math.round(vp.width);
				canvas.height = Math.round(vp.height);
				canvas.style.width = Math.round(vp.width / dpr) + "px";
				canvas.style.height = Math.round(vp.height / dpr) + "px";
				const task = page.render({ canvasContext: canvas.getContext("2d"), viewport: vp });
				canvas_tasks.set(canvas, task);
				try {
					await task.promise;
				} catch (e) {
					if (e && e.name === "RenderingCancelledException") return null;
					throw e;
				} finally {
					if (canvas_tasks.get(canvas) === task) canvas_tasks.delete(canvas);
				}
				return { w: vp.width / dpr, h: vp.height / dpr };
			},
			close() {
				doc.destroy();
			},
		};
	}

	// Every page as a JPEG data URL, for prints (wkhtmltopdf cannot run pdf.js).
	// JPEG, not PNG: customer drawings are often scans, and a scanned A3 page
	// is ~7 MB as PNG against well under 1 MB as JPEG.
	async function page_images(url, width = 1600) {
		const drawing = await open(url);
		const out = [];
		for (let p = 1; p <= drawing.pages; p++) {
			const c = document.createElement("canvas");
			await drawing.render(p, c, width);
			out.push(c.toDataURL("image/jpeg", 0.85));
		}
		drawing.close();
		return out;
	}

	return { load, open, page_images, is_pdf };
})();
