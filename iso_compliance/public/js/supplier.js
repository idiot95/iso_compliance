// The supplier's QMS standing, visible the moment the form opens.
// State is written by approved FRM-005 evaluations (SOP-005 / REG-007).

frappe.ui.form.on("Supplier", {
	refresh(frm) {
		if (frm.doc.__islocal) return;
		frm.set_intro("");
		const status = frm.doc.custom_approval_status;
		const stars = frm.doc.custom_score ? ` — ${((frm.doc.custom_score / 20) || 0).toFixed(1)}★ (${Math.round(frm.doc.custom_score)}%)` : "";
		const due = frm.doc.custom_reapproval_due
			? __(", re-evaluation due {0}", [frappe.datetime.str_to_user(frm.doc.custom_reapproval_due)])
			: "";
		if (status === "Approved") {
			frm.set_intro(__("Approved supplier{0}{1}.", [stars, due]), "green");
		} else if (status === "Suspended") {
			frm.set_intro(__("Suspended — Purchase Orders to this supplier are blocked (SOP-005)."), "red");
		} else if (status) {
			frm.set_intro(__("{0}{1}{2} — record a Supplier Evaluation (FRM-005) to grant approval.", [__(status), stars, due]), "orange");
		} else {
			frm.set_intro(__("Not yet classified on the Approved Suppliers Register (REG-007). Record a Supplier Evaluation (FRM-005)."), "orange");
		}

		if (frappe.model.can_create("Supplier Evaluation")) {
			frm.add_custom_button(
				__("Supplier Evaluation"),
				() => {
					frappe.route_options = { supplier: frm.doc.name };
					frappe.new_doc("Supplier Evaluation");
				},
				__("Create")
			);
		}
	},
});
