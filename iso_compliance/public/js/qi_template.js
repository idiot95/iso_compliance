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
		// drawing templates are edited through the table under the drawing, not the raw grid
		frm.set_df_property(QI_ROWS, "hidden", frm.doc.custom_item || qi_is_drawing(frm) ? 1 : 0);
		const builder = qi_builder(frm);
		builder.render();
		qi_drawing_options(frm);
		qi_tag_prompt(frm);
		if (frm.is_new() || !qi_can_edit()) return;
		if (frm.doc.custom_item || qi_is_drawing(frm)) {
			frm.add_custom_button(__("Tag Items / BOMs"), () => qi_tag_dialog(frm));
			frm.add_custom_button(__("New Revision"), () => qi_new_revision(frm));
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
		? __("Choosing one attaches it to the template.")
		: bom ? __("{0} has no PDF or image attached. Upload one in the drawing panel below.", [bom]) : "");
	frm.refresh_field("custom_drawing_file");
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
		if (this.frm.is_new()) {
			$p.html(`<div class="text-muted small" style="padding:12px 15px">${__(
				"Choose the Item, then its BOM, then the drawing on that BOM: the drawing opens here."
			)}</div>`);
			return;
		}
		if (!d.custom_item && !qi_is_drawing(this.frm)) {
			$p.html(`<div class="text-muted small" style="padding:12px 15px">${__(
				"To make this a drawing template, set the Item above. Templates without drawing rows behave exactly as before."
			)}</div>`);
			this.render_used_by();
			return;
		}
		const locked = !!d.custom_locked;
		const editable = qi_can_edit() && !locked;
		$p.html(`
			<div class="qi-b-head">
				<div class="qi-b-title">${__("Drawing and characteristics")}</div>
				<div class="qi-b-status ${locked ? "locked" : ""}">${
					locked ? __("Locked · inspections submitted; change through New Revision") : __("Editable · not used yet")
				}</div>
			</div>
			<div class="qi-b-banner"></div>
			<div class="qi-b-toolbar">
				${editable ? `<button class="btn btn-xs btn-default qi-pick">${__("Other drawing / upload")}</button>` : ""}
				${editable && d.custom_drawing ? `<button class="btn btn-xs qi-mode ${this.mode === "draw" ? "btn-primary" : "btn-default"}" data-mode="draw">▭ ${__("Draw balloon")}</button>` : ""}
				<span class="qi-b-hint text-muted small">${
					d.custom_drawing ? (editable ? __("Select a row or draw a box: the balloon goes where you draw.") : "") : __("No drawing yet.")
				}</span>
				<span class="qi-b-spacer"></span>
				<span class="qi-b-pages small"></span>
				<button class="btn btn-xs btn-default qi-zoom" data-z="-1">−</button>
				<span class="small qi-zoom-val">${Math.round(this.zoom * 100)}%</span>
				<button class="btn btn-xs btn-default qi-zoom" data-z="1">+</button>
			</div>
			<div class="qi-b-canvas-wrap"><div class="qi-b-stage"><canvas></canvas><div class="qi-b-overlay"></div></div></div>
			<div class="qi-b-add">
				${editable ? `<button class="btn btn-xs btn-default qi-add" data-type="Dimension">+ ${__("Dimension")}</button>
				<button class="btn btn-xs btn-default qi-add" data-type="Test">+ ${__("Test (from Test Method)")}</button>
				<button class="btn btn-xs btn-default qi-add" data-type="Visual">+ ${__("Visual check")}</button>
				<button class="btn btn-xs btn-default qi-add" data-type="Material">+ ${__("Material (supplier 3.1)")}</button>` : ""}
			</div>
			<div class="qi-b-table"></div>
			<div class="qi-b-used"></div>
		`);
		this.bind();
		this.render_table();
		this.render_used_by();
		this.render_banner();
		this.load_drawing();
	}

	bind() {
		const $p = this.$panel;
		$p.find(".qi-pick").on("click", () => qi_pick_drawing(this.frm));
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
				await frappe.require("/assets/iso_compliance/js/qi_pdf.js");
				if (this.drawing) this.drawing.close();
				this.drawing = await window.iso_qi_pdf.open(url);
				this.drawing_url = url;
				this.page = 1;
			}
			await this.draw_page();
			this.ensure_page_images();
		} catch (e) {
			console.error(e);
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

	render_table() {
		const rows = (this.doc[QI_ROWS] || []).filter((r) => r.custom_row_type);
		const $t = this.$panel.find(".qi-b-table");
		if (!rows.length) {
			$t.html(`<div class="qi-empty">${__("No characteristics yet. Draw a box round a dimension on the drawing, or use the buttons above.")}</div>`);
			return;
		}
		const stages = (r) =>
			QI_STAGES.filter(([f]) => r[f])
				.map(([, l]) => l)
				.join(", ");
		const how = (r) =>
			[
				r.custom_sampling === "Fixed number" ? __("{0} pcs", [r.custom_fixed_count || "?"]) : __("lot sample"),
				r.custom_frequency && r.custom_frequency !== "Every lot" ? r.custom_frequency.replace(" N ", ` ${r.custom_frequency_n || "N"} `) : "",
			]
				.filter(Boolean)
				.join(" · ");
		const inst = (r) => {
			const n = (r.custom_instruments || "").split("\n").filter(Boolean).length;
			return n ? __("{0} chosen", [n]) : r.custom_row_type === "Visual" ? "" : `<span class="text-muted">${__("any")}</span>`;
		};
		$t.html(`<div class="qi-b-subtitle">${__("Characteristics")} <span class="text-muted small">${__("click a row to change it")}</span></div>
			<table class="table table-sm qi-rows">
			<thead><tr><th>${__("Balloon")}</th><th>${__("What is checked")}</th><th>${__("On the drawing")}</th>
			<th>${__("Accept")}</th><th>${__("Importance")}</th><th>${__("Stages")}</th><th>${__("Pieces")}</th><th>${__("Instruments")}</th></tr></thead>
			<tbody>${rows
				.map(
					(r) => `<tr data-row="${r.name}" class="${this.selected === r.name ? "selected" : ""}">
				<td><span class="qi-balloon static">${qi_esc(r.custom_balloon_no || "")}</span>${
						r.custom_row_type === "Dimension" && !qi_pos(r) ? ` <span class="text-warning" title="${__("No box on the drawing")}">◌</span>` : ""
					}</td>
				<td>${qi_esc(r.specification)}<div class="text-muted small">${qi_esc(__(r.custom_row_type))}${r.custom_test_method ? " · " + qi_esc(r.custom_test_method) : ""}</div></td>
				<td class="qi-mono">${qi_esc(r.custom_spec_text || "")}${
					r.custom_spec_text && r.custom_unit && r.custom_unit !== "°" && r.custom_tolerance_type !== "Geometric (GD&T)" ? " " + qi_esc(r.custom_unit) : ""
				}</td>
				<td class="qi-mono">${qi_esc(qi_limit_text(r))}</td>
				<td>${r.custom_class ? `<span class="qi-class ${r.custom_class.toLowerCase()}">${qi_esc(r.custom_class)}</span>` : ""}</td>
				<td class="small">${qi_esc(stages(r))}</td>
				<td class="small">${qi_esc(how(r))}</td>
				<td class="small">${inst(r)}</td>
			</tr>`
				)
				.join("")}</tbody></table>`);
		$t.find("tr[data-row]").on("click", (e) => {
			const name = $(e.currentTarget).data("row");
			this.select(name);
			if (qi_can_edit() && !this.doc.custom_locked) qi_balloon_dialog(this.frm, locals["Item Quality Inspection Parameter"][name]);
		});
	}

	render_used_by() {
		const $u = this.$panel.find(".qi-b-used");
		if (this.frm.is_new()) return;
		frappe.call({ method: `${QI}.used_by`, args: { template: this.doc.name } }).then(({ message: m }) => {
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
			}<div class="text-muted small" style="margin-top:6px">${__(
				"Once an inspection is submitted against this template, drawing, balloons and limits lock; changes go through New Revision."
			)}</div>`);
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
const QI_ROW_TYPES = [
	["Dimension", "⌀", __("Dimension")],
	["Test", "⚗", __("Test")],
	["Visual", "👁", __("Visual")],
	["Material", "▤", __("Material (3.1)")],
];
const QI_DIALOG_STAGES = QI_STAGES.filter(([f]) => !["custom_stage_fai", "custom_stage_type_test"].includes(f)); // Phase F later

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

function qi_balloon_dialog(frm, row, defaults = {}, on_cancel) {
	const r = row || {};
	const general = frm.doc.custom_general_tolerance;
	const st = {
		row_type: r.custom_row_type || defaults.row_type || "Dimension",
		tt: r.custom_tolerance_type || "",
		prefix: qi_prefix_of(r.custom_spec_text),
		instruments: new Set((r.custom_instruments || "").split("\n").map((x) => x.trim()).filter(Boolean)),
	};
	if (!st.tt && st.row_type !== "Visual") st.tt = st.row_type === "Dimension" ? QI_TT.SYM : QI_TT.LIM;
	const new_stage = (f) => (st.row_type === "Material" ? f === "custom_stage_incoming" : f === "custom_stage_final") ? 1 : 0;

	const d = new frappe.ui.Dialog({
		title: row ? __("Balloon {0}", [r.custom_balloon_no]) : __("New characteristic"),
		size: "extra-large",
		fields: [
			{ fieldname: "type_html", fieldtype: "HTML" },
			{
				fieldname: "specification",
				fieldtype: "Link",
				options: "Quality Inspection Parameter",
				label: __("What is checked"),
				reqd: 1,
				default: r.specification,
				description: __("e.g. Width, Length, Hardness, Shunt length"),
			},
			{ fieldname: "test_method", fieldtype: "Link", options: "Test Method", label: __("Test method"), default: r.custom_test_method, hidden: 1 },
			{ fieldtype: "Column Break" },
			{ fieldname: "balloon_no", fieldtype: "Data", label: __("Balloon no."), default: r.custom_balloon_no, description: __("Leave blank for the next number") },
			{
				fieldname: "class",
				fieldtype: "Select",
				label: __("Importance"),
				options: [
					{ value: "CTQ", label: __("CTQ · critical to quality") },
					{ value: "Major", label: __("Major") },
					{ value: "Minor", label: __("Minor") },
				],
				default: r.custom_class || "Major",
			},

			{ fieldtype: "Section Break", fieldname: "tol_section", label: __("Tolerance, as shown on the drawing") },
			{ fieldname: "tt_html", fieldtype: "HTML" },
			{ fieldname: "prefix_html", fieldtype: "HTML" },
			{ fieldtype: "Section Break", fieldname: "tol_inputs" },
			{ fieldname: "nominal", fieldtype: "Data", label: __("Nominal"), default: qi_num(r.custom_nominal) },
			{ fieldname: "tol", fieldtype: "Data", label: __("± Tolerance"), default: qi_num(r.custom_tol) },
			{ fieldname: "upper_dev", fieldtype: "Data", label: __("+ Upper deviation"), default: qi_num(r.custom_upper_dev), description: __("As printed, e.g. +0.1") },
			{ fieldname: "lower_dev", fieldtype: "Data", label: __("− Lower deviation"), default: qi_num(r.custom_lower_dev), description: __("As printed, with its sign, e.g. −0.05") },
			{ fieldname: "fit_class", fieldtype: "Data", label: __("Fit class"), default: r.custom_fit_class, description: __("e.g. H7, h9, js7") },
			{
				fieldname: "gdt_symbol",
				fieldtype: "Select",
				label: __("Geometric characteristic"),
				options: Object.entries(QI_GDT).map(([value, sym]) => ({ value, label: `${sym}  ${__(value)}` })),
				default: r.custom_gdt_symbol || "Position",
			},
			{ fieldname: "datums", fieldtype: "Data", label: __("Datums"), default: r.custom_datums, description: __("e.g. A B") },
			{ fieldname: "lower", fieldtype: "Data", label: __("Min (≥)"), default: qi_num(qi_shown_limit(r.min_value)) },
			{ fieldname: "upper", fieldtype: "Data", label: __("Max (≤)"), default: qi_num(qi_shown_limit(r.max_value)) },
			{
				fieldname: "angle_side",
				fieldtype: "Data",
				label: __("Shorter side of the angle (mm)"),
				hidden: 1,
				description: __("ISO 2768 angular tolerance depends on it."),
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "unit",
				fieldtype: "Link",
				options: "UOM",
				label: __("Unit"),
				default: r.custom_unit || (st.row_type === "Dimension" ? "mm" : ""),
			},
			{ fieldname: "limits_preview", fieldtype: "HTML" },

			{ fieldtype: "Section Break", label: __("When and how many") },
			...QI_DIALOG_STAGES.map(([f, label]) => ({ fieldname: f, fieldtype: "Check", label, default: row ? r[f] : new_stage(f) })),
			{
				fieldname: "in_process_at",
				fieldtype: "Select",
				label: __("In process, check at"),
				options: "Every check\nFirst-off only\nFirst-off and last-off",
				default: r.custom_in_process_at || "Every check",
				depends_on: "custom_stage_in_process",
			},
			{ fieldtype: "Column Break" },
			{ fieldname: "frequency", fieldtype: "Select", label: __("How often"), options: "Every lot\nFirst article only\nEvery N lots\nEvery N months", default: r.custom_frequency || "Every lot" },
			{ fieldname: "frequency_n", fieldtype: "Int", label: "N", default: r.custom_frequency_n, depends_on: 'eval:["Every N lots","Every N months"].includes(doc.frequency)' },
			{ fieldname: "sampling", fieldtype: "Select", label: __("Pieces to check"), options: [
				{ value: "Lot sample", label: __("Sample size of the lot") },
				{ value: "Fixed number", label: __("A fixed number") },
			], default: r.custom_sampling || "Lot sample" },
			{ fieldname: "fixed_count", fieldtype: "Int", label: __("How many pieces"), default: r.custom_fixed_count, depends_on: 'eval:doc.sampling=="Fixed number"' },

			{ fieldtype: "Section Break", fieldname: "inst_section", label: __("Instruments the inspector can use") },
			{ fieldname: "inst_html", fieldtype: "HTML" },
		],
		primary_action_label: row ? __("Save") : __("Add"),
		primary_action: (v) => qi_save_balloon(frm, row, v, defaults.position, d, st),
		secondary_action_label: row ? __("Delete") : null,
		secondary_action: row
			? () =>
					frappe.confirm(__("Delete balloon {0}?", [r.custom_balloon_no]), () => {
						frm.get_field(QI_ROWS).grid.grid_rows_by_docname[row.name].remove();
						d.hide();
						frm.save();
					})
			: null,
	});
	d.$wrapper.addClass("qi-dialog");

	const preview = frappe.utils.debounce(() => qi_preview(d, st, general), 200);
	const refresh = () => {
		qi_render_type(d, st, refresh);
		qi_render_tt(d, st, refresh);
		qi_render_prefix(d, st, refresh);
		qi_show_fields(d, st);
		preview();
	};
	[...QI_TOL_FIELDS, "unit"].forEach((f) => (d.fields_dict[f].df.onchange = f === "unit" ? refresh : preview));
	d.fields_dict.test_method.df.onchange = () => qi_from_test_method(d, st);
	qi_render_instruments(d, st);
	d.onhide = () => on_cancel && !d.__saved && on_cancel();
	d.show();
	refresh();
}

function qi_render_type(d, st, refresh) {
	const $w = d.fields_dict.type_html.$wrapper;
	$w.html(`<div class="qi-seg">${QI_ROW_TYPES.map(
		([v, icon, label]) => `<button type="button" class="qi-seg-btn ${st.row_type === v ? "on" : ""}" data-v="${v}"><span>${icon}</span>${qi_esc(label)}</button>`
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

function qi_show_fields(d, st) {
	const need = new Set(st.row_type === "Visual" ? [] : QI_TT_FIELDS[st.tt] || []);
	if (st.tt === QI_TT.GEN && d.get_value("unit") === "°") need.add("angle_side");
	QI_TOL_FIELDS.forEach((f) => d.set_df_property(f, "hidden", need.has(f) ? 0 : 1));
	d.set_df_property("tol", "label", st.tt === QI_TT.GEO ? __("Tolerance zone") : st.tt === QI_TT.ANG ? __("± Tolerance (°)") : __("± Tolerance"));
	d.set_df_property("nominal", "label", st.tt === QI_TT.ANG ? __("Nominal angle (°)") : __("Nominal"));
	const visual = st.row_type === "Visual";
	d.set_df_property("tol_section", "hidden", visual ? 1 : 0);
	d.set_df_property("tol_inputs", "hidden", visual ? 1 : 0);
	d.set_df_property("unit", "hidden", visual ? 1 : 0);
	d.set_df_property("inst_section", "hidden", visual ? 1 : 0);
	d.set_df_property("test_method", "hidden", st.row_type === "Test" ? 0 : 1);
	d.set_df_property("test_method", "reqd", st.row_type === "Test" ? 1 : 0);
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

function qi_preview(d, st, general) {
	if (st.row_type === "Visual") {
		qi_preview_html(d, `<div class="qi-pv"><span>${__("Judged")}</span><b>OK / NG</b></div>`);
		return;
	}
	const v = qi_numbers(d.get_values(true));
	const unit = v.unit || "";
	const bad = qi_bad_numbers(v).filter((f) => !d.fields_dict[f].df.hidden);
	if (bad.length) {
		qi_preview_html(d, `<span class="text-danger">${__("Not a number")}: ${bad.map((f) => qi_esc(d.fields_dict[f].df.label)).join(", ")}</span>`);
		return;
	}
	const callout = qi_callout(st, v);
	const drawing = `<div class="qi-pv"><span>${__("On the drawing")}</span><b>${
		callout ? qi_esc(callout) + (unit && ![QI_TT.ANG, QI_TT.GEO].includes(st.tt) ? " " + qi_esc(unit) : "") : "…"
	}</b></div>`;
	if (st.tt === QI_TT.GEN && (!general || general === "None")) {
		qi_preview_html(d, `${drawing}<div class="qi-pv"><span>${__("Accept")}</span><span class="text-warning">${__(
			"Set the drawing's General tolerance (ISO 2768-1) at the top of the template first."
		)}</span></div>`);
		return;
	}
	frappe
		.call({ method: `${QI_API}.compute_limits`, args: { ...qi_limit_args(st, v), general } })
		.then(({ message: m }) => {
			if (m.error) {
				const msg = callout ? qi_esc(m.error) : __("fill in the boxes on the left");
				qi_preview_html(d, `${drawing}<div class="qi-pv"><span>${__("Accept")}</span><span class="text-muted">${msg}</span></div>`);
				return;
			}
			const accept = m.inspected ? qi_accept_text(m, st.tt === QI_TT.ANG ? "°" : unit, st.tt) : __("not inspected (reference only)");
			qi_preview_html(d, `${drawing}<div class="qi-pv ok"><span>${__("Accept")}</span><b>${accept}</b></div>`);
		});
}

// A Test row takes its unit and instruments from the Test Method.
async function qi_from_test_method(d, st) {
	const tm = d.get_value("test_method");
	if (!tm) return;
	const doc = await frappe.db.get_doc("Test Method", tm);
	if (doc.result_unit && !d.get_value("unit")) d.set_value("unit", doc.result_unit);
	if (!st.instruments.size && (doc.instruments || []).length) {
		const items = doc.instruments.map((i) => i.instrument_item);
		(await qi_instruments()).filter((a) => items.includes(a.item_code)).forEach((a) => st.instruments.add(a.name));
		qi_render_instruments(d, st);
	}
}

async function qi_render_instruments(d, st) {
	const $w = d.fields_dict.inst_html.$wrapper;
	const all = await qi_instruments();
	const groups = {};
	all.forEach((a) => (groups[a.item_name] = groups[a.item_name] || []).push(a));
	const short = (a) => (a.asset_name || a.name).replace(a.item_name, "").trim() || a.name;
	const draw = () => {
		const n = st.instruments.size;
		$w.html(`<div class="qi-inst-head">
				<span class="text-muted small">${
					n ? __("{0} ticked: the inspector chooses one of these.", [n]) : __("None ticked: the inspector can choose any measuring instrument.")
				}</span>
				<a class="qi-inst-all small">${__("Tick all")}</a> · <a class="qi-inst-none small">${__("Clear")}</a>
			</div>
			<div class="qi-inst">${Object.entries(groups)
				.map(([name, assets]) => {
					const on = assets.filter((a) => st.instruments.has(a.name)).length;
					return `<div class="qi-inst-grp">
						<label class="qi-inst-type"><input type="checkbox" data-grp="${qi_esc(name)}" ${on === assets.length ? "checked" : ""} ${
							on && on < assets.length ? 'data-partial="1"' : ""
						}> ${qi_esc(name)} <span class="text-muted">(${assets.length})</span></label>
						<div class="qi-inst-assets">${assets
							.map(
								(a) => `<label class="qi-inst-asset ${st.instruments.has(a.name) ? "on" : ""}" title="${qi_esc(a.name)}">
									<input type="checkbox" data-asset="${qi_esc(a.name)}" ${st.instruments.has(a.name) ? "checked" : ""}> ${qi_esc(short(a))}</label>`
							)
							.join("")}</div></div>`;
				})
				.join("")}</div>`);
		$w.find("[data-partial]").prop("indeterminate", true);
		$w.find("input[data-grp]").on("change", (e) => {
			const assets = groups[$(e.currentTarget).data("grp")];
			const tick = e.currentTarget.checked;
			assets.forEach((a) => (tick ? st.instruments.add(a.name) : st.instruments.delete(a.name)));
			draw();
		});
		$w.find("input[data-asset]").on("change", (e) => {
			const name = $(e.currentTarget).data("asset");
			e.currentTarget.checked ? st.instruments.add(name) : st.instruments.delete(name);
			draw();
		});
		$w.find(".qi-inst-all").on("click", () => {
			all.forEach((a) => st.instruments.add(a.name));
			draw();
		});
		$w.find(".qi-inst-none").on("click", () => {
			st.instruments.clear();
			draw();
		});
	};
	draw();
}

async function qi_save_balloon(frm, row, v, position, dialog, st) {
	v = qi_numbers(v);
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
	if (!QI_DIALOG_STAGES.some(([f]) => v[f]) && !(row && (row.custom_stage_fai || row.custom_stage_type_test))) {
		frappe.msgprint(__("Tick at least one stage."));
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
		custom_unit: visual ? "" : v.unit,
		custom_class: v.class,
		custom_spec_text: visual ? "" : qi_callout({ ...st, tt: st.tt }, v),
		custom_tolerance_type: tolerance_type,
		custom_nominal: keep("nominal", v.nominal),
		custom_tol: tolerance_type === QI_TT.ANG ? tol : keep("tol", tol),
		custom_upper_dev: keep("upper_dev", v.upper_dev),
		custom_lower_dev: keep("lower_dev", v.lower_dev),
		custom_fit_class: keep("fit_class", v.fit_class),
		custom_gdt_symbol: keep("gdt_symbol", v.gdt_symbol),
		custom_datums: keep("datums", v.datums),
		custom_frequency: v.frequency,
		custom_frequency_n: v.frequency_n,
		custom_sampling: v.sampling,
		custom_fixed_count: v.fixed_count,
		custom_instruments: visual ? null : [...st.instruments].join("\n") || null,
		custom_in_process_at: v.in_process_at || "Every check",
	};
	if ([QI_TT.LIM, QI_TT.MIN].includes(tolerance_type)) values.min_value = v.lower;
	if ([QI_TT.LIM, QI_TT.MAX].includes(tolerance_type)) values.max_value = v.upper;
	QI_DIALOG_STAGES.forEach(([f]) => (values[f] = v[f] ? 1 : 0));
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

// --------------------------------------------------------- drawing picker --

function qi_pick_drawing(frm) {
	if (!frm.doc.custom_item) {
		frappe.msgprint(__("Set the Item first: drawings are listed from its BOMs."));
		return;
	}
	frappe.call({ method: `${QI}.drawing_options`, args: { item: frm.doc.custom_item } }).then(({ message: files }) => {
		const d = new frappe.ui.Dialog({
			title: __("Pick drawing"),
			size: "large",
			fields: [{ fieldname: "list", fieldtype: "HTML" }],
			primary_action_label: __("Upload new drawing"),
			primary_action: () => {
				d.hide();
				new frappe.ui.FileUploader({
					doctype: frm.doctype,
					docname: frm.doc.name,
					fieldname: "custom_drawing",
					allow_multiple: false,
					make_attachments_public: true, // files on this site are public
					restrictions: { allowed_file_types: [".pdf", ".png", ".jpg", ".jpeg"] },
					on_success: (file) => qi_use_drawing(frm, file.name),
				});
			},
		});
		const rows = (files || [])
			.map(
				(f) => `<tr><td><a href="${qi_esc(f.file_url)}" target="_blank">${qi_esc(f.file_name)}</a></td>
				<td class="text-muted">${qi_esc(f.attached_to_doctype)} ${qi_esc(f.attached_to_name)}${f.bom_default ? " · " + __("default") : ""}${
					f.attached_to_doctype === "BOM" && !f.bom_active ? " · " + __("inactive") : ""
				}</td>
				<td><button class="btn btn-xs btn-primary" data-file="${qi_esc(f.name)}">${__("Use")}</button></td></tr>`
			)
			.join("");
		d.fields_dict.list.$wrapper.html(
			files && files.length
				? `<table class="table table-sm"><tbody>${rows}</tbody></table>`
				: `<div class="text-muted">${__("No PDF or image is attached to {0}'s BOMs or Item. Upload one.", [qi_esc(frm.doc.custom_item)])}</div>`
		);
		d.fields_dict.list.$wrapper.find("button[data-file]").on("click", (e) => {
			d.hide();
			qi_use_drawing(frm, $(e.currentTarget).data("file"));
		});
		d.show();
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
					frappe.show_alert(__("Revision created. Pick its drawing, check the balloons, then move the BOMs over."));
					frappe.set_route("Form", "Quality Inspection Template", message);
				}),
		__("New Revision"),
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
.qi-builder{padding:12px 15px 18px;border-top:1px solid var(--border-color)}
.qi-b-head{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:8px}
.qi-b-title{font-weight:600;font-size:var(--text-lg)}
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
.qi-b-table{margin-top:12px;overflow-x:auto}
.qi-rows tr[data-row]{cursor:pointer}
.qi-rows tr.selected td{background:var(--yellow-50)}
.grid-row.qi-row-selected .data-row{background:var(--yellow-50)}
.qi-class{font-size:11px;padding:1px 6px;border-radius:8px;background:var(--gray-100)}
.qi-class.ctq{background:var(--red-100);color:var(--red-700)}
.qi-class.major{background:var(--orange-100);color:var(--orange-700)}
.qi-b-add{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
.qi-used-line{padding:3px 0}
.qi-preview{padding:10px 12px;border-radius:8px;background:var(--gray-50);min-height:34px;display:flex;flex-direction:column;gap:6px}
.qi-pv{display:flex;gap:10px;align-items:baseline}
.qi-pv span{min-width:92px;color:var(--text-muted);font-size:var(--text-sm)}
.qi-pv b{font-size:var(--text-lg);font-variant-numeric:tabular-nums}
.qi-pv.ok b{color:var(--green-700)}
.qi-mono{font-variant-numeric:tabular-nums;white-space:nowrap}
.qi-empty{padding:14px;border:1px dashed var(--border-color);border-radius:8px;color:var(--text-muted);text-align:center;margin-top:12px}
.qi-seg{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}
.qi-seg-btn{border:1px solid var(--border-color);background:var(--fg-color);border-radius:8px;padding:6px 12px;display:inline-flex;gap:6px;align-items:center;font-size:var(--text-md)}
.qi-seg-btn.sm{padding:3px 10px;font-size:var(--text-sm);min-width:40px;justify-content:center}
.qi-seg-btn.on{border-color:var(--primary);background:var(--primary);color:var(--white)}
.qi-chips{display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:6px;margin-bottom:12px}
.qi-chip{border:1px solid var(--border-color);background:var(--fg-color);border-radius:8px;padding:6px 8px;text-align:left;display:flex;flex-direction:column;gap:1px}
.qi-chip:hover{border-color:var(--gray-500)}
.qi-chip.on{border-color:var(--primary);box-shadow:0 0 0 1px var(--primary);background:var(--blue-50)}
.qi-chip-sym{font-size:18px;font-weight:600;line-height:1.2}
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
