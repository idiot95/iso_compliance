// SOP-006's outgoing counterpart: the dispatch label — item, batch barcode,
// customer, their PO and the sales order it was raised against. The batch is
// the same key the Certificate of Conformity cites, so a complaint resolves
// back through the delivery to the work order and on to the incoming material.

frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		hcc.labels.add_button(frm, __("Dispatch Labels"));
	},
});
