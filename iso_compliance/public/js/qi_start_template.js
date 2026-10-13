// Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
// For license information, please see license.txt

// BOM / Item › Create › Inspection template (EXTERNAL_CHANGES.md §5).
// Opens the drawing template in use, or starts one from the drawing on the
// BOM: the template is created with the drawing attached, so the builder
// opens straight onto it.

frappe.provide("iso_qi");

iso_qi.start_template = async function (item, bom) {
	const { message: o } = await frappe.call({ method: "iso_compliance.qi.template.start_options", args: { item, bom } });
	if (o.current) {
		frappe.set_route("Form", "Quality Inspection Template", o.current);
		return;
	}
	const esc = frappe.utils.escape_html;
	// "40.054.GA.R03.pdf" → drawing 40.054.GA, revision 03
	const guess = (file) => {
		const base = (file || "").replace(/\.(pdf|png|jpe?g)$/i, "");
		const m = base.match(/^(.*?)[ ._-]?R(?:ev)?[ ._-]?(\d{1,2})$/i);
		return m ? { no: m[1], rev: m[2] } : { no: base, rev: "" };
	};
	const options = o.drawings.map((f) => ({
		value: f.name,
		label: `${f.file_name} · ${f.attached_to_doctype} ${f.attached_to_name}${f.bom_default ? " (" + __("default") + ")" : ""}`,
	}));
	const first = o.drawings[0];
	const g = guess(first && first.file_name);
	const d = new frappe.ui.Dialog({
		title: __("Inspection template for {0}", [o.item]),
		fields: [
			{
				fieldtype: "HTML",
				options: o.legacy
					? `<p class="text-muted small">${__("The item now uses {0}, a template without a drawing. Its inspections stay as they are; the new template takes over once you tag the BOMs.", [esc(o.legacy)])}</p>`
					: "",
			},
			options.length
				? { fieldname: "file", fieldtype: "Select", label: __("Drawing"), options, default: first.name, reqd: 0 }
				: { fieldtype: "HTML", options: `<p>${__("No drawing is attached to {0}'s BOMs or Item. You can upload one in the template.", [esc(o.item)])}</p>` },
			{ fieldname: "drawing_no", fieldtype: "Data", label: __("Drawing no."), default: g.no },
			{ fieldname: "revision", fieldtype: "Data", label: __("Revision"), default: g.rev },
		],
		primary_action_label: __("Create template"),
		primary_action: (v) =>
			frappe
				.call({
					method: "iso_compliance.qi.template.start_template",
					args: { item: o.item, drawing_no: v.drawing_no, revision: v.revision, file: v.file || null },
					freeze: true,
				})
				.then(({ message }) => {
					d.hide();
					frappe.set_route("Form", "Quality Inspection Template", message);
				}),
	});
	if (options.length) {
		d.fields_dict.file.df.onchange = () => {
			const f = o.drawings.find((x) => x.name === d.get_value("file"));
			const g2 = guess(f && f.file_name);
			d.set_values({ drawing_no: g2.no, revision: g2.rev });
		};
	}
	d.show();
};

iso_qi.can_build_template = () => frappe.user.has_role(["Quality Manager", "System Manager"]);

// The "Inspection Plan" summary on BOM and Item: the tagged template's rows
// with their tolerances, and the way in to build or open it.
iso_qi.render_plan = async function (frm, item, bom) {
	const field = frm.fields_dict.custom_inspection_plan_html;
	if (!field) return;
	const esc = frappe.utils.escape_html;
	const template = frm.doc.quality_inspection_template;
	const build = iso_qi.can_build_template() && !frm.is_new()
		? `<button class="btn btn-xs btn-default qi-plan-build">${template ? __("Open / change template") : __("Build inspection template from drawing")}</button>`
		: "";
	if (!template) {
		field.$wrapper.html(`<div class="qi-plan"><p class="text-muted">${__("No inspection template on this {0} yet.", [__(frm.doctype)])}</p>${build}</div>`);
	} else {
		const { message: p } = await frappe.call({ method: "iso_compliance.qi.template.plan_summary", args: { template } });
		const rows = p.rows
			.map((r) => `<tr><td>${esc(r.balloon)}</td><td>${esc(r.specification)}${r.type && r.type !== "Dimension" ? ` <span class="text-muted">(${esc(__(r.type))})</span>` : ""}</td>
				<td>${esc(r.spec_text)}</td><td>${esc(r.limits)} ${esc(r.unit)}</td><td>${esc(r["class"])}</td><td class="text-muted">${esc(r.stages)}</td></tr>`)
			.join("");
		field.$wrapper.html(`<div class="qi-plan">
			<div class="qi-plan-head"><a href="/app/quality-inspection-template/${encodeURIComponent(p.name)}"><b>${esc(p.name)}</b></a>
				${p.drawing ? `<span class="text-muted"> · ${__("Drawing")} ${esc(p.drawing_no || "")}${p.revision ? " " + __("Rev") + " " + esc(p.revision) : ""}</span>` : `<span class="text-muted"> · ${__("no drawing (older template)")}</span>`}
				${p.locked ? `<span class="indicator-pill orange">${__("Locked")}</span>` : ""}
				${p.superseded_by ? `<span class="indicator-pill red">${__("Superseded by {0}", [esc(p.superseded_by)])}</span>` : ""}
			</div>
			<table class="table table-sm qi-plan-table"><thead><tr><th>#</th><th>${__("Parameter")}</th><th>${__("As on drawing")}</th>
				<th>${__("Limits")}</th><th>${__("Class")}</th><th>${__("Stages")}</th></tr></thead><tbody>${rows || `<tr><td colspan="6" class="text-muted">${__("No rows yet.")}</td></tr>`}</tbody></table>
			${build}</div>`);
	}
	field.$wrapper.find(".qi-plan-build").on("click", () => iso_qi.start_template(item, bom));
};

frappe.ui.form.on("BOM", {
	refresh(frm) {
		iso_qi.render_plan(frm, frm.doc.item, frm.doc.name);
		if (frm.is_new() || frm.doc.docstatus === 2 || !iso_qi.can_build_template()) return;
		frm.add_custom_button(__("Inspection template"), () => iso_qi.start_template(frm.doc.item, frm.doc.name), __("Create"));
	},
	quality_inspection_template(frm) {
		iso_qi.render_plan(frm, frm.doc.item, frm.doc.name);
	},
});

frappe.ui.form.on("Item", {
	refresh(frm) {
		iso_qi.render_plan(frm, frm.doc.name);
		if (frm.is_new() || !iso_qi.can_build_template()) return;
		frm.add_custom_button(__("Inspection template"), () => iso_qi.start_template(frm.doc.name), __("Create"));
	},
	quality_inspection_template(frm) {
		iso_qi.render_plan(frm, frm.doc.name);
	},
});

frappe.dom.set_style(`
.qi-plan{padding:4px 0 8px}
.qi-plan-head{margin-bottom:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.qi-plan-table td,.qi-plan-table th{font-size:var(--text-sm)}
`);
