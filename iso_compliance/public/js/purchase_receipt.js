// SOP-006: the incoming identification label — item, batch barcode, supplier,
// date of goods in. Printed at goods-in, before the inspection is finished,
// because material waiting to be inspected is when a mix-up happens.
// The QC OK / Not OK stickers are bought in and applied separately.

frappe.ui.form.on("Purchase Receipt", {
	refresh(frm) {
		hcc.labels.add_button(frm, __("Material Labels"));
	},
});
