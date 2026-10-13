// Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
// For license information, please see license.txt

// Quality Inspection on a drawing template: open the inspector screen, and
// show what was measured. Inspections on legacy templates are unchanged.

frappe.ui.form.on("Quality Inspection", {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.custom_stage) return;
		frm.add_custom_button(frm.doc.docstatus === 0 ? __("Open inspector") : __("View in inspector"), () =>
			frappe.set_route("inspect", frm.doc.name)
		);
		if (frm.doc.docstatus === 0) {
			frm.set_intro(__("Measurements are entered in the inspector screen; this form shows their summary."), "blue");
		}
		qi_render_measurements(frm);
	},
});

function qi_render_measurements(frm) {
	const field = frm.fields_dict.custom_measurements_html;
	if (!field) return;
	frappe.call({ method: "iso_compliance.qi.inspector.get_inspection", args: { qi: frm.doc.name } }).then(({ message: d }) => {
		const esc = frappe.utils.escape_html;
		const html = d.rows
			.map((r) => {
				const vals = r.values
					.map((v) => {
						const n = parseFloat(v.value);
						const bad = r.row_type === "Visual" ? v.value === "NG" : !(n >= r.min - 1e-9 && n <= r.max + 1e-9);
						return `<span class="qi-val ${bad ? "bad" : ""}" title="#${v.sample_no}">${esc(v.value)}</span>`;
					})
					.join(" ");
				return `<tr><td><b>${esc(r.balloon)}</b></td><td>${esc(r.specification)}</td>
					<td class="text-muted">${r.row_type === "Visual" ? "OK / NG" : `${esc(r.min_display)} – ${esc(r.max_display)} ${esc(r.unit || "")}`}</td>
					<td>${r.values.length}/${r.required}</td><td>${vals || '<span class="text-muted">—</span>'}</td></tr>`;
			})
			.join("");
		field.$wrapper.html(`<style>.qi-val{display:inline-block;padding:0 4px;margin:1px;border-radius:4px;background:var(--gray-100);font-variant-numeric:tabular-nums}.qi-val.bad{background:var(--red-100);color:var(--red-700)}</style>
			<table class="table table-sm"><thead><tr><th>#</th><th>${__("Characteristic")}</th><th>${__("Limits")}</th><th>n</th><th>${__("Values")}</th></tr></thead><tbody>${html}</tbody></table>`);
	});
}
