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
				const call = (row, sample_size) =>
					frappe
						.call({
							method: "iso_compliance.qi.inspection.start_receipt_inspection",
							args: { purchase_receipt: frm.doc.name, row, sample_size },
							freeze: true,
						})
						.then(({ message }) => frappe.set_route("inspect", message));
				// a new inspection asks how many pieces; one already started opens as it is
				const start = async (row) => {
					const r = frm.doc.items.find((x) => x.name === row);
					const lot = flt(r.received_qty) || flt(r.qty);
					const { message: started } = await frappe.db.get_value("Quality Inspection",
						{ reference_type: "Purchase Receipt", reference_name: frm.doc.name, child_row_reference: row, docstatus: ["<", 2] }, "name");
					if (started && started.name) return call(row);
					const { message: pct } = await frappe.db.get_single_value("Inspection Settings", "default_sample_percent");
					await frappe.require("/assets/iso_compliance/js/qi_sample.js");
					window.iso_qi_sample.ask({ lot, suggested: Math.min(lot, Math.max(1, Math.ceil((lot * (pct || 5)) / 100))), then: (n) => call(row, n) });
				};
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
