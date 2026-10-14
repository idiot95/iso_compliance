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

	// A close-up of one region of a page, in a fixed-height pane: − / + zoom,
	// drag to move, "Page" for the whole sheet. `page` is a canvas holding the
	// whole page sharply; boxes are {x,y,w,h} in % of the page, `focus` is drawn
	// strong and centred, the rest faint. Returns {show(focus, boxes)}.
	function closeup(host, page, labels = {}) {
		const $h = $(host).html(`<div class="qi-dp"><canvas></canvas>
			<div class="qi-dp-tools">
				<button type="button" data-z="1.5" aria-label="${__("Zoom out")}">−</button>
				<button type="button" data-z="0.667" aria-label="${__("Zoom in")}">+</button>
				<button type="button" data-fit="1">${labels.page || __("Page")}</button>
			</div></div>`);
		const canvas = $h.find("canvas")[0];
		const aspect = page.height / page.width;
		let view = null;
		let focus = null;
		let boxes = [];
		const ratio = () => canvas.clientWidth / Math.max(1, canvas.clientHeight);
		const whole = () => Math.max(1, aspect * ratio());
		const fit = () => {
			if (!focus || !focus.w) return { cx: 0.5, cy: 0.5, span: whole() };
			return {
				cx: (focus.x + focus.w / 2) / 100,
				cy: (focus.y + focus.h / 2) / 100,
				span: Math.min(whole(), Math.max(0.12, (focus.w / 100) * 3, (focus.h / 100) * aspect * ratio() * 2.5)),
			};
		};
		const draw = () => {
			const W = canvas.clientWidth;
			const H = canvas.clientHeight;
			if (!W || !H) return; // not laid out yet: the observer calls again
			if (!view) view = fit();
			const dpr = window.devicePixelRatio || 1;
			canvas.width = Math.round(W * dpr);
			canvas.height = Math.round(H * dpr);
			const ctx = canvas.getContext("2d");
			ctx.fillStyle = "#e9e9e9";
			ctx.fillRect(0, 0, canvas.width, canvas.height);
			const scale = canvas.width / (view.span * page.width); // canvas px per page px
			const sx = view.cx * page.width - canvas.width / scale / 2;
			const sy = view.cy * page.height - canvas.height / scale / 2;
			ctx.drawImage(page, -sx * scale, -sy * scale, page.width * scale, page.height * scale);
			const rect = (p, color, width) => {
				ctx.strokeStyle = color;
				ctx.lineWidth = width * dpr;
				ctx.strokeRect(((p.x / 100) * page.width - sx) * scale, ((p.y / 100) * page.height - sy) * scale,
					(p.w / 100) * page.width * scale, (p.h / 100) * page.height * scale);
			};
			boxes.forEach((p) => p !== focus && rect(p, p.color || "rgba(45,149,240,.6)", 1));
			if (focus && focus.w) rect(focus, focus.color || "#e8590c", 2.5);
		};
		new ResizeObserver(draw).observe(canvas);
		$h.find("[data-z]").on("click", (e) => {
			if (!view) return;
			view.span = Math.min(whole(), Math.max(0.05, view.span * Number($(e.currentTarget).data("z"))));
			draw();
		});
		$h.find("[data-fit]").on("click", () => {
			view = view && view.span >= whole() - 1e-6 ? fit() : { cx: 0.5, cy: 0.5, span: whole() };
			draw();
		});
		let drag = null;
		$(canvas)
			.on("pointerdown", (e) => {
				drag = { x: e.clientX, y: e.clientY, cx: view && view.cx, cy: view && view.cy };
				canvas.setPointerCapture(e.pointerId);
			})
			.on("pointermove", (e) => {
				if (!drag || !view) return;
				const per = (view.span * page.width) / canvas.clientWidth; // page px per screen px
				view.cx = drag.cx - ((e.clientX - drag.x) * per) / page.width;
				view.cy = drag.cy - ((e.clientY - drag.y) * per) / page.height;
				draw();
			})
			.on("pointerup pointercancel", () => (drag = null));
		return {
			show(f, all) {
				focus = f || null;
				boxes = all || [];
				view = null;
				draw();
			},
		};
	}

	// Drawings listed on the left, the clicked one shown on the right, so a
	// drawing is seen before it is chosen. files: drawing_options() rows.
	// Returns {chosen()}; onpick(file) runs on each click.
	function chooser(host, files, { current, onpick } = {}) {
		const esc = frappe.utils.escape_html;
		const $h = $(host).html(`<div class="qi-pick"><div class="qi-pick-list">${files
			.map(
				(f) => `<button type="button" class="qi-pick-row" data-file="${esc(f.name)}">
					<b>${esc(f.file_name)}</b>
					<span class="text-muted small">${esc(f.attached_to_doctype)} ${esc(f.attached_to_name)}${f.bom_default ? " · " + __("default") : ""}${
						f.attached_to_doctype === "BOM" && !f.bom_active ? " · " + __("inactive") : ""
					}${f.name === current ? " · " + __("in use") : ""}</span></button>`
			)
			.join("")}</div>
			<div class="qi-pick-view"><div class="text-muted small qi-pick-msg">${__("Click a drawing to look at it.")}</div></div></div>`);
		let chosen = null;
		let drawing = null;
		const view = async (name) => {
			chosen = name;
			$h.find(".qi-pick-row").each((_, el) => $(el).toggleClass("on", String($(el).data("file")) === name));
			const f = files.find((x) => x.name === name);
			onpick && onpick(f);
			const $v = $h.find(".qi-pick-view").html(`<div class="text-muted small qi-pick-msg">${__("Opening…")}</div>`);
			try {
				if (drawing) drawing.close();
				drawing = await open(f.file_url);
				if (chosen !== name) return;
				let page = 1;
				const show = async () => {
					$v.html(`<div class="qi-pick-bar small">${
						drawing.pages > 1
							? `<button type="button" class="btn btn-xs btn-default" data-p="-1">‹</button> ${__("Sheet {0} of {1}", [page, drawing.pages])}
								<button type="button" class="btn btn-xs btn-default" data-p="1">›</button>`
							: ""
					}<a href="${esc(f.file_url)}" target="_blank" rel="noopener">${__("Open full size")}</a></div><canvas></canvas>`);
					$v.find("[data-p]").on("click", (e) => {
						page = Math.min(drawing.pages, Math.max(1, page + Number($(e.currentTarget).data("p"))));
						show();
					});
					await drawing.render(page, $v.find("canvas")[0], $v.width() - 2);
				};
				await show();
			} catch (e) {
				$v.html(`<div class="text-danger small">${__("Could not show the drawing here")}: ${esc(e.message)}</div>`);
			}
		};
		$h.find(".qi-pick-row").on("click", (e) => view(String($(e.currentTarget).data("file"))));
		const first = files.find((f) => f.name === current) || files[0];
		// the dialog may still be opening: wait for a width before drawing
		if (first) setTimeout(() => view(first.name), 250);
		return { chosen: () => chosen, close: () => drawing && drawing.close() };
	}

	frappe.dom.set_style(`
.qi-pick{display:grid;grid-template-columns:minmax(200px,1fr) 2.2fr;gap:12px;min-height:360px}
.qi-pick-list{display:flex;flex-direction:column;gap:6px;max-height:62vh;overflow:auto}
.qi-pick-row{text-align:left;border:1px solid var(--border-color);background:var(--fg-color);border-radius:8px;padding:8px 10px;display:flex;flex-direction:column;gap:2px}
.qi-pick-row.on{border-color:var(--primary);box-shadow:0 0 0 1px var(--primary);background:var(--blue-50)}
.qi-pick-view{border:1px solid var(--border-color);border-radius:8px;padding:6px;max-height:62vh;overflow:auto;background:var(--gray-50)}
.qi-pick-view canvas{display:block;margin:0 auto}
.qi-pick-bar{display:flex;gap:8px;align-items:center;margin-bottom:6px}
.qi-pick-msg{padding:20px;text-align:center}
@media (max-width:768px){.qi-pick{grid-template-columns:1fr}}
`);

	return { load, open, page_images, is_pdf, closeup, chooser };
})();
