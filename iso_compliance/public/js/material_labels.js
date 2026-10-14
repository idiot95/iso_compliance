// Material identification labels (SOP-006): eight to an A4 sheet, or a thermal
// roll (the layouts live in iso_compliance.api.labels.LAYOUTS). Labels for stock
// already on the shelves, and the scan lookup, are on the Stock Labels page.
//
// Shared by the incoming label on Purchase Receipt and the outgoing label on
// Delivery Note. The label count is typed per batch and never derived from the
// received quantity: a single receipt line on this site has reached 14,137
// blocks, and the sticker goes on the package, not the piece. The running total
// and the confirmation above fifty exist so one stray keystroke cannot send a
// thousand sheets to the printer.

frappe.provide("hcc.labels");

hcc.labels.WARN_THRESHOLD = 50;

hcc.labels.add_button = function (frm, label) {
	if (frm.doc.docstatus !== 1) return;
	frm.add_custom_button(
		label,
		() => hcc.labels.open_dialog(frm),
		__("Print")
	);
};

hcc.labels.open_dialog = async function (frm) {
	if (!hcc.labels.layouts) {
		hcc.labels.layouts = (await frappe.call({ method: "iso_compliance.api.labels.layouts" })).message;
	}
	frappe.call({
		method: "iso_compliance.api.labels.get_label_rows",
		args: { doctype: frm.doctype, name: frm.doc.name },
		freeze: true,
		freeze_message: __("Reading batches…"),
		callback: (r) => {
			const rows = r.message || [];
			if (!rows.length) {
				frappe.msgprint({
					title: __("Nothing to label"),
					message: __("This document has no item lines."),
					indicator: "orange",
				});
				return;
			}
			hcc.labels.show(frm, rows);
		},
	});
};

hcc.labels.show = function (frm, rows) {
	const unbatched = rows.filter((d) => !d.batch_no).length;

	const dialog = new frappe.ui.Dialog({
		title: __("Print Material Labels"),
		size: "large",
		fields: [
			{
				fieldname: "intro",
				fieldtype: "HTML",
				options: `<p class="text-muted" style="margin-bottom:8px">${__(
					"One row per batch. Set how many labels to print for each — the sticker goes on the package or the block, so this is not the received quantity."
				)}${
					unbatched
						? `<br><span style="color:var(--orange-600)">${__(
								"{0} line(s) have no batch: their barcode carries the item code instead.",
								[unbatched]
						  )}</span>`
						: ""
				}</p>`,
			},
			{
				fieldname: "rows",
				fieldtype: "Table",
				cannot_add_rows: true,
				cannot_delete_rows: true,
				in_place_edit: true,
				data: rows,
				get_data: () => rows,
				fields: [
					{ fieldname: "item_name", label: __("Item"), fieldtype: "Data", read_only: 1, in_list_view: 1, columns: 4 },
					{ fieldname: "batch_no", label: __("Batch"), fieldtype: "Data", read_only: 1, in_list_view: 1, columns: 3 },
					{ fieldname: "qty", label: __("Qty"), fieldtype: "Float", read_only: 1, in_list_view: 1, columns: 2 },
					{ fieldname: "labels", label: __("Labels"), fieldtype: "Int", in_list_view: 1, columns: 2 },
					{ fieldname: "item_code", label: __("Item Code"), fieldtype: "Data", read_only: 1 },
					{ fieldname: "idx", label: "idx", fieldtype: "Int", read_only: 1, hidden: 1 },
				],
			},
			{
				fieldname: "layout",
				fieldtype: "Select",
				label: __("Print on"),
				options: hcc.labels.layouts || [],
				default: "a4-8",
				change: () => refresh_total(),
			},
			{
				fieldname: "guides",
				fieldtype: "Check",
				label: __("Show cutting guides"),
				description: __(
					"Outlines each label. Print one on plain paper and hold it against a label sheet to check the printer is not scaling the page."
				),
			},
			{ fieldname: "total", fieldtype: "HTML" },
		],
		primary_action_label: __("Print"),
		primary_action: () => {
			const data = (dialog.get_value("rows") || []).filter((d) => cint(d.labels) > 0);
			const total = data.reduce((sum, d) => sum + cint(d.labels), 0);
			if (!total) {
				frappe.msgprint(__("Set a label count on at least one row."));
				return;
			}
			const go = () => {
				dialog.hide();
				hcc.labels.print(frm, data, dialog.get_value("guides"), dialog.get_value("layout"));
			};
			if (total > hcc.labels.WARN_THRESHOLD) {
				frappe.confirm(__("Print {0} labels?", [total]), go);
			} else {
				go();
			}
		},
	});

	// Live total, so the sheet count is known before anything reaches the printer.
	const refresh_total = () => {
		const data = dialog.get_value("rows") || [];
		const total = data.reduce((sum, d) => sum + cint(d.labels), 0);
		const sheet = (dialog.get_value("layout") || "a4-8") === "a4-8";
		dialog.fields_dict.total.$wrapper.html(
			`<div style="padding:6px 0;font-weight:600">${__("Total")}: ${total} ${__(
				"label(s)"
			)}${sheet ? ` — ${Math.ceil(total / 8)} ${__("A4 sheet(s)")}` : ""}${
				total > hcc.labels.WARN_THRESHOLD
					? ` <span style="color:var(--orange-600);font-weight:400">(${__(
							"will ask to confirm"
					  )})</span>`
					: ""
			}</div>`
		);
	};
	dialog.fields_dict.rows.grid.wrapper.on("change blur", "input", refresh_total);
	refresh_total();
	dialog.show();
};

hcc.labels.print = function (frm, rows, guides, layout) {
	frappe.call({
		method: "iso_compliance.api.labels.render_sheet",
		args: {
			doctype: frm.doctype,
			name: frm.doc.name,
			rows: JSON.stringify(rows),
			guides: guides ? 1 : 0,
			layout: layout || "a4-8",
		},
		freeze: true,
		freeze_message: __("Building the sheet…"),
		callback: (r) => {
			if (!r.message) return;
			// A real window, not an iframe: the browser's own print dialog is where
			// the paper size is chosen, and that has to be the operator's choice.
			const w = window.open("", "_blank");
			if (!w) {
				frappe.msgprint({
					title: __("Pop-up blocked"),
					message: __("Allow pop-ups for this site to open the label sheet."),
					indicator: "red",
				});
				return;
			}
			w.document.write(r.message);
			w.document.close();
		},
	});
};
