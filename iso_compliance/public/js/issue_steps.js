// An Issue raised through Report Issue is laid out as steps, the way the Sales
// Order and the Techno-Commercial Review are: each step is one of the form's own
// tabs, numbered, with a tick once filed; the current step's number is dark and
// its name bold; a line above the tabs says whose turn it is. The answers are the
// Issue's own fields and Save is Frappe's own. The dark button files the step and
// hands the Issue to the next person (iso_compliance/issues/engine.py).
// An Issue typed in by hand or received by email keeps the plain form.

frappe.provide("iso_compliance.issue_steps");

(function () {
	const st = iso_compliance.issue_steps;
	const ENGINE = "iso_compliance.issues.engine.";
	const MAIL = "iso_compliance.issues.mail.";
	const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));

	// Standard Issue fields that say nothing about a reported issue.
	st.NOISE = ["priority", "issue_split_from", "service_level_section", "response", "additional_info",
		"section_break_19", "custom_sales_order", "custom_root_cause"];

	st.styles = function () {
		if (document.getElementById("ri-form-styles")) return;
		const css = `
	.ri-form .form-tabs .ri-step { display: inline-flex; align-items: center; gap: 6px; padding: 2px 0; border-radius: 999px; }
	.ri-form .form-tabs .ri-step__dot { width: 18px; height: 18px; border-radius: 50%; display: inline-flex; align-items: center;
		justify-content: center; font-size: 11px; font-weight: 600; background: var(--gray-200); color: var(--text-muted); }
	.ri-form .form-tabs .ri-step--done .ri-step__dot { background: var(--green-500); color: var(--white); }
	.ri-form .form-tabs .ri-step--now .ri-step { font-weight: 600; color: var(--text-color); }
	.ri-form .form-tabs .ri-step--now .ri-step__dot { background: var(--text-color); color: var(--bg-color); }
	.ri-form .form-tabs .ri-step--todo { color: var(--text-muted); }
	.ri-plain .form-tabs-list { display: none; }
	.ri-form .form-tab-content .form-section .section-head { font-size: var(--text-lg); font-weight: 600; color: var(--text-color);
		padding-bottom: 6px; margin-bottom: 4px; border-bottom: 2px solid var(--gray-300); }
	.ri-form .ri-tip { display: inline-flex; align-items: center; justify-content: center; width: 15px; height: 15px; margin-left: 5px;
		border-radius: 50%; border: 1px solid var(--gray-500); color: var(--text-muted); font-size: 10px; font-weight: 600;
		line-height: 1; cursor: help; vertical-align: 1px; }
	.ri-form .ri-tip:hover, .ri-form .ri-tip:focus { color: var(--text-color); border-color: var(--text-color); outline: none; }
	.ri-form .page-head .standard-actions .btn { white-space: nowrap; flex-shrink: 0; }
	.ri-form .page-head .title-area { min-width: 0; }
	.ri-form .ri-guide { font-size: var(--text-sm); color: var(--text-muted); line-height: 1.7; }
	.ri-form .ri-guide b { color: var(--text-color); font-weight: 500; }
	.ri-form .ri-sum { background: var(--subtle-fg); border: 1px solid var(--border-color); border-radius: var(--border-radius-md);
		padding: 10px 12px; margin-bottom: 12px; font-size: var(--text-sm); color: var(--text-color); }
	.ri-form .ri-sum .ri-sum__meta { color: var(--text-muted); margin-bottom: 4px; }
	.ri-form .ri-who { display: flex; justify-content: space-between; gap: 12px; align-items: baseline; }
	.ri-form .ri-who b { font-size: var(--text-base); color: var(--text-color); }
	.ri-form .ri-who span, .ri-form .ri-note { font-size: var(--text-sm); color: var(--text-muted); }
	.ri-form .ri-note { margin: 4px 0 0; }
	.ri-form .control-label.ri-reqd::after { content: " *"; color: var(--red-500); }
	.ri-form .ri-card { border: 1px solid var(--border-color); border-radius: var(--border-radius-md); padding: 10px 12px; margin-bottom: 8px;
		display: flex; justify-content: space-between; gap: 12px; align-items: center; }
	.ri-form .ri-card--on { border-color: var(--text-color); }
	.ri-form .ri-card .ri-card__sub { font-size: var(--text-sm); color: var(--text-muted); overflow-wrap: anywhere; }
	.ri-form .ri-thread-tools { display: flex; gap: 8px; margin: 8px 0; flex-wrap: wrap; }
	.ri-form .ri-thread-tools input { max-width: 320px; }
	.ri-form table.ri-actions { width: 100%; font-size: var(--text-sm); }
	.ri-form table.ri-actions th { color: var(--text-muted); font-weight: 500; padding: 6px 8px; background: var(--subtle-fg); }
	.ri-form table.ri-actions td { padding: 8px; border-top: 1px solid var(--border-color); vertical-align: middle; }
	`;
		$("<style>").attr("id", "ri-form-styles").text(css).appendTo("head");
	};

	st.plain = function (frm) {
		$(frm.wrapper).removeClass("ri-form").addClass("ri-plain");
	};

	st.dot = function ($link, state, n, label) {
		$link.removeClass("ri-step--done ri-step--now ri-step--todo").addClass(`ri-step--${state}`)
			.html(`<span class="ri-step"><span class="ri-step__dot">${state === "done" ? "✓" : n}</span>${esc(label)}</span>`);
	};

	st.tip = function (frm, fieldname, text) {
		const field = frm.fields_dict[fieldname];
		if (!field || !text) return;
		const $label = field.$wrapper.find(".control-label").first();
		if (!$label.length) return;
		field.$wrapper.find(".ri-tip").remove();
		// hover on a desktop, tap on a phone
		$('<span class="ri-tip" tabindex="0" role="button">i</span>')
			.attr("title", __(text)).attr("aria-label", __(text))
			.insertAfter($label)
			.tooltip({ trigger: "hover focus", placement: "top", container: "body" });
	};

	st.summary = function (frm) {
		const d = frm.doc;
		const ref = d.custom_reported_name
			? `<a href="${frappe.utils.get_form_link(d.custom_reported_doctype, d.custom_reported_name)}">${esc(__(d.custom_reported_doctype))} ${esc(d.custom_reported_name)}</a>` : "";
		const meta = [ref, esc(d.issue_type), d.customer ? `<b>${esc(d.customer_name || d.customer)}</b>` : esc(frappe.user.full_name(d.owner)),
			esc(d.custom_item_group), d.custom_severity ? esc(d.custom_severity) : ""].filter(Boolean).join(" · ");
		const text = frappe.utils.html2text ? frappe.utils.html2text(d.description || "") : $("<div>").html(d.description || "").text();
		return `<div class="ri-sum"><div class="ri-sum__meta">${meta}</div>${esc(text.trim()).replace(/\n/g, "<br>")}</div>`;
	};

	st.render = function (frm, state) {
		if (!frm.layout || !frm.layout.tabs) return;
		st.styles();
		$(frm.wrapper).addClass("ri-form").removeClass("ri-plain");
		frm.layout.show_message();
		frm.layout.show_message(`<div>${esc(state.headline.text)}</div>`, state.headline.color, true);
		frm.toggle_display(st.NOISE, false);
		// ERPNext's own Close and Create > Task would step around the route.
		frm.remove_custom_button(__("Close"));
		frm.remove_custom_button(__("Reopen"));
		frm.remove_custom_button(__("Task"), __("Create"));
		const guide = frm.fields_dict.custom_disposition_help;
		if (guide) guide.$wrapper.addClass("ri-guide");

		const cur = state.steps.find((s) => s.key === state.current);
		const mine = state.can_act && cur ? cur : null;
		const open_fields = mine ? mine.fields.map((f) => f.fieldname) : [];

		// who may type where: only the current step, only its owner
		state.all_fields.forEach((fn) => {
			const field = frm.fields_dict[fn];
			if (!field) return;
			frm.set_df_property(fn, "read_only", open_fields.includes(fn) ? 0 : 1);
			field.$wrapper.find(".control-label").removeClass("ri-reqd");
		});
		if (mine) {
			mine.fields.forEach((f) => {
				const field = frm.fields_dict[f.fieldname];
				const must = f.reqd || (f.must && frappe.utils.eval(f.must.replace(/^eval:/, ""), { doc: frm.doc }));
				if (field && must) field.$wrapper.find(".control-label").addClass("ri-reqd");
			});
			if (state.ca_forced) {
				["custom_ca_needed", "custom_ca_reason"].forEach((fn) => frm.set_df_property(fn, "read_only", 1));
			}
		}
		// an (i) beside every step field: what it is, and where it shows or what it changes
		state.steps.forEach((s) => s.fields.forEach((f) => st.tip(frm, f.fieldname, f.tip)));

		// what was reported is fixed once it is reported
		["subject", "status", "customer", "issue_type", "description", "custom_severity", "custom_batch", "custom_qty_affected"]
			.forEach((fn) => frm.set_df_property(fn, "read_only", 1));

		// the tabs
		st.dot(frm.layout.tabs[0].tab_link.find(".nav-link"), "done", 1, __("Log Issue"));
		const sum = st.summary(frm);
		state.steps.forEach((s) => {
			if (!s.tab) return;
			const tab = frm.layout.tabs.find((t) => t.df.fieldname === s.tab);
			if (!tab) return;
			const tab_state = s.status === "done" ? "done" : s.status === "current" ? "now" : "todo";
			st.dot(tab.tab_link.find(".nav-link"), tab_state, s.idx, __(s.label));

			const whose = __(s.owner_label || "owner");
			const head = tab_state === "done" ? __("Filled by the {0}", [whose])
				: tab_state === "now" ? __("To be filled by the {0}", [whose]) : __("Will be filled by the {0}", [whose]);
			const meta = tab_state === "done" ? `${esc(s.by || "")} · ${esc(frappe.datetime.str_to_user(s.on).slice(0, 10))}`
				: tab_state === "now" && s.due ? __("due {0}", [frappe.datetime.str_to_user(s.due)]) : "";
			const notes = [];
			if (s.help && tab_state !== "done") notes.push(esc(__(s.help)));
			if (tab_state === "now" && state.ca_forced) notes.push(__("Corrective Action Needed is set to Yes for you: {0}", [esc(state.ca_forced)]));
			const $intro = frm.fields_dict[s.intro] && frm.fields_dict[s.intro].$wrapper;
			if (!$intro) return;
			$intro.html(`${sum}<div class="ri-who"><b>${esc(head)}</b><span>${meta}</span></div>${notes.map((n) => `<p class="ri-note">${n}</p>`).join("")}`);
			if (s === mine && s.create) {
				$(`<button type="button" class="btn btn-default btn-sm" style="margin-top:8px">${__("Create {0}", [__(s.create)])}</button>`)
					.appendTo($intro)
					.on("click", () => frappe.new_doc(s.create, { supplier: frm.doc.custom_supplier, asset: frm.doc.custom_asset, failure_date: frm.doc.creation }));
			}
		});

		// The actions table is ERPNext's own child table: name its first column
		// for what it holds here, and leave out the notes column.
		const grid = frm.fields_dict.custom_actions && frm.fields_dict.custom_actions.grid;
		if (grid && !grid.__ri) {
			grid.__ri = true;
			grid.update_docfield_property("problem", "label", __("Action"));
			grid.update_docfield_property("resolution", "in_list_view", 0);
			grid.update_docfield_property("problem", "columns", 4);
			grid.reset_grid && grid.reset_grid();
		}

		st.thread(frm, state, mine && mine.key === "email");
		st.thread_note(frm, state);
		st.actions(frm, state, "custom_actions_html");
		st.actions(frm, state, "custom_check_actions_html");

		// The dark button files the step (saving first); Save, or Ctrl+S, keeps
		// what is typed. Frappe swaps in its own Save as soon as the form is edited,
		// so the buttons are put back after every edit.
		frm.__ri_buttons = () => {
			if (!frm.doc.custom_steps) return;
			if (mine) {
				frm.page.set_primary_action(__(mine.action || "Done"), () => st.file(frm, mine));
				frm.page.set_secondary_action(__("Save"), () => frm.save());
			} else {
				frm.page.clear_primary_action();
				frm.page.clear_secondary_action();
			}
		};
		frm.__ri_buttons();
		if (!frm.__ri_bound) {
			frm.__ri_bound = true;
			$(frm.wrapper).on("dirty", () => setTimeout(() => frm.__ri_buttons && frm.__ri_buttons(), 0));
		}

		// Opens on the current step the first time this Issue is shown.
		if (frm.__ri_opened !== frm.doc.name + ":" + state.current) {
			frm.__ri_opened = frm.doc.name + ":" + state.current;
			const last = state.steps.filter((s) => s.tab).pop();
			frm.layout.select_tab(cur && cur.tab ? cur.tab : last ? last.tab : frm.layout.tabs[0].df.fieldname);
		}
	};

	st.file = async function (frm, step) {
		if (frm.is_dirty()) await frm.save();
		if (frm.is_dirty()) return; // the save was refused
		const r = await frappe.xcall(ENGINE + "complete_step", { issue: frm.doc.name, step: step.key }, "POST", { freeze: true });
		const mail = r && r.mail;
		let text = r.owner ? __("Handed over: {0} is now with {1}", [__(r.step), frappe.user.full_name(r.owner)]) : __("Issue closed");
		if (mail && mail.via === "outlook") text = __("Sent in the customer's Outlook thread.") + " " + text;
		if (mail && mail.via === "frappe") text = __("Emailed from the site's own email account.") + " " + text;
		if (mail && mail.via === "record") text = __("Recorded on the Issue, not emailed: this site cannot send email.") + " " + text;
		frappe.show_alert({ message: text, indicator: mail && !mail.sent ? "orange" : "green" }, 8);
		frm.__ri_opened = null;
		frm.reload_doc();
	};

	// ---------------------------------------------------------- email thread
	st.thread = function (frm, state, mine) {
		const field = frm.fields_dict.custom_thread_html;
		if (!field) return;
		const $w = field.$wrapper.empty();
		const d = frm.doc;
		const m = state.mail;
		const chosen = d.custom_thread_conversation
			? `<div class="ri-card ri-card--on"><div><div><b>${esc(d.custom_thread_subject || __("(no subject)"))}</b></div>
				<div class="ri-card__sub">${esc(d.custom_thread_people || "")}</div></div>
				${mine && m.connected ? `<button type="button" class="btn btn-default btn-xs ri-change">${__("Change")}</button>` : ""}</div>` : "";
		if (!m.outlook) {
			$w.html(`<p class="ri-note">${m.outgoing
				? __("Outlook is not set up on this site, so this goes as a new email from the site's own email account.")
				: __("Outlook is not set up on this site and it has no outgoing email account. The message will be recorded on the Issue but not sent.")}</p>`);
			return;
		}
		if (!m.connected) {
			$w.html(`${chosen}<p class="ri-note">${__("Connect your Microsoft 365 mailbox once, so the reply goes into the customer's own Outlook thread. You will sign in on Microsoft's page and come back here.")}</p>`);
			if (mine) {
				$(`<button type="button" class="btn btn-primary btn-sm" style="margin-top:8px">${__("Connect Outlook")}</button>`).appendTo($w)
					.on("click", async () => { window.location = await frappe.xcall(MAIL + "connect_url", { issue: d.name }); });
			}
			return;
		}
		$w.html(`<label class="control-label">${__("Reply in this email thread")}</label>${chosen
			|| `<p class="ri-note">${mine ? __("Pick the customer's email below. The reply goes to everyone on it.") : __("No thread picked yet.")}</p>`}
			<div class="ri-thread-pick"></div>`);
		if (!mine) return;
		const $pick = $w.find(".ri-thread-pick");
		const choose = async (thread) => {
			await frappe.xcall(MAIL + "choose_thread", { issue: d.name, thread: thread ? JSON.stringify(thread) : null });
			frm.reload_doc();
		};
		const search = async (query) => {
			$pick.html(`<p class="ri-note">${__("Looking in Outlook...")}</p>`);
			let r;
			try {
				r = await frappe.xcall(MAIL + "find_threads", { issue: d.name, query: query || null });
			} catch {
				$pick.html(`<p class="ri-note">${__("Outlook could not be searched.")}</p>`);
				return;
			}
			const cards = r.threads.map((t, i) => `<div class="ri-card"><div><div><b>${esc(t.subject)}</b> <span class="text-muted">· ${esc(t.from_name)} · ${esc(frappe.datetime.str_to_user(t.received).slice(0, 10))}</span></div>
				<div class="ri-card__sub">${esc(t.preview)}</div></div>
				<button type="button" class="btn btn-default btn-xs ri-pick" data-i="${i}">${__("Reply here")}</button></div>`).join("");
			$pick.html(`<div class="ri-thread-tools"><input type="text" class="form-control input-sm" placeholder="${__("Search Outlook: subject, sender or PO number")}" value="${esc(query || "")}">
				<button type="button" class="btn btn-default btn-sm ri-search">${__("Search")}</button>
				<button type="button" class="btn btn-default btn-sm ri-new">${__("New email instead")}</button></div>
				${cards || `<p class="ri-note">${__("No conversation found for {0}.", [esc(r.searched_for.join(", "))])}</p>`}`);
			$pick.find(".ri-search").on("click", () => search($pick.find("input").val().trim()));
			$pick.find("input").on("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); search(e.target.value.trim()); } });
			$pick.find(".ri-new").on("click", () => choose(null));
			$pick.find(".ri-pick").on("click", (e) => choose(r.threads[cint($(e.currentTarget).data("i"))]));
		};
		$w.find(".ri-change").on("click", () => search());
		if (!d.custom_thread_conversation && !d.custom_reply_to) search();
	};

	// The Outcome is an email too: say which thread it goes into, and to whom.
	st.thread_note = function (frm, state) {
		const field = frm.fields_dict.custom_outcome_thread_html;
		if (!field) return;
		const d = frm.doc;
		const m = state.mail;
		let html;
		if (d.custom_thread_conversation && m.connected) {
			html = `<label class="control-label">${__("Goes as a reply in this email thread")}</label>
				<div class="ri-card ri-card--on"><div><div><b>${esc(d.custom_thread_subject || __("(no subject)"))}</b></div>
				<div class="ri-card__sub">${__("To")}: ${esc(d.custom_thread_people || d.custom_customer_email || "")}</div></div></div>`;
		} else if (m.outlook && !m.connected) {
			html = `<p class="ri-note">${__("Connect your Outlook on the Email Reply tab's button, or this goes as a plain email from the site.")}</p>`;
		} else {
			const to = esc(d.custom_customer_email || __("the customer's contact"));
			html = `<p class="ri-note">${m.outgoing ? __("Goes as an email to {0} from the site's own email account.", [to])
				: __("To {0}. This site cannot send email, so the message will be recorded on the Issue but not sent.", [to])}</p>`;
		}
		field.$wrapper.html(html);
	};

	// ------------------------------------------------- the corrective actions
	st.actions = function (frm, state, fieldname) {
		const field = frm.fields_dict[fieldname];
		if (!field) return;
		const rows = frm.doc.custom_actions || [];
		if (!rows.length) {
			field.$wrapper.html(`<p class="ri-note">${__("No actions yet. They are listed at RCA and CAPA.")}</p>`);
			return;
		}
		const cur = state.steps.find((s) => s.key === state.current);
		const body = rows.map((r) => {
			const may = r.status !== "Completed" && (r.responsible === frappe.session.user || (state.can_act && cur));
			return `<tr><td>${r.idx}</td><td>${esc($("<div>").html(r.problem || "").text())}</td>
				<td>${esc(frappe.user.full_name(r.responsible))}</td><td>${esc(frappe.datetime.str_to_user(r.completion_by) || "")}</td>
				<td>${r.status === "Completed" ? `<span class="indicator-pill green">${__("Completed")}</span>`
					: may ? `<button type="button" class="btn btn-default btn-xs ri-done" data-idx="${r.idx}">${__("Mark Completed")}</button>`
					: `<span class="indicator-pill orange">${__("Open")}</span>`}</td></tr>`;
		}).join("");
		field.$wrapper.html(`<table class="ri-actions"><thead><tr><th>${__("No.")}</th><th>${__("Action")}</th><th>${__("Responsible")}</th>
			<th>${__("Completion By")}</th><th>${__("Status")}</th></tr></thead><tbody>${body}</tbody></table>`);
		field.$wrapper.find(".ri-done").on("click", async (e) => {
			if (frm.is_dirty()) await frm.save();
			await frappe.xcall(ENGINE + "mark_action_done", { issue: frm.doc.name, idx: $(e.currentTarget).data("idx") });
			frm.reload_doc();
		});
	};

	frappe.ui.form.on("Issue", {
		refresh(frm) {
			if (frm.is_new() || !frm.doc.custom_steps) return st.plain(frm);
			const name = frm.doc.name;
			frappe.xcall(ENGINE + "get_state", { issue: name }).then((state) => {
				if (state && frm.doc.name === name) st.render(frm, state);
			});
		},
	});
})();
