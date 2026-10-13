// Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
// For license information, please see license.txt

// Work Order › Final inspection (SPEC §4.3): pick the lot and sample, and
// the inspector screen opens on a new inspection that owns a draft
// Manufacture entry for that lot.

frappe.ui.form.on("Work Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || ["Stopped", "Closed", "Cancelled"].includes(frm.doc.status)) return;
		if (!frappe.model.can_create("Quality Inspection")) return;
		frm.add_custom_button(__("Final inspection"), () => qi_final_dialog(frm), __("Inspect"));
	},
});

function qi_final_dialog(frm) {
	frappe.call({ method: "iso_compliance.qi.inspection.final_inspection_info", args: { work_order: frm.doc.name } }).then(({ message: info }) => {
		if (!info.drawing) {
			frappe.msgprint(__("{0} has no drawing template on its BOM or item, so the final inspection is a normal Quality Inspection.", [frm.doc.production_item]));
			return;
		}
		const list = info.existing.length
			? `<table class="table table-sm"><thead><tr><th>${__("Inspection")}</th><th>${__("Lot")}</th><th>${__("Sample")}</th><th>${__("State")}</th></tr></thead><tbody>${info.existing
					.map(
						(q) => `<tr><td><a href="/app/inspect/${encodeURIComponent(q.name)}">${frappe.utils.escape_html(q.name)}</a></td>
						<td>${q.custom_lot_qty || ""}</td><td>${q.sample_size || ""}</td>
						<td>${q.docstatus ? frappe.utils.escape_html(q.custom_disposition || q.status) : __("Draft")}</td></tr>`
					)
					.join("")}</tbody></table>`
			: `<p class="text-muted">${__("No final inspection yet.")}</p>`;
		const d = new frappe.ui.Dialog({
			title: __("Final inspection · {0}", [frm.doc.name]),
			fields: [
				{ fieldtype: "HTML", options: list },
				{ fieldname: "lot_qty", fieldtype: "Float", label: __("Lot quantity"), reqd: 1, default: info.lot_qty },
				{
					fieldname: "sample_size",
					fieldtype: "Float",
					label: __("Sample size"),
					reqd: 1,
					default: info.sample_size,
					description: __("Pre-filled from Inspection Settings; any number may be entered."),
				},
				{ fieldtype: "HTML", options: `<p class="text-muted small">${__("Template: {0}", [frappe.utils.escape_html(info.template)])}</p>` },
			],
			primary_action_label: __("Start inspection"),
			primary_action: (v) =>
				frappe
					.call({
						method: "iso_compliance.qi.inspection.start_final_inspection",
						args: { work_order: frm.doc.name, lot_qty: v.lot_qty, sample_size: v.sample_size },
						freeze: true,
						freeze_message: __("Preparing the lot…"),
					})
					.then(({ message }) => {
						d.hide();
						frappe.set_route("inspect", message);
					}),
		});
		d.fields_dict.lot_qty.df.onchange = () => {
			const lot = d.get_value("lot_qty") || 0;
			frappe.db.get_single_value("Inspection Settings", "default_sample_percent").then((pct) => {
				d.set_value("sample_size", Math.min(lot, Math.max(1, Math.ceil((lot * (pct || 5)) / 100))));
			});
		};
		d.show();
	});
}
