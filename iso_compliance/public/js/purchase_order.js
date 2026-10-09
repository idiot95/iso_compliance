// Supplier approval standing shown as soon as a supplier is picked on a
// Purchase Order, and the override box offered only when it is needed.
// Enforcement is server-side (overrides/purchase_order.py).

const HCC_OVERRIDE_FIELDS = [
	"custom_supplier_override",
	"custom_supplier_override_reason",
	"custom_supplier_override_by",
];

function hcc_show_supplier_standing(frm) {
	if (!frm.doc.supplier) {
		frm.toggle_display(HCC_OVERRIDE_FIELDS, false);
		return;
	}
	frappe.db
		.get_value("Supplier", frm.doc.supplier, [
			"custom_approval_status",
			"custom_score",
			"custom_reapproval_due",
		])
		.then((r) => {
			const s = r && r.message;
			if (!s) return;
			const status = s.custom_approval_status;
			const approved = status === "Approved";
			// The override is only meaningful for a supplier that needs one;
			// a submitted order keeps showing it if it was used.
			frm.toggle_display("custom_supplier_override", !approved && status !== "Suspended" && (frm.doc.docstatus === 0 || frm.doc.custom_supplier_override));
			frm.toggle_display("custom_supplier_override_reason", !!frm.doc.custom_supplier_override);
			frm.toggle_display("custom_supplier_override_by", !!frm.doc.custom_supplier_override_by);

			if (frm.doc.docstatus !== 0) return;
			frm.set_intro("");
			const score = s.custom_score ? ` — ${(s.custom_score / 20).toFixed(1)}★` : "";
			if (approved) {
				frm.set_intro(__("Supplier is Approved{0} (REG-007).", [score]), "green");
			} else if (status === "Suspended") {
				frm.set_intro(__("Supplier is Suspended: this order can't be submitted (SOP-005)."), "red");
			} else {
				frm.set_intro(
					__(
						"Supplier is {0}, not Approved: this order can't be submitted. Approve the supplier with a Supplier Evaluation (FRM-005), or for an urgent order tick Override supplier approval and have a Purchase Manager or Quality Manager submit it.",
						[status ? __(status) : __("not yet evaluated")]
					),
					"red"
				);
			}
		});
}

frappe.ui.form.on("Purchase Order", {
	refresh: hcc_show_supplier_standing,
	supplier: hcc_show_supplier_standing,
	custom_supplier_override: hcc_show_supplier_standing,
});
