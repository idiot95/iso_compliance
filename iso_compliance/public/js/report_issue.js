// Report Issue: one button on every saved record. It opens a small form and
// creates an Issue, which then carries the NCR, corrective action and the rest
// (iso_compliance/issues/engine.py). Faults in the ERP itself go to the
// Support button instead; a failed inspection keeps its own Raise NCR button.

frappe.provide("iso_compliance.report_issue");

(function () {
	const ri = iso_compliance.report_issue;

	// set-up and system records are not something a problem is reported "on"
	ri.SKIP_MODULES = ["Core", "Desk", "Email", "Custom", "Website", "Integrations", "Automation",
		"Printing", "Workflow", "Social", "Geo", "Data Migration", "Event Streaming", "Templates"];
	ri.SKIP_DOCTYPES = ["Issue", "Issue Type", "ToDo", "ERP Ticket", "Communication"];

	ri.applies = function (frm) {
		if (!frm || !frm.doc || frm.is_new() || frm.meta.istable || frm.meta.issingle) return false;
		if (ri.SKIP_DOCTYPES.includes(frm.doctype) || ri.SKIP_MODULES.includes(frm.meta.module)) return false;
		return true;
	};

	$(document).on("form-refresh", (e, frm) => {
		if (!ri.applies(frm)) return;
		frm.add_custom_button(__("Report Issue"), () => ri.open(frm.doctype, frm.docname));
	});

	ri.open = function (doctype, name) {
		frappe.call({
			method: "iso_compliance.issues.engine.get_report_context",
			args: { doctype, name },
			freeze: true,
		}).then((r) => ri.dialog(doctype, name, r.message));
	};

	// Issue Type is nested under Area: only that area's types are offered
	ri.type_options = function (ctx, area) {
		return ["", ...ctx.types.filter((t) => t.area === area).map((t) => t.name)];
	};

	ri.item_label = function (i) {
		const parts = [i.item_code];
		if (i.item_name && i.item_name !== i.item_code) parts.push(i.item_name);
		if (i.batch) parts.push(__("Batch {0}", [i.batch]));
		if (i.qty) parts.push(__("Qty {0}", [i.qty]));
		return parts.join(" · ");
	};

	// one dialog field per fieldname, shown for the issue types that ask for it
	ri.extra_fields = function (ctx) {
		const seen = {};
		const out = [];
		Object.entries(ctx.extra_fields).forEach(([type, fields]) => {
			fields.forEach((f) => {
				const is_type = `doc.issue_type==${JSON.stringify(type)}`;
				const cond = f.mandatory_depends_on ? f.mandatory_depends_on.replace(/^eval:/, "") : f.reqd ? "true" : "";
				let df = seen[f.fieldname];
				if (!df) {
					df = seen[f.fieldname] = Object.assign({}, f, { reqd: 0, __types: [], __must: [], __labels: {} });
					delete df.on;
					out.push(df);
				}
				df.__types.push(is_type);
				df.__labels[type] = { label: f.label, description: f.description || "" };
				if (cond) df.__must.push(`(${is_type} && (${cond}))`);
			});
		});
		out.forEach((df) => {
			df.depends_on = "eval:" + df.__types.join(" || ");
			df.mandatory_depends_on = df.__must.length ? "eval:" + df.__must.join(" || ") : "";
		});
		return out;
	};

	ri.dialog = function (doctype, name, ctx) {
		const by_name = {};
		ctx.types.forEach((t) => (by_name[t.name] = t));
		const product = `eval:${JSON.stringify(ctx.product_types)}.includes(doc.issue_type)`;
		const extras = ri.extra_fields(ctx);
		const items = ctx.items;

		const d = new frappe.ui.Dialog({
			title: __("Report Issue on {0} {1}", [__(doctype), name]),
			size: "large",
			fields: [
				{ fieldname: "custom_area", fieldtype: "Select", label: __("Area"), reqd: 1,
					options: ["", ...ctx.areas], default: ctx.area },
				{ fieldtype: "Column Break" },
				{ fieldname: "issue_type", fieldtype: "Select", label: __("Issue Type"), reqd: 1,
					options: ri.type_options(ctx, ctx.area),
					description: ctx.area ? "" : __("Pick the Area first.") },
				{ fieldtype: "Column Break" },
				{ fieldname: "custom_severity", fieldtype: "Select", label: __("Severity"), reqd: 1,
					options: ["", ...ctx.severities], description: __("Sets the due times.") },
				{ fieldtype: "Section Break", hide_border: 1 },
				{ fieldname: "custom_customer_complaint", fieldtype: "Check", label: __("Customer Complaint"),
					default: ctx.complaint },
				{ fieldtype: "Section Break", label: __("Items affected"), hidden: items.length ? 0 : 1 },
				{ fieldname: "items", fieldtype: "MultiCheck", columns: 1,
					options: items.map((i, n) => ({ label: ri.item_label(i), value: String(n), checked: items.length === 1 })),
					description: items.length > 1 ? __("Tick every item the issue is about.") : "" },
				{ fieldtype: "Section Break" },
				{ fieldname: "description", fieldtype: "Small Text", label: __("Description"), reqd: 1 },
				{ fieldtype: "Section Break", hide_border: 1, depends_on: product },
				{ fieldname: "custom_batch", fieldtype: "Data", label: __("Batch / Lot") },
				{ fieldtype: "Column Break" },
				{ fieldname: "custom_qty_affected", fieldtype: "Float", label: __("Quantity Affected") },
				{ fieldtype: "Section Break", hide_border: 1 },
				...extras.map((df) => Object.assign({}, df, { default: ctx.prefill[df.fieldname] })),
				{ fieldtype: "Section Break" },
				{ fieldname: "attachment", fieldtype: "Attach", label: __("Attachment"),
					description: __("The customer's email, or a photo.") },
				{ fieldname: "next_note", fieldtype: "HTML" },
			],
			primary_action_label: __("Report"),
			primary_action(values) {
				const picked = (values.items || []).map((n) => items[cint(n)]);
				if (items.length > 1 && !picked.length && ctx.product_types.includes(values.issue_type)) {
					frappe.msgprint(__("Tick at least one item the issue is about."));
					return;
				}
				values.items = picked;
				frappe.call({
					method: "iso_compliance.issues.engine.report_issue",
					args: { doctype, name, values },
					freeze: true,
					freeze_message: __("Creating the Issue..."),
				}).then((r) => {
					d.hide();
					frappe.show_alert({ message: __("Issue {0} created", [r.message]), indicator: "green" });
					frappe.set_route("Form", "Issue", r.message);
				});
			},
		});

		const on_type = () => {
			const type = by_name[d.get_value("issue_type")];
			const tick = d.get_field("custom_customer_complaint");
			if (type && type.raised_by !== "both") {
				d.set_value("custom_customer_complaint", type.raised_by === "customer" ? 1 : 0);
				tick.df.read_only = 1;
				tick.df.description = type.raised_by === "customer"
					? __("Only a customer raises this type.") : __("This type is always internal.");
			} else {
				tick.df.read_only = 0;
				tick.df.description = "";
			}
			tick.refresh();
			extras.forEach((df) => {
				const text = type && df.__labels[type.name];
				if (!text) return;
				const field = d.get_field(df.fieldname);
				field.df.label = __(text.label);
				field.df.description = text.description ? __(text.description) : "";
				field.refresh();
			});
			d.get_field("next_note").$wrapper.html(
				type ? `<p class="text-muted small" style="margin:0">${frappe.utils.escape_html(__(type.description))}</p>` : ""
			);
		};
		d.fields_dict.issue_type.df.onchange = on_type;
		d.fields_dict.custom_area.df.onchange = () => {
			const field = d.get_field("issue_type");
			const area = d.get_value("custom_area");
			field.df.options = ri.type_options(ctx, area);
			field.df.description = area ? "" : __("Pick the Area first.");
			if (!field.df.options.includes(d.get_value("issue_type"))) d.set_value("issue_type", "");
			field.refresh();
		};
		// one ticked item with a batch fills Batch / Lot
		d.fields_dict.items.$wrapper.on("change", "input", () => {
			const picked = (d.get_value("items") || []).map((n) => items[cint(n)]);
			if (picked.length === 1 && picked[0].batch) d.set_value("custom_batch", picked[0].batch);
		});
		if (items.length === 1 && items[0].batch) d.set_value("custom_batch", items[0].batch);
		// A section whose fields were all hidden stays collapsed after its fields
		// appear (the Supplier, Asset and other per-type questions), so re-check
		// the sections after every change.
		const resections = () => setTimeout(() => {
			d.refresh_dependency();
			d.refresh_sections && d.refresh_sections();
		}, 200);
		d.$wrapper.on("change", "input, select, textarea", resections);
		d.show();
		resections();
	};
})();
