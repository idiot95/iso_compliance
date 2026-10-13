// Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
// For license information, please see license.txt

// Purchase Receipt › Inspect: incoming inspection on a drawing template,
// one per receipt row. Rows on legacy templates keep ERPNext's own flow.

frappe.ui.form.on("Purchase Receipt", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus === 2 || !frappe.model.can_create("Quality Inspection")) return;
		const items = [...new Set((frm.doc.items || []).map((i) => i.item_code))];
		Promise.all(
			items.map((item_code) =>
				frappe
					.call({ method: "iso_compliance.qi.inspection.drawing_template_for", args: { item_code } })
					.then(({ message }) => [item_code, message])
			)
		).then((pairs) => {
			const drawing = new Set(pairs.filter(([, t]) => t).map(([i]) => i));
			const rows = (frm.doc.items || []).filter((r) => drawing.has(r.item_code));
			if (!rows.length) return;
			frm.add_custom_button(__("Incoming inspection"), () => {
				const start = (row) =>
					frappe
						.call({
							method: "iso_compliance.qi.inspection.start_receipt_inspection",
							args: { purchase_receipt: frm.doc.name, row },
							freeze: true,
						})
						.then(({ message }) => frappe.set_route("inspect", message));
				if (rows.length === 1) return start(rows[0].name);
				const d = new frappe.ui.Dialog({
					title: __("Which item?"),
					fields: [
						{
							fieldname: "row",
							fieldtype: "Select",
							label: __("Row"),
							reqd: 1,
							options: rows.map((r) => ({ value: r.name, label: `#${r.idx} ${r.item_code} · ${r.received_qty || r.qty}` })),
						},
					],
					primary_action_label: __("Inspect"),
					primary_action: (v) => {
						d.hide();
						start(v.row);
					},
				});
				d.show();
			}, __("Inspect"));
		});
	},
});
