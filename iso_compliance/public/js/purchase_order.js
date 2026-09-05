// Supplier approval standing shown as soon as a supplier is picked on a
// Purchase Order. Enforcement is server-side (overrides/purchase_order.py).

function hcc_show_supplier_standing(frm) {
	if (!frm.doc.supplier || frm.doc.docstatus !== 0) return;
	frappe.db
		.get_value("Supplier", frm.doc.supplier, [
			"custom_approval_status",
			"custom_score",
			"custom_reapproval_due",
		])
		.then((r) => {
			const s = r && r.message;
			if (!s) return;
			frm.set_intro("");
			const status = s.custom_approval_status;
			const score = s.custom_score ? ` — ${(s.custom_score / 20).toFixed(1)}★` : "";
			if (status === "Approved") {
				frm.set_intro(__("Supplier is Approved{0} (REG-007).", [score]), "green");
			} else if (status === "Suspended") {
				frm.set_intro(__("Supplier is Suspended — this order cannot be submitted (SOP-005)."), "red");
			} else {
				frm.set_intro(
					__("Supplier is {0} on the Approved Suppliers Register — an FRM-005 evaluation is expected before regular orders (SOP-005).", [
						status ? __(status) : __("not yet classified"),
					]),
					"orange"
				);
			}
		});
}

frappe.ui.form.on("Purchase Order", {
	refresh: hcc_show_supplier_standing,
	supplier: hcc_show_supplier_standing,
});
