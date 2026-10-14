// Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
// For license information, please see license.txt

// SOP-006 (2026-10-14): ERPNext's own Finish is the way in. Its Manufacture
// entry holds the finished goods in Inspection Required and is assigned to
// Engineering; the Work Order shows what waits and lets the engineer start.
// hcc.inspection.pick comes from inspection_waiting.js.
frappe.ui.form.on("Work Order", {
	async refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		const { message: rows } = await frappe.call({
			method: "iso_compliance.overrides.inspection_flow.waiting_for_work_order",
			args: { work_order: frm.doc.name },
		});
		if (!(rows || []).length) return;
		const qty = rows.reduce((s, r) => s + r.qty, 0);
		frm.dashboard.add_comment(
			__("{0} {1} finished and waiting in Inspection Required for the final inspection.", [
				format_number(qty), frappe.utils.escape_html(rows[0].uom || ""),
			]),
			"blue",
			true
		);
		if (!frappe.model.can_create("Quality Inspection")) return;
		frm.add_custom_button(__("Final inspection"), () => {
			const start = (r) => hcc.inspection.pick("Stock Entry", r.stock_entry, [r]);
			if (rows.length === 1) return start(rows[0]);
			const d = new frappe.ui.Dialog({
				title: __("Which lot?"),
				fields: [{
					fieldname: "lot", fieldtype: "Select", label: __("Manufacture entry"), reqd: 1,
					options: rows.map((r, i) => ({ value: String(i), label: `${r.stock_entry} · ${format_number(r.qty)} ${r.uom || ""}` })),
				}],
				primary_action_label: __("Inspect"),
				primary_action: (v) => {
					d.hide();
					start(rows[cint(v.lot)]);
				},
			});
			d.show();
		}).addClass("btn-primary");
	},
});
