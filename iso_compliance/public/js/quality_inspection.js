// A rejected Quality Inspection is one click away from its Non Conformance
// (FRM-020): the NC opens pre-filled with the source, references, item and
// the readings that failed (SOP-012 -> SOP-013 chain).

frappe.ui.form.on("Quality Inspection", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || frm.doc.status !== "Rejected") return;
		if (!frappe.model.can_create("Non Conformance")) return;

		frm.add_custom_button(
			__("Non Conformance"),
			() => {
				const source_map = {
					"Purchase Receipt": "Incoming",
					"Purchase Invoice": "Incoming",
					"Stock Entry": "In-Process",
					"Job Card": "In-Process",
					"Delivery Note": "Final Inspection",
				};
				const failed = (frm.doc.readings || [])
					.filter((r) => r.status === "Rejected")
					.map((r) => `${r.specification}${r.reading_value ? ": " + r.reading_value : ""}`)
					.join("; ");
				const opts = {
					subject: __("Rejected inspection {0} — {1}", [frm.doc.name, frm.doc.item_code]),
					status: "Open",
					custom_source: source_map[frm.doc.reference_type] || "Production",
					custom_quality_inspection: frm.doc.name,
					custom_item: frm.doc.item_code,
					custom_batch_wo: frm.doc.batch_no || "",
					custom_qty: frm.doc.sample_size,
					details: failed ? __("Failed parameters: {0}", [failed]) : "",
				};
				if (frm.doc.reference_type === "Purchase Receipt") {
					opts.custom_purchase_receipt = frm.doc.reference_name;
				} else if (frm.doc.reference_type === "Delivery Note") {
					opts.custom_delivery_note = frm.doc.reference_name;
				}
				frappe.route_options = opts;
				frappe.new_doc("Non Conformance");
			},
			__("Create")
		);
	},
});
