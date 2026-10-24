// Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
// For license information, please see license.txt

// Drawing-based inspection template builder (SPEC §4.6).
// Pick the drawing from the item's BOMs, draw a box round each dimension,
// say what is printed there; the server turns it into limits. Legacy
// templates (no drawing rows, no item) look exactly as before.

const QI = "iso_compliance.qi.template";
const QI_API = "iso_compliance.qi.api";
const QI_ROWS = "item_quality_inspection_parameter";
const QI_STAGES = [
	["custom_stage_incoming", __("Incoming")],
	["custom_stage_in_process", __("In process")],
	["custom_stage_final", __("Final")],
	["custom_stage_fai", __("FAI")],
	["custom_stage_type_test", __("Type test")],
];

frappe.ui.form.on("Quality Inspection Template", {
	setup(frm) {
		frm.set_query("custom_product_wi", () => ({ filters: { name: ["like", "%WI-%"] } }));
		frm.set_query("custom_bom", () => ({ filters: { item: frm.doc.custom_item || "", docstatus: 1 } }));
	},

	onload(frm) {
		// Arrived with the item already set (readiness report, BOM or Item button).
		if (frm.is_new() && frm.doc.custom_item && !frm.doc.quality_inspection_template_name) frm.trigger("custom_item");
	},

	refresh(frm) {
		qi_form_layout(frm);
		const builder = qi_builder(frm);
		builder.render();
		qi_drawing_options(frm);
		qi_tag_prompt(frm);
		if (frm.is_new() || !qi_can_edit()) return;
		if (frm.doc.custom_item || qi_is_drawing(frm)) {
			frm.add_custom_button(__("Tag Items / BOMs"), () => qi_tag_dialog(frm));
			frm.add_custom_button(__("New Revision"), () => qi_new_revision(frm));
			frm.add_custom_button(__("Duplicate"), () => qi_duplicate(frm));
		}
	},

	// Item → BOM → drawing: each choice narrows the next.
	custom_bom(frm) {
		frm.set_value("custom_drawing_file", "");
		qi_drawing_options(frm, true);
	},

	custom_drawing_file(frm) {
		const file = frm.doc.custom_drawing_file;
		if (!file || frm.__qi_setting_file) return;
		const f = (frm.__qi_drawings || []).find((x) => x.name === file);
		const g = qi_guess_drawing(f && f.file_name);
		const fill = {};
		// picked from all the item's BOMs: the BOM is the one it hangs on (set directly,
		// so the BOM handler doesn't clear the choice just made)
		if (!frm.doc.custom_bom && f && f.attached_to_doctype === "BOM") {
			frm.doc.custom_bom = f.attached_to_name;
			frm.refresh_field("custom_bom");
		}
		if (!frm.doc.custom_drawing_no && g.no) fill.custom_drawing_no = g.no;
		if (!frm.doc.custom_drawing_revision && g.rev) fill.custom_drawing_revision = g.rev;
		// the save links the drawing (server side), so the form never holds a stale one
		frm.set_value(fill).then(async () => {
			if (!frm.doc.quality_inspection_template_name) {
				const { message } = await frappe.db.get_value("Item", frm.doc.custom_item, "item_name");
				frm.doc.quality_inspection_template_name = qi_suggest_name(frm, message && message.item_name);
			}
			await frm.save();
		});
	},

	custom_item(frm) {
		if (frm.doc.custom_bom) frm.set_value("custom_bom", "");
		if (frm.doc.custom_item) {
			// one active default BOM is the usual case: take it
			frappe.db.get_list("BOM", { filters: { item: frm.doc.custom_item, docstatus: 1, is_active: 1 }, fields: ["name", "is_default"], limit: 20 })
				.then((boms) => {
					const pick = boms.find((b) => b.is_default) || (boms.length === 1 ? boms[0] : null);
					if (pick && !frm.doc.custom_bom) frm.set_value("custom_bom", pick.name);
				});
		}
		if (frm.doc.custom_item && !frm.doc.quality_inspection_template_name) {
			frappe.db.get_value("Item", frm.doc.custom_item, "item_name").then(({ message }) => {
				frm.set_value("quality_inspection_template_name", qi_suggest_name(frm, message && message.item_name));
			});
		}
		qi_drawing_options(frm); // every BOM's drawings until a BOM narrows them
		qi_builder(frm).render();
	},
	custom_drawing_no: (frm) => qi_rename_hint(frm),
	custom_drawing_revision: (frm) => qi_rename_hint(frm),
});

// Only the new format shows. The builder under the drawing holds the rows, the
// lock, the supersession and "Used by", so the raw fields behind it stay out of
// sight. A template from before drawings (no item, no drawing rows) is
// archived: read only, still used by its items until a new-format one replaces it.
const QIT_BEHIND_BUILDER = [QI_ROWS, "custom_rows_section", "custom_drawing", "custom_locked", "custom_superseded_by", "custom_used_by"];

function qi_is_legacy(frm) {
	return !frm.is_new() && !frm.doc.custom_item && (frm.doc[QI_ROWS] || []).length > 0 && !qi_is_drawing(frm);
}

function qi_form_layout(frm) {
	QIT_BEHIND_BUILDER.forEach((f) => frm.set_df_property(f, "hidden", 1));
	// sub-headings inside the "Item and drawing" section
	[["custom_item", __("Item")], ["custom_drawing_no", __("Drawing")], ["custom_general_tolerance", __("General tolerances (title block)")]].forEach(([f, label]) => {
		const $f = frm.fields_dict[f] && $(frm.fields_dict[f].wrapper);
		if ($f && !$f.prev(".qi-col-head").length) $f.before(`<div class="qi-col-head">${label}</div>`);
	});
	// the fields say what they are; the header and the pickers say the rest
	["custom_item", "custom_bom", "custom_general_tolerance"].forEach((f) => frm.set_df_property(f, "description", ""));
	const legacy = qi_is_legacy(frm);
	frm.set_df_property("custom_drawing_section", "hidden", legacy ? 1 : 0);
	if (legacy) {
		frm.set_read_only();
		frm.disable_save();
	}
}

function qi_guess_drawing(file) {
	// "40.054.GA.R03.pdf" → drawing 40.054.GA, revision 03
	const base = (file || "").replace(/\.(pdf|png|jpe?g)$/i, "");
	const m = base.match(/^(.*?)[ ._-]?R(?:ev)?[ ._-]?(\d{1,2})$/i);
	return m ? { no: m[1], rev: m[2] } : { no: base, rev: "" };
}

// The BOM's drawings as the choices of "Drawing on the BOM".
async function qi_drawing_options(frm, autopick) {
	if (!frm.doc.custom_item) {
		frm.set_df_property("custom_drawing_file", "options", []);
		return;
	}
	const { message: files } = await frappe.call({ method: `${QI}.drawing_options`, args: { item: frm.doc.custom_item } });
	const bom = frm.doc.custom_bom;
	const cur = frm.doc.custom_drawing_file;
	const mine = (files || []).filter(
		(f) => f.name === cur || (bom ? f.attached_to_doctype === "BOM" && f.attached_to_name === bom : true)
	);
	frm.__qi_drawings = files || [];
	const options = [{ label: "", value: "" }].concat(
		mine.map((f) => ({ label: bom ? f.file_name : `${f.file_name} · ${f.attached_to_name}`, value: f.name }))
	);
	if (cur && !mine.some((f) => f.name === cur)) options.push({ label: cur, value: cur }); // uploaded to the template
	frm.set_df_property("custom_drawing_file", "options", options);
	frm.set_df_property("custom_drawing_file", "description", mine.length
		? `<a class="qi-browse">${__("Look at the drawings before choosing")}</a>`
		: bom ? __("{0} has no PDF or image attached. Upload one in the drawing panel below.", [bom]) : "");
	frm.refresh_field("custom_drawing_file");
	$(frm.fields_dict.custom_drawing_file.wrapper).find(".qi-browse").off("click").on("click", () => qi_pick_drawing(frm));
	if (autopick && mine.length === 1 && !frm.doc.custom_drawing_file) frm.set_value("custom_drawing_file", mine[0].name);
}

// Built against a BOM that doesn't point at it yet: offer to tag it.
function qi_tag_prompt(frm) {
	const bom = frm.doc.custom_bom;
	if (frm.is_new() || !bom || !qi_can_edit() || !qi_is_drawing(frm)) return;
	frappe.db.get_value("BOM", bom, "quality_inspection_template").then(({ message }) => {
		if (!message || message.quality_inspection_template === frm.doc.name) return;
		frm.dashboard.set_headline_alert(
			`${__("BOM {0} does not use this template yet{1}.", [frappe.utils.escape_html(bom),
				message.quality_inspection_template ? " " + __("(it uses {0})", [frappe.utils.escape_html(message.quality_inspection_template)]) : ""])}
			<a class="qi-tag-now">${__("Tag it now")}</a>`, "orange");
		frm.dashboard.$wrapper.find(".qi-tag-now").on("click", () => qi_tag_dialog(frm));
	});
}

function qi_can_edit() {
	return frappe.user.has_role(["Quality Manager", "System Manager"]);
}

function qi_is_drawing(frm) {
	return (frm.doc[QI_ROWS] || []).some((r) => r.custom_row_type);
}

function qi_suggest_name(frm, item_name) {
	const d = frm.doc;
	return [d.custom_drawing_no, d.custom_drawing_revision && `Rev ${d.custom_drawing_revision}`, item_name || d.custom_item]
		.filter(Boolean)
		.join(" · ")
		.slice(0, 140);
}

function qi_rename_hint(frm) {
	if (frm.is_new() && frm.doc.custom_item) {
		frappe.db.get_value("Item", frm.doc.custom_item, "item_name").then(({ message }) => {
			frm.set_value("quality_inspection_template_name", qi_suggest_name(frm, message && message.item_name));
		});
	}
}

const qi_esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));

function qi_limit_text(r) {
	if (r.custom_row_type === "Visual") return "OK / NG";
	if (r.custom_tolerance_type === "Reference / basic") return __("not inspected");
	const big = 999999;
	const lo = Math.abs(r.min_value) >= big ? null : r.min_value;
	const hi = Math.abs(r.max_value) >= big ? null : r.max_value;
	const unit = r.custom_unit ? " " + r.custom_unit : "";
	const f = (x) => format_number(x, null, 3);
	if (r.custom_unit === "°") return `${qi_num(lo)}° … ${qi_num(hi)}°`;
	if (["Maximum only", "Geometric (GD&T)"].includes(r.custom_tolerance_type) || lo === null) return `≤ ${f(hi)}${unit}`;
	if (r.custom_tolerance_type === "Minimum only" || hi === null) return `≥ ${f(lo)}${unit}`;
	return `${f(lo)} … ${f(hi)}${unit}`;
}

// ------------------------------------------------------------- the builder --

function qi_builder(frm) {
	if (!frm.__qi_builder) frm.__qi_builder = new QIBuilder(frm);
	frm.__qi_builder.frm = frm;
	return frm.__qi_builder;
}

class QIBuilder {
	constructor(frm) {
		this.frm = frm;
		this.page = 1;
		this.zoom = 1;
		this.mode = "select";
		this.selected = null;
		this.drawing = null;
		this.drawing_url = null;
	}

	get doc() {
		return this.frm.doc;
	}

	mount() {
		const section = this.frm.fields_dict.custom_drawing_section;
		if (!section) return null;
		let $panel = $(this.frm.wrapper).find(".qi-builder");
		if (!$panel.length) {
			// not "form-section": Frappe hides any form-section it finds no fields in
			$panel = $(`<div class="qi-builder card-section"></div>`);
			$(section.wrapper).closest(".form-section, .section-body").first().after($panel);
			if (!$panel.parent().length) $(section.wrapper).after($panel);
		}
		this.$panel = $panel;
		return $panel;
	}

	render() {
		const $p = this.mount();
		if (!$p) return;
		const d = this.doc;
		if (qi_is_legacy(this.frm)) {
			this.render_legacy();
			return;
		}
		this.render_header();
		const locked = !!d.custom_locked;
		const editable = qi_can_edit() && !locked;
		const pick_label = d.custom_drawing ? __("Change drawing") : d.custom_item ? __("Choose drawing") : __("Upload drawing");
		$p.html(`
			<div class="qi-b-banner"></div>
			<div class="qi-b-block">
				<div class="qi-b-head">
					<div class="qi-b-title">${__("Drawing")}</div>
					<span class="qi-b-spacer"></span>
					${editable ? `<button class="btn btn-xs btn-default qi-pick-btn">${pick_label}</button>` : ""}
					${editable && d.custom_drawing ? `<button class="btn btn-xs qi-mode ${this.mode === "draw" ? "btn-primary" : "btn-default"}" data-mode="draw">${__("Mark on drawing")}</button>` : ""}
				</div>
				${d.custom_drawing ? `<div class="qi-b-toolbar">
					<span class="qi-b-hint text-muted small">${editable ? __("Mark on drawing, then drag a box round what is checked: its number goes there.") : ""}</span>
					<span class="qi-b-spacer"></span>
					<span class="qi-b-pages small"></span>
					<button class="btn btn-xs btn-default qi-zoom" data-z="-1">−</button>
					<span class="small qi-zoom-val">${Math.round(this.zoom * 100)}%</span>
					<button class="btn btn-xs btn-default qi-zoom" data-z="1">+</button>
				</div>` : `<div class="qi-b-nodrawing text-muted small">${__("No drawing. Characteristics can be added without one; a drawing can be added at any time.")}</div>`}
				<div class="qi-b-canvas-wrap"><div class="qi-b-stage"><canvas></canvas><div class="qi-b-overlay"></div></div></div>
			</div>
			<div class="qi-b-block">
				<div class="qi-b-head">
					<div class="qi-b-title">${__("Characteristics")}</div>
					<span class="qi-b-count text-muted small"></span>
					<span class="qi-b-spacer"></span>
					${editable ? `<span class="text-muted small">${__("Add")}</span>
					<button class="btn btn-xs btn-default qi-add" data-type="Dimension">${__("Dimensional")}</button>
					<button class="btn btn-xs btn-default qi-add" data-type="Test">${__("Operational")}</button>
					<button class="btn btn-xs btn-default qi-add" data-type="Visual">${__("Visual")}</button>` : ""}
				</div>
				<div class="qi-b-table"></div>
			</div>
			<div class="qi-b-block qi-b-used"></div>
		`);
		this.bind();
		this.render_table();
		this.render_used_by();
		this.render_banner();
		this.load_drawing();
	}

	bind() {
		const $p = this.$panel;
		$p.find(".qi-pick-btn").on("click", () => qi_pick_drawing(this.frm));
		$p.find(".qi-mode").on("click", () => {
			this.mode = this.mode === "draw" ? "select" : "draw";
			$p.find(".qi-mode").toggleClass("btn-primary", this.mode === "draw").toggleClass("btn-default", this.mode !== "draw");
			$p.find(".qi-b-overlay").toggleClass("drawing", this.mode === "draw");
		});
		$p.find(".qi-zoom").on("click", (e) => {
			const z = Number($(e.currentTarget).data("z"));
			this.zoom = Math.min(3, Math.max(0.5, Math.round((this.zoom + z * 0.25) * 100) / 100));
			$p.find(".qi-zoom-val").text(Math.round(this.zoom * 100) + "%");
			this.draw_page();
		});
		$p.find(".qi-add").on("click", (e) => qi_balloon_dialog(this.frm, null, { row_type: $(e.currentTarget).data("type") }));
		this.bind_drawing();
	}

	// ---- drawing ----

	async load_drawing() {
		const url = this.doc.custom_drawing;
		const $wrap = this.$panel.find(".qi-b-canvas-wrap");
		if (!url) {
			$wrap.hide();
			return;
		}
		$wrap.show();
		try {
			if (this.drawing_url !== url) {
				// one open per drawing, even when the form refreshes while it loads
				this.drawing_url = url;
				this.opening = (async () => {
					await frappe.require("/assets/iso_compliance/js/qi_pdf.js");
					if (this.drawing) this.drawing.close();
					this.drawing = await window.iso_qi_pdf.open(url);
					this.page = 1;
				})();
			}
			await this.opening;
			await this.draw_page();
			this.ensure_page_images();
		} catch (e) {
			console.error(e);
			this.drawing_url = null; // try again on the next refresh
			$wrap.html(`<div class="text-danger small" style="padding:12px">${__("Could not show the drawing here")}: ${qi_esc(e.message)}
				· <a href="${qi_esc(url)}" target="_blank" rel="noopener">${__("open the file")}</a></div>`);
		}
	}

	async draw_page() {
		if (!this.drawing) return;
		const $wrap = this.$panel.find(".qi-b-canvas-wrap");
		const canvas = $wrap.find("canvas")[0];
		const width = Math.max(320, ($wrap.width() || 900) - 2) * this.zoom;
		const size = await this.drawing.render(this.page, canvas, width);
		if (!size) return;
		$wrap.find(".qi-b-stage").css({ width: size.w, height: size.h });
		const pages = this.drawing.pages;
		const $pg = this.$panel.find(".qi-b-pages").empty();
		if (pages > 1) {
			$pg.append(`<button class="btn btn-xs btn-default qi-pg" data-d="-1" ${this.page <= 1 ? "disabled" : ""}>‹</button>
				<span>${__("Page {0} of {1}", [this.page, pages])}</span>
				<button class="btn btn-xs btn-default qi-pg" data-d="1" ${this.page >= pages ? "disabled" : ""}>›</button>`);
			$pg.find(".qi-pg").on("click", (e) => {
				this.page += Number($(e.currentTarget).data("d"));
				this.draw_page();
			});
		}
		this.render_boxes();
	}

	// A sharp copy of a page for the popup's close-up, kept until the drawing changes.
	hires(page) {
		const key = `${this.drawing_url}#${page}`;
		if (!this.__hires || this.__hires.url !== this.drawing_url) this.__hires = { url: this.drawing_url };
		if (!this.__hires[key]) {
			this.__hires[key] = (async () => {
				await this.opening;
				const c = document.createElement("canvas");
				const dpr = Math.min(window.devicePixelRatio || 1, 2);
				const pdf = window.iso_qi_pdf.is_pdf(this.drawing_url);
				if (!(await this.drawing.render(page, c, pdf ? 2400 / dpr : 2400))) throw new Error("render cancelled");
				return c;
			})();
			this.__hires[key].catch(() => delete this.__hires[key]);
		}
		return this.__hires[key];
	}

	render_boxes() {
		const $ov = this.$panel.find(".qi-b-overlay").empty();
		for (const r of this.doc[QI_ROWS] || []) {
			const pos = qi_pos(r);
			if (!pos || (pos.page || 1) !== this.page) continue;
			const $b = $(`<div class="qi-box ${this.selected === r.name ? "selected" : ""}" title="${qi_esc(r.custom_spec_text || r.specification)}">
				<span class="qi-balloon">${qi_esc(r.custom_balloon_no || "?")}</span></div>`)
				.css({ left: pos.x + "%", top: pos.y + "%", width: pos.w + "%", height: pos.h + "%" })
				.attr("data-row", r.name);
			$ov.append($b);
		}
		$ov.find(".qi-box").on("click", (e) => {
			if (this.mode === "draw") return;
			e.stopPropagation();
			const row = locals["Item Quality Inspection Parameter"][$(e.currentTarget).data("row")];
			this.select(row.name);
			if (qi_can_edit() && !this.doc.custom_locked) qi_balloon_dialog(this.frm, row);
		});
	}

	bind_drawing() {
		const $ov = this.$panel.find(".qi-b-overlay");
		let start = null;
		let $rect = null;
		const pct = (e) => {
			const b = $ov[0].getBoundingClientRect();
			return {
				x: Math.min(100, Math.max(0, ((e.clientX - b.left) / b.width) * 100)),
				y: Math.min(100, Math.max(0, ((e.clientY - b.top) / b.height) * 100)),
			};
		};
		$ov.on("pointerdown", (e) => {
			if (this.mode !== "draw") return;
			e.preventDefault();
			$ov[0].setPointerCapture(e.pointerId);
			start = pct(e);
			$rect = $(`<div class="qi-box drawing-now"></div>`).appendTo($ov);
		});
		$ov.on("pointermove", (e) => {
			if (!start) return;
			const p = pct(e);
			$rect.css({
				left: Math.min(start.x, p.x) + "%",
				top: Math.min(start.y, p.y) + "%",
				width: Math.abs(p.x - start.x) + "%",
				height: Math.abs(p.y - start.y) + "%",
			});
		});
		$ov.on("pointerup pointercancel", (e) => {
			if (!start) return;
			const p = pct(e);
			const box = {
				page: this.page,
				x: +Math.min(start.x, p.x).toFixed(2),
				y: +Math.min(start.y, p.y).toFixed(2),
				w: +Math.abs(p.x - start.x).toFixed(2),
				h: +Math.abs(p.y - start.y).toFixed(2),
			};
			start = null;
			if (box.w < 0.5 || box.h < 0.5) {
				$rect && $rect.remove();
				return;
			}
			const row = this.selected && locals["Item Quality Inspection Parameter"][this.selected];
			if (row && !qi_pos(row)) {
				// a selected row without a box: place it
				frappe.model.set_value(row.doctype, row.name, "custom_position", JSON.stringify(box));
				this.frm.save().then(() => this.render_boxes());
			} else {
				qi_balloon_dialog(this.frm, null, { position: box, row_type: "Dimension" }, () => $rect && $rect.remove());
			}
		});
	}

	select(rowname) {
		this.selected = rowname;
		const row = rowname && locals["Item Quality Inspection Parameter"][rowname];
		const pos = row && qi_pos(row);
		if (pos && (pos.page || 1) !== this.page) {
			this.page = pos.page || 1;
			this.draw_page();
		} else {
			this.render_boxes();
		}
		// the Characteristics grid row for this balloon
		const grid_row = this.frm.fields_dict[QI_ROWS].grid.grid_rows_by_docname[rowname];
		$(this.frm.fields_dict[QI_ROWS].grid.wrapper).find(".grid-row").removeClass("qi-row-selected");
		if (grid_row) $(grid_row.wrapper).addClass("qi-row-selected");
		const $box = this.$panel.find(`.qi-box[data-row="${rowname}"]`);
		if ($box.length) $box[0].scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
	}

	// Page PNGs for prints, rebuilt only when the drawing changes (SPEC §4.6).
	async ensure_page_images() {
		const d = this.doc;
		if (!qi_can_edit() || !d.custom_drawing || !window.iso_qi_pdf.is_pdf(d.custom_drawing)) return;
		let stored = {};
		try {
			stored = JSON.parse(d.custom_drawing_pages || "{}");
		} catch (e) {
			stored = {};
		}
		const hash = d.custom_drawing_hash || d.custom_drawing;
		if (stored.hash === hash || this.__imaging) return;
		this.__imaging = true;
		try {
			const pages = await window.iso_qi_pdf.page_images(d.custom_drawing);
			const r = await frappe.call({
				method: `${QI}.save_page_images`,
				args: { template: d.name, drawing_hash: hash, pages },
			});
			this.frm.doc.custom_drawing_pages = JSON.stringify({ hash, pages: r.message });
		} finally {
			this.__imaging = false;
		}
	}

	// ---- rows ----

	// One line per characteristic, grouped by kind: what it is (with its class),
	// what is accepted (the drawing's callout under it), at which stages, and
	// how many pieces when that differs from the lot sample. Cards on a phone.
	render_table() {
		const rows = (this.doc[QI_ROWS] || []).filter((r) => r.custom_row_type);
		const $t = this.$panel.find(".qi-b-table");
		if (!rows.length) {
			this.$panel.find(".qi-b-count").text("");
			$t.html(`<div class="qi-empty">${__("No characteristics yet. Mark one on the drawing, or use Add above.")}</div>`);
			return;
		}
		const pill = (text, cls = "") => `<span class="qi-t-pill ${cls}">${qi_esc(text)}</span>`;
		const STAGE_SHORT = { custom_stage_incoming: __("Inc"), custom_stage_in_process: __("Proc"), custom_stage_final: __("Final"),
			custom_stage_fai: __("FAI"), custom_stage_type_test: __("Type") };
		const stages = (r) => QI_STAGES.map(([f, l]) => `<span class="qi-t-stage ${r[f] ? "on" : ""}" title="${qi_esc(l)}">${qi_esc(STAGE_SHORT[f])}</span>`).join("");
		const callout = (r) =>
			r.custom_spec_text
				? qi_esc(r.custom_spec_text) + (r.custom_unit && r.custom_unit !== "°" && r.custom_tolerance_type !== "Geometric (GD&T)" ? " " + qi_esc(r.custom_unit) : "")
				: "";
		const sampling = (r) => {
			const n = (r.custom_instruments || "").split("\n").filter(Boolean).length;
			const freq = r.custom_frequency && r.custom_frequency !== "Every lot" ? r.custom_frequency.replace(" N ", ` ${r.custom_frequency_n || "N"} `) : "";
			return `<div class="qi-t-main">${r.custom_sampling === "Fixed number" ? __("{0} pcs", [qi_esc(r.custom_fixed_count || "?")]) : `<span class="qi-t-dim">${__("Lot")}</span>`}</div>
				<div class="qi-t-sub">${[freq && qi_esc(freq), r.custom_row_type === "Visual" ? "" : n ? __("{0} instrument(s)", [n]) : __("Any instrument")].filter(Boolean).join(" · ")}</div>`;
		};
		const line = (r) => `<div class="qi-t-row ${this.selected === r.name ? "selected" : ""}" data-row="${r.name}">
			<div class="qi-t-no"><span class="qi-balloon static">${qi_esc(r.custom_balloon_no || "")}</span></div>
			<div class="qi-t-what"><div class="qi-t-name">${qi_esc(r.specification)}</div>
				<div class="qi-t-pills">${r.custom_class ? pill(r.custom_class, "class-" + r.custom_class.toLowerCase()) : ""}${
					r.custom_test_method ? pill(r.custom_test_method) : ""}${
					r.custom_row_type === "Dimension" && !qi_pos(r) ? pill(__("No box on drawing"), "warn") : ""}</div></div>
			<div class="qi-t-accept"><div class="qi-t-main qi-mono">${qi_esc(qi_limit_text(r))}</div>${
				callout(r) ? `<div class="qi-t-sub qi-mono">${__("Drawing")} ${callout(r)}</div>` : ""}</div>
			<div class="qi-t-stages">${stages(r)}</div>
			<div class="qi-t-how">${sampling(r)}</div>
		</div>`;
		const kinds = [...QI_ROW_TYPES.map(([v]) => v), ...new Set(rows.map((r) => r.custom_row_type))].filter((v, i, a) => a.indexOf(v) === i);
		const groups = kinds
			.map((k) => [k, rows.filter((r) => r.custom_row_type === k)])
			.filter(([, rs]) => rs.length)
			.map(([k, rs]) => `<div class="qi-t-group"><span>${qi_esc(qi_type_label(k))}</span>${pill(String(rs.length))}</div>${rs.map(line).join("")}`)
			.join("");
		this.$panel.find(".qi-b-count").text(__("{0} · click a row to change it", [rows.length]));
		$t.html(`<div class="qi-t">
			<div class="qi-t-head"><div>${__("No.")}</div><div>${__("Characteristic")}</div><div>${__("Accept")}</div><div>${__("Stages")}</div><div>${__("Sampling")}</div></div>
			${groups}</div>`);
		$t.find(".qi-t-row[data-row]").on("click", (e) => {
			const name = $(e.currentTarget).data("row");
			this.select(name);
			if (qi_can_edit() && !this.doc.custom_locked) qi_balloon_dialog(this.frm, locals["Item Quality Inspection Parameter"][name]);
		});
	}

	// An archived template: its checks, read only, and the way to the new format.
	render_legacy() {
		const rows = this.doc[QI_ROWS] || [];
		const accept = (r) =>
			r.formula_based_criteria ? r.acceptance_formula : r.numeric ? `${qi_num(r.min_value)} … ${qi_num(r.max_value)}` : r.value || "";
		this.$panel.html(`
			<div class="qi-b-head">
				<div class="qi-b-title">${__("Old-format template")}</div>
				<div class="qi-b-status">${__("Archived · read only")}</div>
			</div>
			<div class="alert alert-warning small">${__(
				"Made before drawing-based inspection. Inspections of the items below still use it as it is. To change what is inspected, make the new-format template from the item's drawing; tagging it on the item replaces this one."
			)} ${qi_can_edit() ? `<button class="btn btn-xs btn-primary qi-start-new" style="margin-left:6px">${__("New-format template")}</button>` : ""}</div>
			<div class="qi-b-subtitle">${__("Checks in this template")}</div>
			<table class="table table-sm qi-legacy"><thead><tr><th>${__("Parameter")}</th><th>${__("Group")}</th><th>${__("Accept")}</th></tr></thead>
			<tbody>${rows
				.map((r) => `<tr><td>${qi_esc(r.specification)}</td><td class="text-muted">${qi_esc(r.parameter_group || "")}</td><td>${qi_esc(accept(r))}</td></tr>`)
				.join("")}</tbody></table>
			<div class="qi-b-used"></div>`);
		this.render_used_by();
		this.$panel.find(".qi-start-new").on("click", async () => {
			const { message: m } = await frappe.call({ method: `${QI}.used_by`, args: { template: this.doc.name } });
			const d = new frappe.ui.Dialog({
				title: __("New-format template"),
				fields: [{ fieldname: "item", fieldtype: "Link", options: "Item", label: __("Item"), reqd: 1, default: (m.items[0] || {}).name,
					description: __("Its BOMs' drawings are offered next.") }],
				primary_action_label: __("Next"),
				primary_action: async (v) => {
					d.hide();
					await frappe.require("/assets/iso_compliance/js/qi_start_template.js");
					iso_qi.start_template(v.item);
				},
			});
			d.show();
		});
	}

	// What the plan is and where it stands, as label : value pills, above
	// the setup fields (which fold away once the plan has characteristics).
	render_header() {
		const d = this.doc;
		const section = this.frm.fields_dict.custom_drawing_section;
		if (!section) return;
		let $h = $(this.frm.wrapper).find(".qi-hd");
		if (!$h.length) {
			$h = $(`<div class="qi-hd card-section"></div>`); // not form-section: Frappe hides those without fields
			$(section.wrapper).closest(".form-section").first().before($h);
		}
		if (this.frm.is_new() || qi_is_legacy(this.frm)) {
			$h.empty().hide();
			return;
		}
		const rows = (d[QI_ROWS] || []).filter((r) => r.custom_row_type).length;
		const status = d.custom_superseded_by
			? `<span class="qi-hd-status red">${__("Superseded by {0}", [qi_esc(d.custom_superseded_by)])}</span>`
			: d.custom_locked
			? `<span class="qi-hd-status orange" title="${__("Inspections submitted")}">${__("Locked · change through New Revision")}</span>`
			: `<span class="qi-hd-status green">${__("Editable")}</span>`;
		const kv = (label, value, cls = "") => `<span class="qi-hd-pill ${cls}"><span>${qi_esc(label)}</span>${value}</span>`;
		const dwg = d.custom_drawing
			? qi_esc([d.custom_drawing_no, d.custom_drawing_revision && __("Rev {0}", [d.custom_drawing_revision])].filter(Boolean).join(" · ") || __("attached"))
			: __("None");
		$h.show().html(`<div class="qi-hd-top"><div class="qi-hd-name">${qi_esc(d.quality_inspection_template_name || d.name)}</div>${status}</div>
			<div class="qi-hd-pills">
				${kv(__("Item"), `<b class="qi-hd-item">${qi_esc(d.custom_item || "—")}</b>`)}
				${kv(__("BOM"), qi_esc(d.custom_bom || "—"), d.custom_bom ? "" : "dim")}
				${kv(__("Drawing"), dwg, d.custom_drawing ? "" : "dim")}
				${d.custom_general_tolerance && d.custom_general_tolerance !== "None" ? kv(__("Tolerance"), qi_esc(d.custom_general_tolerance)) : ""}
				${kv(__("Characteristics"), String(rows), rows ? "" : "warn")}
				<span class="qi-hd-used">${kv(__("Used by"), "…", "dim")}</span>
			</div>`);
		if (d.custom_item) {
			frappe.db.get_value("Item", d.custom_item, "item_name").then(({ message }) => {
				if (message && message.item_name) $h.find(".qi-hd-item").after(` <span class="qi-hd-sub">${qi_esc(message.item_name)}</span>`);
			});
		}
	}

	render_used_by() {
		const $u = this.$panel.find(".qi-b-used");
		if (this.frm.is_new()) return;
		frappe.call({ method: `${QI}.used_by`, args: { template: this.doc.name } }).then(({ message: m }) => {
			const n = m.boms.length + m.items.length + m.groups.length;
			$(this.frm.wrapper).find(".qi-hd-used").html(
				`<span class="qi-hd-pill ${n ? "" : "warn"}"><span>${__("Used by")}</span>${
					n ? [m.boms.length && __("{0} BOM(s)", [m.boms.length]), m.items.length && __("{0} Item(s)", [m.items.length]), m.groups.length && __("{0} group(s)", [m.groups.length])].filter(Boolean).join(" · ") : __("nothing yet")
				}</span>`
			);
			const can = qi_can_edit();
			const line = (dt, name, extra) =>
				`<div class="qi-used-line"><a href="/app/${frappe.router.slug(dt)}/${encodeURIComponent(name)}">${qi_esc(dt)} ${qi_esc(name)}</a>
				<span class="text-muted">${qi_esc(extra || "")}</span>${
					can ? ` <a class="qi-untag text-muted small" data-dt="${dt}" data-name="${qi_esc(name)}">${__("untag")}</a>` : ""
				}</div>`;
			const html = [
				...m.boms.map((b) => line("BOM", b.name, (b.is_default ? __("default") : "") + (b.is_active ? "" : " · " + __("inactive")))),
				...m.items.map((i) => line("Item", i.name, i.item_name)),
				...m.groups.map((g) => `<div class="qi-used-line">${__("Item Group")} ${qi_esc(g)} <span class="text-muted">${__("default for the group")}</span></div>`),
			];
			$u.html(`<div class="qi-b-subtitle">${__("Used by")}</div>${
				html.length ? html.join("") : `<div class="text-muted small">${__("Nothing points at this template yet. Use Tag Items / BOMs.")}</div>`
			}`);
			$u.find(".qi-untag").on("click", (e) => {
				const { dt, name } = $(e.currentTarget).data();
				frappe.confirm(__("Remove this template from {0} {1}?", [dt, name]), () =>
					frappe.call({ method: `${QI}.untag`, args: { template: this.doc.name, doctype: dt, name: String(name) } }).then(() => this.render_used_by())
				);
			});
		});
	}

	render_banner() {
		const $b = this.$panel.find(".qi-b-banner").empty();
		const d = this.doc;
		if (this.frm.is_new()) return;
		if (d.custom_superseded_by) {
			$b.html(`<div class="alert alert-warning small">${__("Superseded by {0}", [
				`<a href="/app/quality-inspection-template/${encodeURIComponent(d.custom_superseded_by)}">${qi_esc(d.custom_superseded_by)}</a>`,
			])}</div>`);
			return;
		}
		if (!qi_can_edit()) return;
		frappe.call({ method: `${QI}.earlier_revisions`, args: { template: d.name } }).then(({ message }) => {
			if (!message || !message.length) return;
			for (const old of message) {
				const $a = $(`<div class="alert alert-info small">${__("{0} is still in use by {1} BOM(s) and {2} Item(s).", [
					qi_esc(old.name),
					old.boms.length,
					old.items.length,
				])} <a class="qi-move">${__("Move them to this revision")}</a></div>`).appendTo($b);
				$a.find(".qi-move").on("click", () => qi_move_dialog(this.frm, old));
			}
		});
	}
}

function qi_pos(r) {
	if (!r.custom_position) return null;
	try {
		return JSON.parse(r.custom_position);
	} catch (e) {
		return null;
	}
}

// ------------------------------------------------------ characteristic popup --
// One way in: pick what kind of tolerance the drawing shows (symbol chips),
// fill only the boxes that kind needs, and read back what the drawing says and
// what will be accepted. The callout ("As on drawing") is written from the
// boxes, never typed.

const QI_TT = {
	SYM: "Symmetric",
	DEV: "Deviations",
	LIM: "Limits",
	MAX: "Maximum only",
	MIN: "Minimum only",
	FIT: "ISO fit (ISO 286)",
	GEN: "General (ISO 2768)",
	ANG: "Angle",
	GEO: "Geometric (GD&T)",
	REF: "Reference / basic",
};

// [type, symbol, name, example]
const QI_TT_CHIPS = [
	[QI_TT.SYM, "±", __("Plus / minus"), "12.5 ±0.05"],
	[QI_TT.DEV, "⁺∕₋", __("Unequal + / −"), "12.5 +0.1/−0.05"],
	[QI_TT.LIM, "↔", __("Min to Max"), "12.4 – 12.6"],
	[QI_TT.MAX, "≤", __("Max only"), "≤ 0.5"],
	[QI_TT.MIN, "≥", __("Min only"), "≥ 56"],
	[QI_TT.FIT, "H7", __("ISO fit"), "Ø12 H7"],
	[QI_TT.GEN, "≈", __("General tol."), __("12.5, no tolerance")],
	[QI_TT.ANG, "∠", __("Angle"), "45° ±1°"],
	[QI_TT.GEO, "⌖", __("GD&T"), "⌖ 0.05 | A"],
	[QI_TT.REF, "( )", __("Reference"), "(12.5)"],
];
const QI_TT_NUMERIC_ONLY = [QI_TT.LIM, QI_TT.MAX, QI_TT.MIN, QI_TT.SYM, QI_TT.DEV]; // Test / Material rows

// The boxes each kind needs.
const QI_TT_FIELDS = {
	[QI_TT.SYM]: ["nominal", "tol"],
	[QI_TT.DEV]: ["nominal", "upper_dev", "lower_dev"],
	[QI_TT.LIM]: ["lower", "upper"],
	[QI_TT.MAX]: ["upper"],
	[QI_TT.MIN]: ["lower"],
	[QI_TT.FIT]: ["nominal", "fit_class"],
	[QI_TT.GEN]: ["nominal"],
	[QI_TT.ANG]: ["nominal", "tol"],
	[QI_TT.GEO]: ["gdt_symbol", "tol", "datums"],
	[QI_TT.REF]: ["nominal"],
};
const QI_TOL_FIELDS = ["nominal", "tol", "upper_dev", "lower_dev", "fit_class", "gdt_symbol", "datums", "lower", "upper", "angle_side"];

const QI_GDT = {
	Flatness: "⏥",
	Straightness: "⏤",
	Circularity: "○",
	Cylindricity: "⌭",
	Perpendicularity: "⟂",
	Parallelism: "∥",
	Angularity: "∠",
	Position: "⌖",
	Concentricity: "◎",
	Symmetry: "⌯",
	"Circular runout": "↗",
	"Total runout": "⌰",
	"Profile of a line": "⌒",
	"Profile of a surface": "⌓",
};
const QI_PREFIXES = ["", "Ø", "R", "SØ", "SR", "□"];
// Stored values stay Dimension / Test / Visual; people read these names. The
// Material type (values read off a supplier's 3.1) is no longer offered for new
// rows (developer, 2026-10-14); the 3.1 certificate belongs to the dispatch.
const QI_ROW_TYPES = [
	["Dimension", __("Dimensional")],
	["Test", __("Operational")],
	["Visual", __("Visual")],
];
const qi_type_label = (t) => (QI_ROW_TYPES.find(([v]) => v === t) || [t, t])[1];

function qi_num(x) {
	if (x == null || x === "") return "";
	return String(Number(Number(x).toFixed(6)));
}
const QI_NUM_FIELDS = ["nominal", "tol", "upper_dev", "lower_dev", "lower", "upper", "angle_side"];
// Typed numbers to numbers: "−0,05" → -0.05, blank → null. Anything else stays text so the preview can say so.
function qi_numbers(v) {
	const out = { ...v };
	QI_NUM_FIELDS.forEach((f) => {
		const t = String(v[f] == null ? "" : v[f]).trim().replace(/[−–]/g, "-").replace(",", ".").replace(/^\+/, "");
		out[f] = t === "" ? null : isNaN(Number(t)) ? t : Number(t);
	});
	return out;
}
function qi_bad_numbers(v) {
	return QI_NUM_FIELDS.filter((f) => typeof v[f] === "string");
}
function qi_signed(x) {
	const n = Number(x || 0);
	return n > 0 ? "+" + qi_num(n) : n < 0 ? "−" + qi_num(-n) : "0";
}

// What the drawing says, written from the boxes.
function qi_callout(st, v) {
	const p = st.row_type === "Dimension" ? st.prefix || "" : "";
	const has = (...f) => f.every((k) => v[k] !== undefined && v[k] !== null && v[k] !== "");
	switch (st.tt) {
		case QI_TT.SYM:
			return has("nominal", "tol") ? `${p}${qi_num(v.nominal)} ±${qi_num(v.tol)}` : "";
		case QI_TT.DEV:
			return has("nominal") ? `${p}${qi_num(v.nominal)} ${qi_signed(v.upper_dev)}/${qi_signed(v.lower_dev)}` : "";
		case QI_TT.LIM:
			return has("lower", "upper") ? `${p}${qi_num(v.lower)} – ${qi_num(v.upper)}` : "";
		case QI_TT.MAX:
			return has("upper") ? `≤ ${p}${qi_num(v.upper)}` : "";
		case QI_TT.MIN:
			return has("lower") ? `≥ ${p}${qi_num(v.lower)}` : "";
		case QI_TT.FIT:
			return has("nominal", "fit_class") ? `${p}${qi_num(v.nominal)} ${v.fit_class}` : "";
		case QI_TT.GEN:
			return has("nominal") ? `${p}${qi_num(v.nominal)}` : "";
		case QI_TT.ANG:
			return has("nominal", "tol") ? `${qi_num(v.nominal)}° ±${qi_num(v.tol)}°` : "";
		case QI_TT.GEO: {
			if (!has("tol")) return "";
			const datums = (v.datums || "").split(/[\s,|]+/).filter(Boolean);
			// the name too: some GD&T symbols are missing from the PDF server's fonts
			return [`${QI_GDT[v.gdt_symbol] || ""} ${v.gdt_symbol || ""} ${qi_num(v.tol)}`.trim(), ...datums].join(" | ");
		}
		case QI_TT.REF:
			return has("nominal") ? `(${p}${qi_num(v.nominal)})` : "";
	}
	return "";
}

function qi_prefix_of(spec_text) {
	const m = /^[≤≥(]?\s*(SØ|SR|Ø|R|□)\s*\d/.exec(spec_text || "");
	return m ? m[1] : "";
}

// Measuring instruments, fetched once per page.
function qi_instruments() {
	if (!window.__qi_instruments) {
		window.__qi_instruments = frappe.call({ method: `${QI}.measuring_instruments` }).then((r) => r.message || []);
	}
	return window.__qi_instruments;
}

// Stage check fields on the row and the stage names an inspection carries.
const QI_STAGE_NAMES = {
	custom_stage_incoming: "Incoming",
	custom_stage_in_process: "In Process",
	custom_stage_final: "Final",
};

// custom_instruments: one Asset per line; "Incoming: ASSET" narrows it to a stage.
function qi_parse_instruments(text) {
	const out = { "": new Set() };
	Object.values(QI_STAGE_NAMES).forEach((s) => (out[s] = null)); // null: same as every stage
	(text || "").split("\n").forEach((line) => {
		line = line.trim();
		if (!line) return;
		const i = line.indexOf(":");
		const stage = i > 0 ? line.slice(0, i).trim() : "";
		if (stage && stage in out) (out[stage] = out[stage] || new Set()).add(line.slice(i + 1).trim());
		else out[""].add(line);
	});
	return out;
}
function qi_join_instruments(inst, stages) {
	const lines = [...inst[""]];
	Object.entries(QI_STAGE_NAMES).forEach(([f, s]) => {
		if (stages[f] && inst[s]) inst[s].forEach((n) => lines.push(`${s}: ${n}`));
	});
	return lines.join("\n");
}

function qi_balloon_dialog(frm, row, defaults = {}, on_cancel) {
	const r = row || {};
	const type = r.custom_row_type || defaults.row_type || "Dimension";
	const st = {
		row_type: type,
		cls: r.custom_class || "Major",
		tt: r.custom_tolerance_type || "",
		prefix: qi_prefix_of(r.custom_spec_text),
		dev_signs: qi_dev_signs_of(r.custom_upper_dev, r.custom_lower_dev),
		inst: qi_parse_instruments(r.custom_instruments),
		inst_tab: "",
		inst_filter: "",
		when: {
			stages: Object.fromEntries(
				Object.keys(QI_STAGE_NAMES).map((f) => [f, row ? (r[f] ? 1 : 0) : (type === "Material" ? f === "custom_stage_incoming" : f === "custom_stage_final") ? 1 : 0])
			),
			in_process_at: r.custom_in_process_at || "Every check",
			frequency: r.custom_frequency || "Every lot",
			frequency_n: r.custom_frequency_n || null,
			sampling: r.custom_sampling || "Lot sample",
			fixed_count: r.custom_fixed_count || null,
		},
	};
	if (!st.tt && st.row_type !== "Visual") st.tt = st.row_type === "Dimension" ? QI_TT.SYM : QI_TT.LIM;

	const d = new frappe.ui.Dialog({
		title: row ? __("Characteristic {0}", [r.custom_balloon_no]) : __("New characteristic"),
		size: "large",
		fields: [
			{ fieldtype: "Section Break", fieldname: "char_section", label: __("Characteristic") },
			{ fieldname: "type_html", fieldtype: "HTML" },
			{ fieldtype: "Section Break", fieldname: "what_section" },
			{
				fieldname: "specification",
				fieldtype: "Link",
				options: "Quality Inspection Parameter",
				label: __("Parameter"),
				reqd: 1,
				default: r.specification,
				description: __("e.g. Width, Length, Hardness, Shunt length"),
			},
			{
				fieldname: "work_instruction",
				fieldtype: "Link",
				options: "Controlled Document",
				label: __("Work instruction"),
				default: r.custom_work_instruction,
				hidden: 1,
				get_query: () => ({ filters: { name: ["like", "%WI-%"] } }),
				description: __("How the check is done. Its test methods are offered next."),
			},
			{ fieldname: "test_method", fieldtype: "Link", options: "Test Method", label: __("Test method"), default: r.custom_test_method, hidden: 1 },
			{ fieldtype: "Column Break" },
			{ fieldname: "balloon_no", fieldtype: "Data", label: __("Reference no."), default: r.custom_balloon_no, description: __("Blank: the next number") },
			{ fieldtype: "Column Break" },
			{ fieldname: "class_html", fieldtype: "HTML" },

			{ fieldtype: "Section Break", fieldname: "tol_section", label: __("Tolerance as specified on the drawing") },
			{ fieldname: "general_html", fieldtype: "HTML" },
			{ fieldname: "tt_html", fieldtype: "HTML" },
			{ fieldname: "prefix_html", fieldtype: "HTML" },
			{ fieldname: "dev_html", fieldtype: "HTML" },
			{ fieldtype: "Section Break", fieldname: "tol_inputs" },
			// three columns, so each kind's boxes sit side by side
			{ fieldname: "nominal", fieldtype: "Data", label: __("Nominal value"), default: qi_num(r.custom_nominal) },
			{ fieldname: "lower", fieldtype: "Data", label: __("Lower limit"), default: qi_num(qi_shown_limit(r.min_value)) },
			{
				fieldname: "gdt_symbol",
				fieldtype: "Select",
				label: __("Geometric characteristic"),
				options: Object.entries(QI_GDT).map(([value, sym]) => ({ value, label: `${sym}  ${__(value)}` })),
				default: r.custom_gdt_symbol || "Position",
			},
			{ fieldtype: "Column Break" },
			{ fieldname: "tol", fieldtype: "Data", label: __("Tolerance (±)"), default: qi_num(r.custom_tol) },
			{ fieldname: "upper_dev", fieldtype: "Data", label: __("Upper deviation"), default: qi_num(qi_abs(r.custom_upper_dev)) },
			{ fieldname: "upper", fieldtype: "Data", label: __("Upper limit"), default: qi_num(qi_shown_limit(r.max_value)) },
			{ fieldname: "fit_class", fieldtype: "Data", label: __("Fit (ISO 286)"), default: r.custom_fit_class, description: __("e.g. H7, h9, js7") },
			{ fieldtype: "Column Break" },
			{ fieldname: "lower_dev", fieldtype: "Data", label: __("Lower deviation"), default: qi_num(qi_abs(r.custom_lower_dev)) },
			{ fieldname: "datums", fieldtype: "Data", label: __("Datum references"), default: r.custom_datums, description: __("e.g. A B") },
			{
				fieldname: "angle_side",
				fieldtype: "Data",
				label: __("Shorter side of the angle (mm)"),
				hidden: 1,
				description: __("ISO 2768 angular tolerance depends on it."),
			},
			{
				fieldname: "unit",
				fieldtype: "Link",
				options: "UOM",
				label: __("Unit of measure"),
				default: r.custom_unit || (st.row_type === "Dimension" ? "mm" : ""),
			},
			{ fieldtype: "Section Break", fieldname: "preview_section" },
			{ fieldname: "limits_preview", fieldtype: "HTML" },

			{ fieldtype: "Section Break", fieldname: "when_section", label: __("Inspection stages, frequency and sample size"), collapsible: 1 },
			{ fieldname: "when_html", fieldtype: "HTML" },

			{ fieldtype: "Section Break", fieldname: "inst_section", label: __("Measuring instruments"), collapsible: 1 },
			{ fieldname: "inst_html", fieldtype: "HTML" },
		],
		primary_action_label: row ? __("Save") : __("Add"),
		primary_action: (v) => qi_save_balloon(frm, row, v, defaults.position, d, st),
		secondary_action_label: row ? __("Delete") : null,
		secondary_action: row
			? () =>
					frappe.confirm(__("Delete characteristic {0}?", [r.custom_balloon_no]), () => {
						frm.get_field(QI_ROWS).grid.grid_rows_by_docname[row.name].remove();
						d.hide();
						frm.save();
					})
			: null,
	});
	d.$wrapper.addClass("qi-dialog");

	const preview = frappe.utils.debounce(() => qi_preview(d, st, frm), 200);
	const refresh = () => {
		qi_render_type(d, st, refresh);
		qi_render_class(d, st);
		qi_render_general(d, st, frm, refresh);
		qi_render_tt(d, st, refresh);
		qi_render_prefix(d, st, refresh);
		qi_render_dev_signs(d, st, refresh);
		qi_show_fields(d, st);
		qi_render_when(d, st);
		qi_render_instruments(d, st);
		preview();
	};
	[...QI_TOL_FIELDS, "unit"].forEach((f) => (d.fields_dict[f].df.onchange = f === "unit" ? refresh : preview));
	d.fields_dict.work_instruction.df.onchange = () => qi_from_work_instruction(d);
	d.fields_dict.test_method.df.onchange = () => qi_from_test_method(d, st);
	d.onhide = () => on_cancel && !d.__saved && on_cancel();
	d.show();
	refresh();
	qi_from_work_instruction(d, true);
	// the drawing sits between the title and the scrolling body, so it stays in view
	const $host = $(`<div class="qi-dp-host"></div>`).insertAfter(d.$wrapper.find(".modal-header"));
	qi_drawing_pane(frm, d, $host, defaults.position || qi_pos(r));
}

const QI_CLASSES = [
	["CTQ", __("CTQ"), __("Critical to quality: every planned sample must be measured before the inspection can be submitted.")],
	["Major", __("Major"), __("Affects fit or function.")],
	["Minor", __("Minor"), __("Little effect on fit or function.")],
];
function qi_render_class(d, st) {
	const $w = d.fields_dict.class_html.$wrapper;
	$w.html(`<div class="form-group"><label class="control-label">${__("Classification")}</label>
		<div class="qi-pills">${QI_CLASSES.map(
			([v, label, hint]) => `<button type="button" class="qi-pill ${v.toLowerCase()} ${st.cls === v ? "on" : ""}" data-v="${v}" title="${qi_esc(hint)}">${qi_esc(label)}</button>`
		).join("")}</div></div>`);
	$w.find(".qi-pill").on("click", (e) => {
		st.cls = String($(e.currentTarget).data("v"));
		qi_render_class(d, st);
	});
}

// ---- inspection stages, frequency and sample size ----
// Four rows of choices, each with what it means on hover.

const QI_WHEN = {
	in_process_at: [
		["Every check", __("Every check"), __("At every in-process check of the Work Order: First, Random and Last Check.")],
		["First Check only", __("First Check only"), __("Only on the first pieces off a new set-up.")],
		["First and Last Check", __("First and Last Check"), __("On the first pieces off the set-up and on the last pieces of the run.")],
	],
	frequency: [
		["Every lot", __("Every lot"), __("Checked on every lot that reaches this stage.")],
		["First article only", __("First article only"), __("Checked once, on the first lot of this drawing revision.")],
		["Every N lots", __("Every N lots"), __("Checked on one lot in every N; the lots in between skip it.")],
		["Every N months", __("Every N months"), __("Checked when N months have passed since it was last checked.")],
	],
	sampling: [
		["Lot sample", __("Sampling plan"), __("As many pieces as the inspection's sample size, taken from the lot by the sampling plan.")],
		["Fixed number", __("Fixed quantity"), __("Always this many pieces, whatever the lot size.")],
	],
};
const qi_tip = (text) => `<span class="qi-tip" title="${qi_esc(text)}">i</span>`;

function qi_render_when(d, st) {
	const w = st.when;
	const $w = d.fields_dict.when_html.$wrapper;
	const pills = (key, opts) =>
		opts.map(([v, label, tip]) => `<button type="button" class="qi-pill ${w[key] === v ? "on" : ""}" data-k="${key}" data-v="${qi_esc(v)}" title="${qi_esc(tip)}">${qi_esc(label)}</button>`).join("");
	const n_freq = ["Every N lots", "Every N months"].includes(w.frequency);
	$w.html(`<div class="qi-when">
		<div class="qi-when-row"><div class="qi-when-label">${__("Inspection stages")} ${qi_tip(__("Where this characteristic is checked. Tick every stage that applies."))}</div>
			<div class="qi-pills">${Object.entries(QI_STAGE_NAMES)
				.map(([f]) => {
					const label = QI_STAGES.find(([x]) => x === f)[1];
					return `<button type="button" class="qi-pill check ${w.stages[f] ? "on" : ""}" data-stage="${f}">${w.stages[f] ? "✓ " : ""}${qi_esc(label)}</button>`;
				})
				.join("")}</div></div>
		${w.stages.custom_stage_in_process ? `<div class="qi-when-row"><div class="qi-when-label">${__("In-process checkpoint")} ${qi_tip(__("Which in-process checks of a Work Order include this characteristic."))}</div>
			<div class="qi-pills">${pills("in_process_at", QI_WHEN.in_process_at)}</div></div>` : ""}
		<div class="qi-when-row"><div class="qi-when-label">${__("Frequency")} ${qi_tip(__("How often a lot is checked for this characteristic."))}</div>
			<div class="qi-pills">${pills("frequency", QI_WHEN.frequency)}
			${n_freq ? `<label class="qi-when-n">N <input type="number" min="1" class="form-control input-xs" data-n="frequency_n" value="${qi_esc(w.frequency_n || "")}"></label>` : ""}</div></div>
		<div class="qi-when-row"><div class="qi-when-label">${__("Sample size")} ${qi_tip(__("How many pieces of a checked lot are measured."))}</div>
			<div class="qi-pills">${pills("sampling", QI_WHEN.sampling)}
			${w.sampling === "Fixed number" ? `<label class="qi-when-n">${__("Pieces")} <input type="number" min="1" class="form-control input-xs" data-n="fixed_count" value="${qi_esc(w.fixed_count || "")}"></label>` : ""}</div></div>
	</div>`);
	$w.find("[data-stage]").on("click", (e) => {
		const f = $(e.currentTarget).data("stage");
		w.stages[f] = w.stages[f] ? 0 : 1;
		qi_render_when(d, st);
		qi_render_instruments(d, st);
		qi_when_title(d, st);
	});
	$w.find("[data-k]").on("click", (e) => {
		w[$(e.currentTarget).data("k")] = String($(e.currentTarget).data("v"));
		qi_render_when(d, st);
		qi_when_title(d, st);
	});
	$w.find("[data-n]").on("change", (e) => {
		w[$(e.currentTarget).data("n")] = parseInt(e.currentTarget.value, 10) || null;
		qi_when_title(d, st);
	});
	qi_when_title(d, st);
}

// The section opens closed; its title says what is set.
function qi_when_title(d, st) {
	const w = st.when;
	const stages = Object.keys(QI_STAGE_NAMES).filter((f) => w.stages[f]).map((f) => QI_STAGES.find(([x]) => x === f)[1]);
	const freq = w.frequency.replace(" N ", ` ${w.frequency_n || "N"} `);
	const pieces = w.sampling === "Fixed number" ? __("{0} pcs", [w.fixed_count || "?"]) : __("sampling plan");
	d.fields_dict.when_section.wrapper
		.find(".section-head")
		.first()
		.contents()
		.filter((_, n) => n.nodeType === 3 && n.textContent.trim())
		.first()
		.replaceWith(`${__("Inspection stages, frequency and sample size")} · ${stages.join(", ") || __("no stage")} · ${__(freq)} · ${pieces}`);
}

function qi_show_fields(d, st) {
	const need = new Set(st.row_type === "Visual" ? [] : QI_TT_FIELDS[st.tt] || []);
	if (st.tt === QI_TT.GEN && d.get_value("unit") === "°") need.add("angle_side");
	QI_TOL_FIELDS.forEach((f) => d.set_df_property(f, "hidden", need.has(f) ? 0 : 1));
	d.set_df_property("tol", "label", st.tt === QI_TT.GEO ? __("Tolerance zone") : st.tt === QI_TT.ANG ? __("Tolerance (±°)") : __("Tolerance (±)"));
	d.set_df_property("nominal", "label", st.tt === QI_TT.ANG ? __("Nominal angle (°)") : __("Nominal value"));
	const visual = st.row_type === "Visual";
	const test = st.row_type === "Test";
	d.set_df_property("tol_section", "hidden", visual ? 1 : 0);
	d.set_df_property("tol_inputs", "hidden", visual ? 1 : 0);
	d.set_df_property("unit", "hidden", visual ? 1 : 0);
	d.set_df_property("inst_section", "hidden", visual ? 1 : 0);
	d.set_df_property("tol_section", "label", test || st.row_type === "Material" ? __("Acceptance limits") : __("Tolerance as specified on the drawing"));
	d.set_df_property("work_instruction", "hidden", test ? 0 : 1);
	d.set_df_property("work_instruction", "reqd", test ? 1 : 0);
	d.set_df_property("test_method", "hidden", test ? 0 : 1);
	d.set_df_property("test_method", "reqd", test ? 1 : 0);
}

// An Operational check goes through its work instruction: the test methods
// written under it are offered (all of them while none is linked yet).
async function qi_from_work_instruction(d, quiet) {
	const wi = d.get_value("work_instruction");
	const methods = wi ? await frappe.db.get_list("Test Method", { filters: { procedure: wi }, pluck: "name", limit: 100 }) : [];
	d.fields_dict.test_method.get_query = () => (methods.length ? { filters: { name: ["in", methods] } } : {});
	d.set_df_property(
		"test_method",
		"description",
		!wi ? __("Choose the work instruction first.") : methods.length ? __("{0} test method(s) under {1}.", [methods.length, wi]) : __("No test method is linked to {0} yet: all are offered.", [wi])
	);
	if (!quiet && methods.length === 1 && !d.get_value("test_method")) d.set_value("test_method", methods[0]);
}

// A Test row takes its unit, instruments and (when unset) work instruction from the Test Method.
async function qi_from_test_method(d, st) {
	const tm = d.get_value("test_method");
	if (!tm) return;
	const doc = await frappe.db.get_doc("Test Method", tm);
	if (doc.result_unit && !d.get_value("unit")) d.set_value("unit", doc.result_unit);
	if (doc.procedure && !d.get_value("work_instruction")) d.set_value("work_instruction", doc.procedure);
	if (!st.inst[""].size && (doc.instruments || []).length) {
		const items = doc.instruments.map((i) => i.instrument_item);
		(await qi_instruments()).filter((a) => items.includes(a.item_code)).forEach((a) => st.inst[""].add(a.name));
		qi_render_instruments(d, st);
	}
}

// ---- measuring instruments ----
// One choice for every stage, and per stage "same as every stage" or its own.
// Search narrows the list; a tick on an instrument type takes all its units.

async function qi_render_instruments(d, st) {
	const $w = d.fields_dict.inst_html.$wrapper;
	const all = await qi_instruments();
	const stages = Object.entries(QI_STAGE_NAMES).filter(([f]) => st.when.stages[f]);
	if (st.inst_tab && !stages.some(([, s]) => s === st.inst_tab)) st.inst_tab = "";
	const tab = st.inst_tab;
	const own = tab === "" || !!st.inst[tab];
	const set = tab === "" ? st.inst[""] : st.inst[tab] || st.inst[""];
	const q = st.inst_filter.toLowerCase();
	const groups = {};
	all.filter((a) => !q || `${a.item_name} ${a.asset_name} ${a.name} ${a.location || ""}`.toLowerCase().includes(q)).forEach((a) => (groups[a.item_name] = groups[a.item_name] || []).push(a));
	const short = (a) => (a.asset_name || a.name).replace(a.item_name, "").trim() || a.name;
	const count = (s) => (s ? s.size : null);
	const tab_label = (s) => {
		const n = s === "" ? count(st.inst[""]) : st.inst[s] ? count(st.inst[s]) : null;
		return n == null ? __("same") : n ? n : __("any");
	};
	$w.html(`<div class="qi-inst-tabs">
			<button type="button" class="qi-pill ${tab === "" ? "on" : ""}" data-tab="">${__("Every stage")} <span class="qi-badge">${tab_label("")}</span></button>
			${stages.map(([f, s]) => `<button type="button" class="qi-pill ${tab === s ? "on" : ""}" data-tab="${s}">${qi_esc(QI_STAGES.find(([x]) => x === f)[1])} <span class="qi-badge">${tab_label(s)}</span></button>`).join("")}
		</div>
		${tab ? `<label class="qi-inst-same"><input type="checkbox" ${own ? "" : "checked"}> ${__("Same instruments as every stage")}</label>` : ""}
		<div class="qi-inst-head">
			<input type="search" class="form-control input-sm qi-inst-search" placeholder="${__("Search instruments, e.g. micrometer, 0013")}" value="${qi_esc(st.inst_filter)}">
			<span class="text-muted small qi-inst-note">${
				!own ? __("Uses the every-stage choice.") : set.size ? __("{0} ticked: the inspector chooses one of these.", [set.size]) : __("None ticked: any measuring instrument.")
			}</span>
			${own ? `<a class="qi-inst-all small">${__("Tick shown")}</a> · <a class="qi-inst-none small">${__("Clear")}</a>` : ""}
		</div>
		<div class="qi-inst ${own ? "" : "off"}">${
			Object.entries(groups)
				.map(([name, assets]) => {
					const on = assets.filter((a) => set.has(a.name)).length;
					return `<div class="qi-inst-grp">
						<label class="qi-inst-type"><input type="checkbox" data-grp="${qi_esc(name)}" ${on === assets.length ? "checked" : ""} ${on && on < assets.length ? 'data-partial="1"' : ""} ${own ? "" : "disabled"}>
							${qi_esc(name)} <span class="text-muted">(${assets.length})</span></label>
						<div class="qi-inst-assets">${assets
							.map(
								(a) => `<label class="qi-inst-asset ${set.has(a.name) ? "on" : ""}" title="${qi_esc(a.name)}${a.location ? " · " + qi_esc(a.location) : ""}">
									<input type="checkbox" data-asset="${qi_esc(a.name)}" ${set.has(a.name) ? "checked" : ""} ${own ? "" : "disabled"}> ${qi_esc(short(a))}</label>`
							)
							.join("")}</div></div>`;
				})
				.join("") || `<div class="text-muted small">${__("No instrument matches.")}</div>`
		}</div>`);
	$w.find("[data-partial]").prop("indeterminate", true);
	const redraw = () => qi_render_instruments(d, st);
	$w.find("[data-tab]").on("click", (e) => {
		st.inst_tab = String($(e.currentTarget).data("tab") || "");
		redraw();
	});
	$w.find(".qi-inst-same input").on("change", (e) => {
		st.inst[tab] = e.currentTarget.checked ? null : new Set(st.inst[""]);
		redraw();
	});
	const $search = $w.find(".qi-inst-search");
	$search.on(
		"input",
		frappe.utils.debounce(() => {
			st.inst_filter = $search.val() || "";
			redraw().then(() => {
				const el = $w.find(".qi-inst-search")[0];
				el.focus();
				el.setSelectionRange(el.value.length, el.value.length);
			});
		}, 250)
	);
	$w.find("input[data-grp]").on("change", (e) => {
		const tick = e.currentTarget.checked;
		groups[$(e.currentTarget).data("grp")].forEach((a) => (tick ? set.add(a.name) : set.delete(a.name)));
		redraw();
	});
	$w.find("input[data-asset]").on("change", (e) => {
		const name = $(e.currentTarget).data("asset");
		e.currentTarget.checked ? set.add(name) : set.delete(name);
		redraw();
	});
	$w.find(".qi-inst-all").on("click", () => {
		Object.values(groups).flat().forEach((a) => set.add(a.name));
		redraw();
	});
	$w.find(".qi-inst-none").on("click", () => {
		set.clear();
		redraw();
	});
	const n = st.inst[""].size;
	const per = stages.filter(([, s]) => st.inst[s]).length;
	d.fields_dict.inst_section.wrapper
		.find(".section-head")
		.first()
		.contents()
		.filter((_, node) => node.nodeType === 3 && node.textContent.trim())
		.first()
		.replaceWith(`${__("Measuring instruments")} · ${n ? __("{0} chosen", [n]) : __("any")}${per ? " · " + __("{0} stage(s) differ", [per]) : ""}`);
}

async function qi_save_balloon(frm, row, v, position, dialog, st) {
	v = qi_dev_apply(st, qi_numbers(v));
	const w = st.when;
	const visual = st.row_type === "Visual";
	const bad = visual ? [] : qi_bad_numbers(v).filter((f) => !dialog.fields_dict[f].df.hidden);
	if (bad.length) {
		frappe.msgprint(__("Not a number: {0}", [bad.map((f) => dialog.fields_dict[f].df.label).join(", ")]));
		return;
	}
	if (!visual && !st.tt) {
		frappe.msgprint(__("Choose how the tolerance is shown on the drawing."));
		return;
	}
	if (!Object.values(w.stages).some(Boolean) && !(row && (row.custom_stage_fai || row.custom_stage_type_test))) {
		frappe.msgprint(__("Choose at least one inspection stage."));
		return;
	}
	let tolerance_type = visual ? null : st.tt;
	let tol = v.tol;
	// A general-tolerance angle becomes an explicit Angle with the ISO 2768 value.
	if (tolerance_type === QI_TT.GEN && v.unit === "°") {
		if (!v.angle_side) {
			frappe.msgprint(__("Give the shorter side of the angle so the ISO 2768 angular tolerance can be found."));
			return;
		}
		const { message: m } = await frappe.call({
			method: `${QI_API}.compute_limits`,
			args: { ...qi_limit_args(st, v), general: frm.doc.custom_general_tolerance },
		});
		if (m.error) {
			frappe.msgprint(m.error);
			return;
		}
		tolerance_type = QI_TT.ANG;
		tol = (m.max_value - m.min_value) / 2;
	}
	const need = new Set(visual ? [] : QI_TT_FIELDS[tolerance_type] || []);
	const keep = (f, val) => (need.has(f) ? val : null); // boxes the kind doesn't use are cleared
	const target = row || frm.add_child(QI_ROWS);
	const before = row ? { ...row } : null;
	const values = {
		custom_row_type: st.row_type,
		specification: v.specification,
		custom_balloon_no: v.balloon_no || target.custom_balloon_no || "",
		custom_test_method: st.row_type === "Test" ? v.test_method : null,
		custom_work_instruction: st.row_type === "Test" ? v.work_instruction : null,
		custom_unit: visual ? "" : v.unit,
		custom_class: st.cls,
		custom_spec_text: visual ? "" : qi_callout({ ...st, tt: st.tt }, v),
		custom_tolerance_type: tolerance_type,
		custom_nominal: keep("nominal", v.nominal),
		custom_tol: tolerance_type === QI_TT.ANG ? tol : keep("tol", tol),
		custom_upper_dev: keep("upper_dev", v.upper_dev),
		custom_lower_dev: keep("lower_dev", v.lower_dev),
		custom_fit_class: keep("fit_class", v.fit_class),
		custom_gdt_symbol: keep("gdt_symbol", v.gdt_symbol),
		custom_datums: keep("datums", v.datums),
		custom_frequency: w.frequency,
		custom_frequency_n: w.frequency_n,
		custom_sampling: w.sampling,
		custom_fixed_count: w.fixed_count,
		custom_instruments: visual ? null : qi_join_instruments(st.inst, w.stages) || null,
		custom_in_process_at: w.in_process_at || "Every check",
		...w.stages,
	};
	if ([QI_TT.LIM, QI_TT.MIN].includes(tolerance_type)) values.min_value = v.lower;
	if ([QI_TT.LIM, QI_TT.MAX].includes(tolerance_type)) values.max_value = v.upper;
	if (position) values.custom_position = JSON.stringify(position);
	Object.assign(target, values);
	dialog.__saved = true;
	frm.dirty();
	try {
		await frm.save();
		if (frm.is_dirty()) throw new Error("not saved"); // frm.save() resolves even when the server refuses
		dialog.hide();
	} catch (e) {
		dialog.__saved = false;
		// the server refused: take the row back out (new) or put it back (edit), and keep the popup open
		if (before) Object.assign(target, before);
		else frm.doc[QI_ROWS] = frm.doc[QI_ROWS].filter((x) => x !== target);
		frm.refresh_field(QI_ROWS);
		frm.doc.__unsaved = 0;
		frm.toolbar && frm.toolbar.refresh();
	}
}

// ---- the drawing, inside the popup ----
// The region round the box, from a sharp copy of the page the builder keeps.

async function qi_drawing_pane(frm, d, $host, pos) {
	const builder = frm.__qi_builder;
	if (!frm.doc.custom_drawing || !builder || !builder.drawing_url) return $host.remove();
	const page = (pos && pos.page) || builder.page || 1;
	$host.html(`<div class="qi-dp"><div class="qi-dp-msg text-muted small">${__("Loading drawing…")}</div></div>`);
	try {
		const hi = await builder.hires(page);
		const boxes = (frm.doc[QI_ROWS] || []).map(qi_pos).filter((p) => p && (p.page || 1) === page);
		const focus = pos && pos.w && (pos.page || 1) === page ? { ...pos } : null;
		window.iso_qi_pdf.closeup($host, hi).show(focus, focus ? boxes.filter((p) => JSON.stringify(p) !== JSON.stringify(pos)).concat(focus) : boxes);
	} catch (e) {
		$host.find(".qi-dp-msg").text(__("Could not show the drawing here"));
	}
}

// ---- general tolerances, inside the popup ----
// The drawing's title block values, shown (and changeable) where they are used.

function qi_render_general(d, st, frm, refresh) {
	const $w = d.fields_dict.general_html.$wrapper;
	if (st.row_type !== "Dimension") return $w.empty();
	const opts = (f) => (frappe.meta.get_docfield(frm.doctype, f).options || "").split("\n");
	const select = (f, title) => {
		const cur = frm.doc[f] || "None";
		return `<label class="qi-gen-item">${qi_esc(title)}
			<select class="form-control input-xs" data-f="${f}">${opts(f)
				.map((o) => `<option value="${qi_esc(o)}" ${o === cur ? "selected" : ""}>${qi_esc(o === "None" ? __("none on the drawing") : o)}</option>`)
				.join("")}</select></label>`;
	};
	const missing = st.tt === QI_TT.GEN && (!frm.doc.custom_general_tolerance || frm.doc.custom_general_tolerance === "None");
	$w.html(`<div class="qi-gen ${missing ? "warn" : ""}">
		<span class="qi-gen-title">${__("General tolerances on this drawing")}</span>
		${select("custom_general_tolerance", __("Linear & angular (ISO 2768-1)"))}
		${select("custom_general_geometric", __("Geometric (ISO 2768-2)"))}
		<span class="text-muted small">${__("Used for any size printed without its own tolerance. Saved with this characteristic.")}</span>
	</div>`);
	$w.find("select").on("change", (e) => {
		const f = $(e.currentTarget).data("f");
		frm.doc[f] = e.currentTarget.value;
		frm.refresh_field(f);
		frm.dirty();
		refresh();
	});
}

function qi_render_type(d, st, refresh) {
	const $w = d.fields_dict.type_html.$wrapper;
	$w.html(`<div class="qi-seg">${QI_ROW_TYPES.map(
		([v, label]) => `<button type="button" class="qi-seg-btn ${st.row_type === v ? "on" : ""}" data-v="${v}">${qi_esc(label)}</button>`
	).join("")}</div>`);
	$w.find(".qi-seg-btn").on("click", (e) => {
		const v = $(e.currentTarget).data("v");
		if (v === st.row_type) return;
		st.row_type = v;
		if (v === "Visual") st.tt = "";
		else if (v !== "Dimension" && !QI_TT_NUMERIC_ONLY.includes(st.tt)) st.tt = QI_TT.LIM;
		else if (!st.tt) st.tt = v === "Dimension" ? QI_TT.SYM : QI_TT.LIM;
		if (v === "Material") d.set_values({ custom_stage_incoming: 1, custom_stage_final: 0 });
		if (v === "Dimension" && !d.get_value("unit")) d.set_value("unit", "mm");
		if (v !== "Dimension" && d.get_value("unit") === "mm") d.set_value("unit", "");
		refresh();
	});
}

function qi_render_tt(d, st, refresh) {
	const chips = st.row_type === "Dimension" ? QI_TT_CHIPS : QI_TT_CHIPS.filter(([t]) => QI_TT_NUMERIC_ONLY.includes(t));
	const $w = d.fields_dict.tt_html.$wrapper;
	$w.html(`<div class="qi-chips">${chips
		.map(
			([t, sym, name, ex]) => `<button type="button" class="qi-chip ${st.tt === t ? "on" : ""}" data-t="${qi_esc(t)}">
				<span class="qi-chip-sym">${qi_esc(sym)}</span><span class="qi-chip-name">${qi_esc(name)}</span><span class="qi-chip-ex">${qi_esc(ex)}</span></button>`
		)
		.join("")}</div>`);
	$w.find(".qi-chip").on("click", (e) => {
		st.tt = $(e.currentTarget).data("t");
		if (st.tt === QI_TT.ANG) d.set_value("unit", "°");
		else if (d.get_value("unit") === "°" && st.row_type === "Dimension") d.set_value("unit", "mm");
		refresh();
	});
}

function qi_render_prefix(d, st, refresh) {
	const $w = d.fields_dict.prefix_html.$wrapper;
	const show = st.row_type === "Dimension" && ![QI_TT.ANG, QI_TT.GEO].includes(st.tt);
	if (!show) return $w.empty();
	$w.html(`<div class="qi-prefix"><span class="text-muted small">${__("Symbol before the number")}</span>${QI_PREFIXES.map(
		(p) => `<button type="button" class="qi-seg-btn sm ${st.prefix === p ? "on" : ""}" data-p="${p}">${p || __("none")}</button>`
	).join("")}</div>`);
	$w.find("button").on("click", (e) => {
		st.prefix = String($(e.currentTarget).data("p") || "");
		refresh();
	});
}

// Unequal tolerance: both deviations above nominal (+/+), either side (+/−) or
// both below (−/−). The toggle gives the signs; the boxes take the sizes.
const QI_DEV_SIGNS = [
	["+-", "+ / −", "12.5 +0.1/−0.05"],
	["++", "+ / +", "12.5 +0.2/+0.1"],
	["--", "− / −", "12.5 −0.05/−0.15"],
];
function qi_abs(x) {
	return x == null || x === "" ? x : Math.abs(Number(x));
}
function qi_dev_signs_of(upper, lower) {
	if (Number(upper) < 0) return "--";
	if (Number(lower) > 0) return "++";
	return "+-";
}
function qi_dev_apply(st, v) {
	if (st.tt !== QI_TT.DEV) return v;
	const [su, sl] = { "+-": [1, -1], "++": [1, 1], "--": [-1, -1] }[st.dev_signs] || [1, -1];
	const sign = (x, k) => (typeof x === "number" ? k * Math.abs(x) : x);
	let u = sign(v.upper_dev, su);
	let l = sign(v.lower_dev, sl);
	if (typeof u === "number" && typeof l === "number" && u < l) [u, l] = [l, u]; // typed the other way round
	return { ...v, upper_dev: u, lower_dev: l };
}
const QI_DEV_LABELS = {
	"+-": [__("+ Upper deviation"), __("− Lower deviation")],
	"++": [__("+ Upper deviation (larger)"), __("+ Lower deviation (smaller)")],
	"--": [__("− Upper deviation (smaller)"), __("− Lower deviation (larger)")],
};
function qi_render_dev_signs(d, st, refresh) {
	const $w = d.fields_dict.dev_html.$wrapper;
	if (st.row_type === "Visual" || st.tt !== QI_TT.DEV) return $w.empty();
	const ex = (QI_DEV_SIGNS.find(([k]) => k === st.dev_signs) || [])[2] || "";
	$w.html(`<div class="qi-prefix"><span class="text-muted small">${__("Deviations")}</span>${QI_DEV_SIGNS.map(
		([k, label]) => `<button type="button" class="qi-seg-btn sm ${st.dev_signs === k ? "on" : ""}" data-k="${k}">${label}</button>`
	).join("")}<span class="text-muted small">${__("e.g.")} ${qi_esc(ex)}</span></div>`);
	$w.find("button").on("click", (e) => {
		st.dev_signs = String($(e.currentTarget).data("k"));
		refresh();
	});
	const [ul, ll] = QI_DEV_LABELS[st.dev_signs];
	d.set_df_property("upper_dev", "label", ul);
	d.set_df_property("lower_dev", "label", ll);
}

function qi_preview_html(d, html) {
	d.fields_dict.limits_preview.$wrapper.html(`<div class="qi-preview">${html}</div>`);
}

function qi_limit_args(st, v) {
	return {
		tolerance_type: st.tt,
		nominal: v.nominal,
		tol: v.tol,
		upper_dev: v.upper_dev,
		lower_dev: v.lower_dev,
		fit_class: v.fit_class,
		lower: v.lower,
		upper: v.upper,
		angle_side: v.unit === "°" ? v.angle_side : null,
		zone: st.tt === QI_TT.GEO ? v.tol : null,
	};
}

// Unbounded stand-ins (Minimum only / Maximum only) show as empty, not 999999.
function qi_shown_limit(x) {
	return x == null || Math.abs(x) >= 999999 ? null : x;
}

function qi_accept_text(m, unit, tt) {
	const u = unit ? ` ${qi_esc(unit)}` : "";
	if (unit === "°") return `${m.min_display}° ≤ x ≤ ${m.max_display}°`;
	if ([QI_TT.MAX, QI_TT.GEO].includes(tt) || m.min_display === "—" || m.min_display === "") return `x ≤ ${m.max_display}${u}`;
	if (m.max_display === "—" || m.max_display === "") return `x ≥ ${m.min_display}${u}`;
	return `${m.min_display} ≤ x ≤ ${m.max_display}${u}`;
}

function qi_preview(d, st, frm) {
	const general = frm.doc.custom_general_tolerance;
	if (st.row_type === "Visual") {
		qi_preview_html(d, `<div class="qi-pv"><span>${__("Judged")}</span><b>OK / NG</b></div>`);
		return;
	}
	const v = qi_dev_apply(st, qi_numbers(d.get_values(true)));
	const unit = v.unit || "";
	const bad = qi_bad_numbers(v).filter((f) => !d.fields_dict[f].df.hidden);
	if (bad.length) {
		qi_preview_html(d, `<span class="text-danger">${__("Not a number")}: ${bad.map((f) => qi_esc(d.fields_dict[f].df.label)).join(", ")}</span>`);
		return;
	}
	const callout = qi_callout(st, v);
	const drawing = `<div class="qi-pv"><span>${__("As specified")}</span><b>${
		callout ? qi_esc(callout) + (unit && ![QI_TT.ANG, QI_TT.GEO].includes(st.tt) ? " " + qi_esc(unit) : "") : "…"
	}</b></div>`;
	if (st.tt === QI_TT.GEN && (!general || general === "None")) {
		qi_preview_html(d, `${drawing}<div class="qi-pv"><span>${__("Acceptance range")}</span><span class="text-warning">${__(
			"Choose the drawing's general tolerance (ISO 2768-1) above."
		)}</span></div>`);
		return;
	}
	frappe
		.call({ method: `${QI_API}.compute_limits`, args: { ...qi_limit_args(st, v), general } })
		.then(({ message: m }) => {
			if (m.error) {
				const msg = callout ? qi_esc(m.error) : __("fill in the boxes on the left");
				qi_preview_html(d, `${drawing}<div class="qi-pv"><span>${__("Acceptance range")}</span><span class="text-muted">${msg}</span></div>`);
				return;
			}
			const accept = m.inspected ? qi_accept_text(m, st.tt === QI_TT.ANG ? "°" : unit, st.tt) : __("not inspected (reference only)");
			qi_preview_html(d, `${drawing}<div class="qi-pv ok"><span>${__("Acceptance range")}</span><b>${accept}</b></div>`);
		});
}

// --------------------------------------------------------- drawing picker --

// The item's drawings, each one viewable before it is chosen. Without an Item,
// straight to upload.
function qi_pick_drawing(frm) {
	if (frm.is_new()) {
		frappe.msgprint(__("Give the plan a name and save it first."));
		return;
	}
	const upload = () =>
		new frappe.ui.FileUploader({
			doctype: frm.doctype,
			docname: frm.doc.name,
			fieldname: "custom_drawing",
			allow_multiple: false,
			make_attachments_public: true, // files on this site are public
			restrictions: { allowed_file_types: [".pdf", ".png", ".jpg", ".jpeg"] },
			on_success: (file) => qi_use_drawing(frm, file.name),
		});
	if (!frm.doc.custom_item) return upload();
	frappe.call({ method: `${QI}.drawing_options`, args: { item: frm.doc.custom_item } }).then(async ({ message: files }) => {
		files = files || [];
		await frappe.require("/assets/iso_compliance/js/qi_pdf.js");
		let picker = null;
		const d = new frappe.ui.Dialog({
			title: __("Choose the drawing"),
			size: "extra-large",
			fields: [{ fieldname: "list", fieldtype: "HTML" }],
			primary_action_label: __("Use this drawing"),
			primary_action: () => {
				const chosen = picker && picker.chosen();
				if (!chosen) return frappe.show_alert(__("Click a drawing to look at it first."));
				d.hide();
				qi_use_drawing(frm, chosen);
			},
			secondary_action_label: __("Upload new drawing"),
			secondary_action: () => {
				d.hide();
				upload();
			},
		});
		d.onhide = () => picker && picker.close();
		d.show();
		const $w = d.fields_dict.list.$wrapper;
		if (files.length) picker = window.iso_qi_pdf.chooser($w, files, { current: frm.doc.custom_drawing_file, bom: frm.doc.custom_bom, item: frm.doc.custom_item });
		else $w.html(`<div class="text-muted">${__("No PDF or image is attached to {0}'s BOMs or Item. Upload one.", [qi_esc(frm.doc.custom_item)])}</div>`);
	});
}

function qi_use_drawing(frm, file) {
	// a file not on the BOM (picked from the Item, or just uploaded) still has to be a choice
	const opts = frm.fields_dict.custom_drawing_file.df.options || [];
	if (Array.isArray(opts) && !opts.some((o) => o.value === file)) {
		frm.set_df_property("custom_drawing_file", "options", opts.concat([{ label: file, value: file }]));
	}
	frm.set_value("custom_drawing_file", file);
}

// ---------------------------------------------------------------- tagging --

function qi_tag_dialog(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the template first."));
		return;
	}
	frappe.call({ method: `${QI}.tagging_options`, args: { template: frm.doc.name } }).then(({ message: o }) => {
		if (!o.item) {
			frappe.msgprint(__("Set the Item on the template first."));
			return;
		}
		const fields = [
			{
				fieldtype: "HTML",
				options: `<p class="text-muted small">${__(
					"Inspections started from a ticked BOM use this template. The Item is tagged only when all its active BOMs use this template (or it has none), so an item group default isn't replaced on items with several drawings."
				)}</p>`,
			},
		];
		o.boms.forEach((b, i) =>
			fields.push({
				fieldname: "bom_" + i,
				fieldtype: "Check",
				label: `${b.name}${b.is_default ? " · " + __("default") : ""}${
					b.quality_inspection_template ? " — " + __("now: {0}", [b.quality_inspection_template]) : ""
				}`,
				default: b.quality_inspection_template === frm.doc.name || (b.is_default && !b.quality_inspection_template) ? 1 : 0,
			})
		);
		if (!o.boms.length) fields.push({ fieldtype: "HTML", options: `<p>${__("{0} has no active BOM.", [qi_esc(o.item)])}</p>` });
		fields.push({
			fieldname: "item",
			fieldtype: "Check",
			label: __("Item {0}", [o.item]) + (o.item_template ? " — " + __("now: {0}", [o.item_template]) : ""),
			default: o.item_template === frm.doc.name || (!o.boms.length && !o.item_template) ? 1 : 0,
		});
		const d = new frappe.ui.Dialog({
			title: __("Tag Items / BOMs"),
			fields,
			primary_action_label: __("Tag"),
			primary_action: (v) => {
				const boms = o.boms.filter((b, i) => v["bom_" + i]).map((b) => b.name);
				const args = { template: frm.doc.name, boms, item: v.item ? o.item : null };
				const done = (m) => {
					d.hide();
					const msg = [];
					if (m.tagged && m.tagged.length) msg.push(__("Tagged: {0}", [m.tagged.map((t) => `${t.doctype} ${t.name}`).join(", ")]));
					else msg.push(__("Nothing to change."));
					if (m.skipped_item)
						msg.push(__("Item {0} left as it is: not all of its active BOMs use this template.", [m.skipped_item]));
					frappe.msgprint(msg.join("<br>"));
					frm.__qi_builder && frm.__qi_builder.render_used_by();
				};
				frappe.call({ method: `${QI}.tag_template`, args }).then(({ message: m }) => {
					if (!m.conflicts || !m.conflicts.length) return done(m);
					frappe.confirm(
						__("These already use another template:") +
							"<ul>" +
							m.conflicts.map((c) => `<li>${qi_esc(c.doctype)} ${qi_esc(c.name)}: ${qi_esc(c.current)}</li>`).join("") +
							"</ul>" +
							__("Replace it with this template?"),
						() => frappe.call({ method: `${QI}.tag_template`, args: { ...args, overwrite: 1 } }).then(({ message }) => done(message))
					);
				});
			},
		});
		d.show();
	});
}

// -------------------------------------------------------------- revisions --

function qi_new_revision(frm) {
	frappe.prompt(
		[{ fieldname: "revision", fieldtype: "Data", label: __("New drawing revision"), reqd: 1 }],
		(v) =>
			frappe
				.call({ method: `${QI}.new_revision`, args: { template: frm.doc.name, revision: v.revision }, freeze: true })
				.then(({ message }) => {
					frappe.show_alert(__("Revision created. Pick its drawing, check the numbers, then move the BOMs over."));
					frappe.set_route("Form", "Quality Inspection Template", message);
				}),
		__("New Revision"),
		__("Create")
	);
}

// A variant of this plan (same drawing), copied untagged: the Items and BOMs on
// the original keep loading the original until the copy is tagged on them.
function qi_duplicate(frm) {
	frappe.prompt(
		[{ fieldname: "name", fieldtype: "Data", label: __("Name of the copy"), reqd: 1, default: __("{0} (copy)", [frm.doc.name]).slice(0, 140) }],
		(v) =>
			frappe
				.call({ method: `${QI}.duplicate`, args: { template: frm.doc.name, name: v.name }, freeze: true })
				.then(({ message }) => {
					frappe.show_alert(__("Copy created. Change what differs, then Tag Items / BOMs."));
					frappe.set_route("Form", "Quality Inspection Template", message);
				}),
		__("Duplicate"),
		__("Create")
	);
}

function qi_move_dialog(frm, old) {
	const fields = old.boms.map((b, i) => ({ fieldname: "bom_" + i, fieldtype: "Check", label: "BOM " + b.name, default: 1 }));
	old.items.forEach((it, i) => fields.push({ fieldname: "item_" + i, fieldtype: "Check", label: "Item " + it.name, default: 1 }));
	const d = new frappe.ui.Dialog({
		title: __("Move from {0}", [old.name]),
		fields,
		primary_action_label: __("Move and mark superseded"),
		primary_action: (v) => {
			const boms = old.boms.filter((b, i) => v["bom_" + i]).map((b) => b.name);
			const item = (old.items.find((it, i) => v["item_" + i]) || {}).name || null;
			frappe.call({ method: `${QI}.supersede`, args: { old: old.name, new: frm.doc.name, boms, item }, freeze: true }).then(({ message: m }) => {
				d.hide();
				if (m.skipped_item) frappe.msgprint(__("Item {0} left as it is: not all of its active BOMs use this template.", [m.skipped_item]));
				frm.reload_doc();
			});
		},
	});
	d.show();
}

// ------------------------------------------------------------------ style --

frappe.dom.set_style(`
.qi-builder{padding:4px 15px 18px;border-top:1px solid var(--border-color);display:flex;flex-direction:column;gap:14px}
.qi-col-head{font-size:var(--text-xs);font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--text-muted);margin:4px 0 8px;padding-bottom:4px;border-bottom:1px solid var(--border-color)}
.qi-b-block{border:1px solid var(--border-color);border-radius:10px;padding:12px 14px;background:var(--card-bg)}
.qi-b-block:empty{display:none}
.qi-b-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid var(--border-color)}
.qi-b-title{font-weight:600;font-size:var(--text-base);color:var(--heading-color, var(--text-color))}
.qi-b-nodrawing{padding:6px 0}
.qi-b-used .qi-b-subtitle:first-child{margin-top:0}
.qi-b-status{font-size:var(--text-sm);color:var(--text-muted)}
.qi-b-status.locked{color:var(--orange-600)}
.qi-b-subtitle{font-weight:600;margin:14px 0 6px}
.qi-b-toolbar{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.qi-b-spacer{flex:1}
.qi-b-pages{display:inline-flex;gap:6px;align-items:center}
.qi-b-canvas-wrap{border:1px solid var(--border-color);border-radius:8px;overflow:auto;max-height:75vh;background:var(--gray-50)}
.qi-b-stage{position:relative;margin:0 auto}
.qi-b-stage canvas{display:block}
.qi-b-overlay{position:absolute;inset:0;touch-action:none}
.qi-b-overlay.drawing{cursor:crosshair}
.qi-box{position:absolute;border:2px solid var(--blue-500);background:rgba(45,149,240,.08);border-radius:3px;cursor:pointer}
.qi-box.selected{border-color:var(--orange-500);background:rgba(240,140,40,.15)}
.qi-box.drawing-now{border-style:dashed;pointer-events:none}
.qi-balloon{position:absolute;top:-11px;left:-11px;min-width:22px;height:22px;padding:0 4px;border-radius:11px;background:var(--blue-500);color:#fff;font-size:11px;font-weight:600;display:flex;align-items:center;justify-content:center}
.qi-box.selected .qi-balloon{background:var(--orange-500)}
.qi-balloon.static{position:static;display:inline-flex}
.qi-b-table .table{margin-bottom:0}
.qi-hd{margin:0 0 4px;padding:16px 35px 14px;border-bottom:1px solid var(--border-color);display:flex;flex-direction:column;gap:10px}
.qi-hd-top{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.qi-hd-name{font-size:var(--text-xl);font-weight:600;color:var(--text-color)}
.qi-hd-status{font-size:var(--text-xs);font-weight:600;padding:2px 8px;border-radius:10px}
.qi-hd-status.green{background:var(--green-100);color:var(--green-700)}
.qi-hd-status.orange{background:var(--orange-100);color:var(--orange-700)}
.qi-hd-status.red{background:var(--red-100);color:var(--red-700)}
.qi-hd-pills{display:flex;flex-wrap:wrap;gap:6px}
.qi-hd-used{display:contents}
.qi-hd-pill{display:inline-flex;align-items:baseline;gap:6px;font-size:var(--text-sm);padding:3px 10px;border-radius:8px;background:var(--gray-100);color:var(--text-color)}
.qi-hd-pill>span:first-child{font-size:var(--text-xs);color:var(--text-muted)}
.qi-hd-pill.dim{color:var(--text-muted)}
.qi-hd-pill.warn{background:var(--yellow-50);color:var(--yellow-800)}
.qi-hd-sub{color:var(--text-muted)}
.qi-t{--qi-t-cols:44px minmax(150px,1.5fr) minmax(150px,1.2fr) 196px minmax(110px,.8fr);font-size:var(--text-sm)}
.qi-t-head,.qi-t-row{display:grid;grid-template-columns:var(--qi-t-cols);gap:12px;align-items:start;padding:10px 8px}
.qi-t-head{padding-top:4px;padding-bottom:6px;border-bottom:1px solid var(--border-color);font-size:var(--text-xs);font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--text-muted)}
.qi-t-group{display:flex;align-items:center;gap:6px;padding:14px 8px 6px;font-size:var(--text-xs);font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--text-muted)}
.qi-t-row{border-bottom:1px solid var(--border-color);cursor:pointer;border-radius:6px}
.qi-t-row:hover{background:var(--gray-50)}
.qi-t-row.selected{background:var(--yellow-50)}
.qi-t-name{font-size:var(--text-base);font-weight:600;color:var(--text-color)}
.qi-t-pills{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}
.qi-t-pills:empty{display:none}
.qi-t-pill{display:inline-block;font-size:11px;font-weight:500;line-height:16px;padding:0 6px;border-radius:8px;background:var(--gray-100);color:var(--text-color)}
.qi-t-pill.class-ctq{background:var(--red-100);color:var(--red-700)}
.qi-t-pill.class-major{background:var(--orange-100);color:var(--orange-700)}
.qi-t-pill.warn{background:var(--yellow-100);color:var(--yellow-800)}
.qi-t-main{font-size:var(--text-base);font-weight:600;color:var(--text-color)}
.qi-t-sub{font-size:var(--text-xs);color:var(--text-muted);margin-top:2px}
.qi-t-dim{font-weight:400;color:var(--text-muted)}
.qi-t-stages{display:flex;gap:3px;flex-wrap:nowrap}
.qi-t-stage{font-size:11px;line-height:20px;padding:0 6px;border-radius:6px;border:1px solid var(--border-color);color:var(--gray-400)}
.qi-t-stage.on{background:var(--gray-800);border-color:var(--gray-800);color:#fff}
@media (max-width:767px){
	.qi-t-head{display:none}
	.qi-t-row{grid-template-columns:32px 1fr auto;grid-template-areas:"no what accept" "no stages how";row-gap:8px;padding:12px 4px}
	.qi-t-no{grid-area:no}.qi-t-what{grid-area:what}.qi-t-accept{grid-area:accept;text-align:right}
	.qi-t-stages{grid-area:stages;flex-wrap:wrap}.qi-t-stage:not(.on){display:none}.qi-t-how{grid-area:how;text-align:right}
	.qi-hd{padding-left:15px;padding-right:15px}
}
.grid-row.qi-row-selected .data-row{background:var(--yellow-50)}
.qi-class{font-size:11px;padding:1px 6px;border-radius:8px;background:var(--gray-100)}
.qi-class.ctq{background:var(--red-100);color:var(--red-700)}
.qi-class.major{background:var(--orange-100);color:var(--orange-700)}
.qi-b-add{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
.qi-used-line{padding:3px 0}
.qi-preview{padding:10px 12px;border-radius:8px;background:var(--gray-50);min-height:34px;display:flex;flex-direction:column;gap:6px}
.qi-pv{display:flex;gap:10px;align-items:baseline}
.qi-pv span{min-width:120px;color:var(--text-muted);font-size:var(--text-sm)}
.qi-pv b{font-size:var(--text-lg);font-variant-numeric:tabular-nums}
.qi-pv.ok b{color:var(--green-700)}
.qi-mono{font-variant-numeric:tabular-nums;white-space:nowrap}
.qi-empty{padding:14px;border:1px dashed var(--border-color);border-radius:8px;color:var(--text-muted);text-align:center;margin-top:12px}
.qi-seg{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}
.qi-seg-btn{border:1px solid var(--border-color);background:var(--fg-color);border-radius:8px;padding:6px 12px;display:inline-flex;gap:6px;align-items:center;font-size:var(--text-md)}
.qi-seg-btn.sm{padding:3px 10px;font-size:var(--text-sm);min-width:40px;justify-content:center}
.qi-seg-btn.on{border-color:var(--primary);background:var(--primary);color:var(--white)}
.qi-chips{display:grid;grid-template-columns:repeat(auto-fill,minmax(104px,1fr));gap:5px;margin-bottom:10px}
.qi-chip{border:1px solid var(--border-color);background:var(--fg-color);border-radius:8px;padding:4px 7px;text-align:left;display:flex;flex-direction:column;gap:0}
.qi-chip:hover{border-color:var(--gray-500)}
.qi-chip.on{border-color:var(--primary);box-shadow:0 0 0 1px var(--primary);background:var(--blue-50)}
.qi-chip-sym{font-size:15px;font-weight:600;line-height:1.2}
.qi-dialog .modal-dialog.modal-lg{max-width:720px}
.qi-dialog .modal-content{max-height:calc(100vh - 3.5rem);display:flex;flex-direction:column}
.qi-dialog .modal-body{overflow-y:auto;flex:1 1 auto;min-height:0;padding-top:8px}
.qi-dialog .form-section .section-head{margin-bottom:6px}
.qi-dialog .form-section{padding-top:10px;padding-bottom:4px}
.qi-dialog .frappe-control .help-box{margin-top:2px}
.qi-dp-host{padding:10px var(--padding-md, 15px) 0;flex:none}
.qi-dialog .qi-seg{margin-bottom:0}
.qi-dp{position:relative;min-height:40px}
.qi-dp canvas{display:block;width:100%;height:200px;border:1px solid var(--border-color);border-radius:8px;cursor:grab;touch-action:none;background:#e9e9e9}
.qi-dp-tools{position:absolute;top:6px;right:6px;display:flex;gap:4px}
.qi-dp-tools button{min-width:30px;height:28px;border:1px solid var(--border-color);border-radius:6px;background:var(--fg-color);font-size:var(--text-sm);box-shadow:0 1px 3px rgba(0,0,0,.18)}
.qi-dp-msg{padding:10px 2px}
@media (max-width:640px){.qi-dp canvas{height:150px}}
.qi-dialog .form-section .section-head{font-size:var(--text-sm);font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-muted)}
.qi-dialog .form-section{border-top:1px solid var(--border-color)}
.qi-dialog .form-section:first-child,.qi-dialog .form-section:not(:has(.section-head)){border-top:0}
.qi-when{display:flex;flex-direction:column;gap:12px}
.qi-when-row{display:grid;grid-template-columns:170px 1fr;gap:10px;align-items:center}
.qi-when-label{font-size:var(--text-sm);font-weight:500;color:var(--text-color)}
.qi-when-n{display:inline-flex;gap:6px;align-items:center;margin:0 0 0 6px;font-size:var(--text-sm);color:var(--text-muted)}
.qi-when-n input{width:70px;height:28px}
.qi-tip{display:inline-flex;width:15px;height:15px;border-radius:50%;border:1px solid var(--gray-400);color:var(--gray-600);font-size:10px;font-style:italic;font-weight:600;align-items:center;justify-content:center;cursor:help;margin-left:4px}
.qi-pill.check.on{background:var(--primary);border-color:var(--primary)}
.qi-inst-tabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.qi-badge{display:inline-block;margin-left:4px;padding:0 6px;border-radius:8px;background:rgba(0,0,0,.08);font-size:11px}
.qi-pill.on .qi-badge{background:rgba(255,255,255,.25)}
.qi-inst-same{display:flex;gap:6px;align-items:center;font-size:var(--text-sm);margin:0 0 8px}
.qi-inst-search{max-width:280px}
.qi-inst.off{opacity:.5}
@media (max-width:640px){.qi-when-row{grid-template-columns:1fr}}
.qi-pills{display:flex;gap:6px;flex-wrap:wrap}
.qi-pill{border:1px solid var(--border-color);background:var(--fg-color);border-radius:999px;padding:4px 14px;font-size:var(--text-sm);font-weight:500}
.qi-pill.on{background:var(--gray-700);border-color:var(--gray-700);color:var(--white)}
.qi-pill.ctq.on{background:var(--red-600);border-color:var(--red-600)}
.qi-pill.major.on{background:var(--orange-500);border-color:var(--orange-500)}
.qi-gen{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;padding:6px 10px;margin-bottom:10px;border-radius:8px;background:var(--gray-50)}
.qi-gen.warn{background:var(--yellow-50);box-shadow:inset 0 0 0 1px var(--yellow-300)}
.qi-gen-title{font-weight:600;font-size:var(--text-sm)}
.qi-gen-item{display:inline-flex;gap:6px;align-items:center;margin:0;font-size:var(--text-sm);color:var(--text-muted)}
.qi-gen-item select{width:auto;height:26px;padding:0 6px}
.qi-gen .small{flex-basis:100%}
.qi-legacy td{font-variant-numeric:tabular-nums}
.qi-chip-name{font-size:var(--text-sm);font-weight:500}
.qi-chip-ex{font-size:11px;color:var(--text-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.qi-prefix{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
.qi-prefix .text-muted{margin-right:4px}
.qi-inst-head{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;margin-bottom:6px}
.qi-inst-head .text-muted{flex:1}
.qi-inst{display:flex;flex-direction:column;gap:6px;max-height:300px;overflow:auto}
.qi-inst-grp{display:flex;gap:10px;align-items:flex-start;padding:6px 0;border-bottom:1px solid var(--border-color)}
.qi-inst-type{min-width:210px;font-weight:500;margin:0;display:flex;gap:6px;align-items:center}
.qi-inst-assets{display:flex;flex-wrap:wrap;gap:4px}
.qi-inst-asset{border:1px solid var(--border-color);border-radius:12px;padding:1px 8px;font-size:var(--text-sm);margin:0;display:inline-flex;gap:4px;align-items:center;cursor:pointer}
.qi-inst-asset.on{background:var(--blue-50);border-color:var(--blue-300)}
@media (max-width:640px){.qi-inst-grp{flex-direction:column}.qi-inst-type{min-width:0}}
`);
