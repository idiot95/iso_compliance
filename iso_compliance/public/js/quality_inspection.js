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
				// Drawing inspections can hold the same parameter at several
				// balloons: name the balloon so the NC says which one failed.
				const failed = (frm.doc.readings || [])
					.filter((r) => r.status === "Rejected")
					.map((r) => {
						const name = r.custom_balloon_no ? `${r.custom_balloon_no} ${r.specification}` : r.specification;
						if (r.custom_row_type && r.custom_row_type !== "Visual")
							return `${name}: ${r.custom_out_of_spec || 0} of ${r.custom_n || 0} out (${r.custom_obs_min} – ${r.custom_obs_max})`;
						return `${name}${r.reading_value ? ": " + r.reading_value : ""}`;
					})
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
