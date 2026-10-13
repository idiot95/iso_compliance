// Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
// For license information, please see license.txt

// Job Card › Inspect: the in-process inspection on the drawing template.
// Only shown when a drawing template applies; otherwise ERPNext's own
// Quality Inspection flow is untouched.

frappe.ui.form.on("Job Card", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus === 2 || !frappe.model.can_create("Quality Inspection")) return;
		frappe
			.call({
				method: "iso_compliance.qi.inspection.drawing_template_for",
				args: { item_code: frm.doc.production_item, bom_no: frm.doc.bom_no, explicit: frm.doc.quality_inspection_template },
			})
			.then(({ message }) => {
				if (!message) return;
				frm.add_custom_button(__("In-process inspection"), () => qi_check_point_dialog(frm), __("Inspect"));
			});
	},
});

// First-off at the start of the Work Order's run, patrols during it,
// last-off at its end. One Job Card can carry several.
function qi_check_point_dialog(frm) {
	frappe.call({ method: "iso_compliance.qi.inspection.job_card_check_points", args: { job_card: frm.doc.name } }).then(({ message: o }) => {
		const esc = frappe.utils.escape_html;
		const list = o.existing.length
			? `<table class="table table-sm"><tbody>${o.existing
					.map((q) => `<tr><td><a href="/app/inspect/${encodeURIComponent(q.name)}">${esc(q.name)}</a></td><td>${esc(q.custom_check_point || "")}</td>
					<td>${q.docstatus ? esc(q.custom_disposition || q.status) : __("Draft")}</td></tr>`)
					.join("")}</tbody></table>`
			: `<p class="text-muted">${__("No in-process inspection on this Job Card yet.")}</p>`;
		const d = new frappe.ui.Dialog({
			title: __("In-process inspection · {0}", [frm.doc.name]),
			fields: [
				{ fieldtype: "HTML", options: list },
				{
					fieldname: "check_point",
					fieldtype: "Select",
					label: __("Check point"),
					options: "First-off\nPatrol\nLast-off",
					default: o.default,
					reqd: 1,
					description: __("First-off and last-off check one piece; a patrol samples the run."),
				},
			],
			primary_action_label: __("Start inspection"),
			primary_action: (v) =>
				frappe
					.call({ method: "iso_compliance.qi.inspection.start_job_card_inspection", args: { job_card: frm.doc.name, check_point: v.check_point }, freeze: true })
					.then(({ message: qi }) => {
						d.hide();
						frappe.set_route("inspect", qi);
					}),
		});
		d.show();
	});
}
