// FRM-005 fills itself as far as it can: picking the supplier brings its
// category, the category loads that template's criteria, and the next review
// date follows from the template's interval. The server repeats all of this
// on save (and adds the receipt-based pre-ratings); this file only makes it
// visible before the first save.

function se_next_review(frm) {
	if (!frm.doc.category || frm.doc.docstatus !== 0) return;
	frappe.db.get_value("Supplier Evaluation Template", frm.doc.category, "review_months").then((r) => {
		const months = (r && r.message && r.message.review_months) || 12;
		const from = frm.doc.evaluation_date || frappe.datetime.get_today();
		frm.set_value("next_review_date", frappe.datetime.add_months(from, months));
	});
}

function se_load_template(frm) {
	if (!frm.doc.category || frm.doc.docstatus !== 0) return;
	frappe.db.get_doc("Supplier Evaluation Template", frm.doc.category).then((template) => {
		const same =
			(frm.doc.criteria || []).length === template.criteria.length &&
			template.criteria.every(
				(t, i) => frm.doc.criteria[i].criterion === t.criterion && frm.doc.criteria[i].weight === t.weight
			);
		frm.set_value("template", template.name);
		if (same) return;
		frm.clear_table("criteria");
		template.criteria.forEach((t) => {
			frm.add_child("criteria", { criterion: t.criterion, weight: t.weight, auto_rate: t.auto_rate });
		});
		frm.refresh_field("criteria");
	});
	se_next_review(frm);
}

frappe.ui.form.on("Supplier Evaluation", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0) return;
		frm.set_intro("");
		if (!frm.doc.category) {
			frm.set_intro(__("Pick the supplier; its category loads the right criteria."), "blue");
		} else if (frm.is_new()) {
			frm.set_intro(__("Save to pre-rate quality and delivery from the last 12 months of receipts, then rate the rest."), "blue");
		}
		if (frm.doc.category && !(frm.doc.criteria || []).length) se_load_template(frm);
	},

	supplier(frm) {
		if (!frm.doc.supplier) return;
		frappe.db.get_value("Supplier", frm.doc.supplier, "custom_category").then((r) => {
			const category = r && r.message && r.message.custom_category;
			if (category && category !== frm.doc.category) frm.set_value("category", category);
		});
	},

	category(frm) {
		se_load_template(frm);
	},

	evaluation_date(frm) {
		se_next_review(frm);
	},
});
