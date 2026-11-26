// FRM-036 on the Quotation form: the same create button and banner the Sales
// Order has. The actual gate is server-side (overrides/sales_order.py); this
// file is convenience only.

frappe.ui.form.on("Quotation", {
	refresh(frm) {
		if (frm.doc.__islocal || frm.doc.docstatus !== 0) return;
		if (!frappe.model.can_create("Techno Commercial Review")) return;

		frm.add_custom_button(
			__("Techno-Commercial Review"),
			() => {
				frappe.route_options = { quotation: frm.doc.name, review_stage: "Enquiry Review" };
				frappe.new_doc("Techno Commercial Review");
			},
			__("Create")
		);

		// Slabs are rupee values: compare the company-currency total, not the
		// foreign-currency figure on an export quotation.
		const STANDARD_FROM = 500000;
		const DETAILED_FROM = 1000000;
		const value = frm.doc.base_grand_total || 0;
		if (value < STANDARD_FROM) return;
		const tier = value >= DETAILED_FROM ? __("Detailed") : __("Standard");

		frappe.db
			.get_list("Techno Commercial Review", {
				filters: { quotation: frm.doc.name, docstatus: 1 },
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
						"This quotation requires a {0} Techno-Commercial Review (FRM-036) before it can be submitted. Use Create → Techno-Commercial Review.",
						[tier]
					),
					"orange"
				);
			});
	},
});
