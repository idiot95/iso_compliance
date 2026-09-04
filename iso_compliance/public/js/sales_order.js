// FRM-036 on the Sales Order form: a create button that opens the review
// pre-filled, and a banner when SOP-004's slabs demand one. The actual gate
// is server-side (overrides/sales_order.py); this file is convenience only.

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0 || frm.doc.__islocal) return;
		if (!frappe.model.can_create("Techno Commercial Review")) return;

		frm.add_custom_button(
			__("Techno-Commercial Review"),
			() => {
				frappe.route_options = { sales_order: frm.doc.name };
				frappe.new_doc("Techno Commercial Review");
			},
			__("Create")
		);

		// Slabs are rupee values: compare the company-currency total, not the
		// foreign-currency figure on an export order.
		const STANDARD_FROM = 500000;
		const DETAILED_FROM = 1000000;
		const value = frm.doc.base_grand_total || 0;
		if (value < STANDARD_FROM) return;
		const tier = value >= DETAILED_FROM ? __("Detailed") : __("Standard");

		frappe.db
			.get_list("Techno Commercial Review", {
				filters: { sales_order: frm.doc.name, docstatus: 1 },
				fields: ["name", "outcome"],
				limit: 1,
			})
			.then((rows) => {
				if (rows && rows.length) return;
				// Clear before setting: refresh fires more than once around a
				// save, and stacked intros show the banner twice.
				frm.set_intro("");
				frm.set_intro(
					__(
						"This order requires a {0} Techno-Commercial Review (FRM-036) before it can be submitted. Use Create → Techno-Commercial Review.",
						[tier]
					),
					"orange"
				);
			});
	},
});
