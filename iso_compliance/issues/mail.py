# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Email on an Issue goes into the customer's own Outlook conversation.

The customer's complaint arrives in Outlook, not in ERPNext, so the reply is
made the way the Shipment's dispatch email is made (hcc_erp_edits/dispatch.py,
whose Microsoft Graph helpers this file borrows): the sender's own Outlook
token, the customer's thread found by their contacts and PO number, and
Graph's createReplyAll, so the reply carries the thread's headers and sits in
the sender's Sent Items. The Issue remembers the conversation; the Outcome
step replies into the same one.

Nobody is asked for the customer's email address up front: a reply goes to
everyone on the thread. Only a brand-new email (no thread picked) asks for To.

Where Outlook is not set up (the local copy, or hcc_erp_edits missing) the
message is recorded on the Issue as a Communication, and sent only if the site
has a default outgoing email account.
"""

import json

import frappe
from frappe import _
from frappe.utils import escape_html


def _dispatch():
	try:
		return frappe.get_module("hcc_erp_edits.dispatch")
	except Exception:
		return None


def status():
	d = _dispatch()
	outlook = bool(d and d._connected_app_name())
	return {"outlook": outlook, "connected": bool(outlook and d._is_connected()),
	        "outgoing": bool(frappe.db.exists("Email Account", {"enable_outgoing": 1, "default_outgoing": 1}))}


@frappe.whitelist()
def connect_url(issue):
	return _dispatch().connect_url(return_to=f"/app/issue/{issue}")


def customer_emails(doc, limit=6):
	emails = [doc.custom_customer_email] if doc.get("custom_customer_email") else []
	if doc.get("customer"):
		emails.append(frappe.db.get_value("Customer", doc.customer, "email_id"))
		links = frappe.get_all("Dynamic Link", pluck="parent",
		                       filters={"parenttype": "Contact", "link_doctype": "Customer", "link_name": doc.customer})
		if links:
			emails += frappe.get_all("Contact Email", filters={"parent": ["in", links]}, pluck="email_id",
			                         order_by="is_primary desc")
	return list(dict.fromkeys(e.strip().lower() for e in emails if e and e.strip()))[:limit]


def references(doc):
	"""What the customer's emails are likely to quote: their PO numbers and our document."""
	refs = []
	for dt, name in ((doc.get("custom_reported_doctype"), doc.get("custom_reported_name")),
	                 ("Sales Order", doc.get("custom_sales_order"))):
		if dt and name and frappe.get_meta(dt).has_field("po_no"):
			po = frappe.db.get_value(dt, name, "po_no")
			if po:
				refs.append((f'"{po}"', _("PO {0}").format(po)))
	if doc.get("custom_reported_name"):
		refs.append((f'"{doc.custom_reported_name}"', doc.custom_reported_name))
	return list(dict.fromkeys(refs))


@frappe.whitelist()
def find_threads(issue, query=None):
	"""The customer's conversations in the sender's own and the shared mailboxes,
	newest first. Same shape as the dispatch email's thread search."""
	doc = frappe.get_doc("Issue", issue)
	doc.check_permission("read")
	d = _dispatch()
	session = d._session()
	query = (query or "").replace('"', " ").strip()
	if query:
		queries = [(f'"{query}"', query)]
	else:
		queries = references(doc) + [(f'"participants:{e}"', e) for e in customer_emails(doc)]
	mailboxes, merged = [], {}
	for mailbox, label, address in d._mailboxes():
		found, state = d._search(session, mailbox, queries) if queries else ({}, "ok")
		mailboxes.append({"mailbox": mailbox, "label": label, "address": address, "status": state, "count": len(found)})
		for conv, thread in found.items():
			thread["mailbox_label"] = label
			have = merged.get(conv)
			if not have or thread["received"] > have["received"]:
				merged[conv] = thread
	threads = sorted(merged.values(), key=lambda t: t["received"], reverse=True)[:20]
	for t in threads:
		t["last_used"] = bool(doc.custom_thread_conversation and t["conversation_id"] == doc.custom_thread_conversation)
	return {"threads": threads, "mailboxes": mailboxes, "searched_for": [m for _q, m in queries], "custom": bool(query)}


@frappe.whitelist()
def choose_thread(issue, thread=None):
	"""Remember the conversation to reply in (or none: a new email)."""
	from iso_compliance.issues import engine

	doc = frappe.get_doc("Issue", issue)
	engine.require_turn(doc, "email")
	t = frappe._dict(frappe.parse_json(thread) if thread else {})
	values = {
		"custom_thread_conversation": t.conversation_id,
		"custom_thread_mailbox": t.mailbox,
		"custom_thread_message": t.id,
		"custom_thread_subject": (t.subject or "")[:140] or None,
		"custom_thread_people": ", ".join(t.participants or []) or None,
	}
	if t.get("from"):
		values["custom_customer_email"] = t["from"]
	frappe.db.set_value("Issue", issue, values, update_modified=False)
	return values


def _latest(d, session, base, doc):
	"""The newest message of the Issue's conversation, so a later reply (the
	outcome) answers the customer's last word, not the first email."""
	try:
		res = session.get(f"{base}/messages", timeout=60, params={
			"$filter": f"conversationId eq '{doc.custom_thread_conversation}'",
			"$select": "id,receivedDateTime,isDraft", "$top": "50"})
		rows = [m for m in res.json().get("value", []) if not m.get("isDraft")] if res.status_code < 400 else []
		if rows:
			return max(rows, key=lambda m: m["receivedDateTime"])["id"]
	except Exception:
		pass
	return doc.custom_thread_message


def _file(url):
	if not url:
		return None
	name = frappe.db.get_value("File", {"file_url": url}, "name", order_by="creation desc")
	if not name:
		return None
	file = frappe.get_doc("File", name)
	return file.file_name, file.get_content()


def send(doc, body, to=None, cc=None, attachment=None, pdfs=None, subject=None):
	"""Send `body` on the Issue's thread. Returns {"via", "sent", "subject"}."""
	body = body or ""
	files = [f for f in [_file(attachment)] if f] + list(pdfs or [])
	state = status()
	if not state["connected"]:
		return _fallback(doc, body, to, cc, attachment, subject, state)

	d = _dispatch()
	session = d._session()
	mailbox = doc.custom_thread_mailbox or "me"
	base = d._base(mailbox)
	if doc.custom_thread_conversation:
		draft = d._graph(session, "POST", f"{base}/messages/{_latest(d, session, base, doc)}/createReplyAll")
		patch = {"body": {"contentType": "HTML", "content": d._prepend(body, (draft.get("body") or {}).get("content", ""))}}
		if d._recipients(cc):
			patch["ccRecipients"] = (draft.get("ccRecipients") or []) + d._recipients(cc)
		d._graph(session, "PATCH", f"{base}/messages/{draft['id']}", json=patch)
	else:
		if not d._recipients(to):
			frappe.throw(_("Pick the customer's email thread, or enter To for a new email."))
		draft = d._graph(session, "POST", f"{base}/messages", json={
			"subject": subject or _("{0} ({1})").format(doc.subject, doc.name),
			"body": {"contentType": "HTML", "content": body},
			"toRecipients": d._recipients(to), "ccRecipients": d._recipients(cc)})
	for name, data in files:
		d._attach(session, base, draft["id"], name, data)
	view = d._graph(session, "GET", f"{base}/messages/{draft['id']}",
	                params={"$select": "subject,toRecipients,ccRecipients,from,conversationId"})
	d._graph(session, "POST", f"{base}/messages/{draft['id']}/send")

	addr = lambda rows: ", ".join(((r.get("emailAddress") or {}).get("address") or "") for r in rows or [])
	sender = ((view.get("from") or {}).get("emailAddress") or {}).get("address") or frappe.db.get_value("User", frappe.session.user, "email")
	_log(doc, view.get("subject"), body, sender, addr(view.get("toRecipients")), addr(view.get("ccRecipients")),
	     [n for n, _b in files], _("Sent from Outlook via ERPNext"), "Sent")
	if not doc.custom_thread_conversation:
		doc.custom_thread_conversation = view.get("conversationId")
		doc.custom_thread_mailbox = mailbox
		doc.custom_thread_subject = (view.get("subject") or "")[:140]
		doc.custom_thread_people = addr(view.get("toRecipients"))
	_remember(doc, addr(view.get("toRecipients")))
	return {"via": "outlook", "sent": True, "subject": view.get("subject")}


def _fallback(doc, body, to, cc, attachment, subject, state):
	to = to or (customer_emails(doc) or [None])[0]
	if not to:
		frappe.throw(_("Enter To: the customer's email address."))
	subject = subject or _("Re: {0} ({1})").format(doc.custom_thread_subject or doc.subject, doc.name)
	if state["outgoing"]:
		from frappe.core.doctype.communication.email import make

		file = frappe.db.get_value("File", {"file_url": attachment}, "name") if attachment else None
		make(doctype="Issue", name=doc.name, content=body, subject=subject, recipients=to, cc=cc,
		     send_email=True, attachments=[file] if file else None)
	else:
		_log(doc, subject, body, frappe.db.get_value("User", frappe.session.user, "email"), to, cc, [], _("Recorded only: this site cannot send email"), "")
	_remember(doc, to)
	return {"via": "frappe" if state["outgoing"] else "record", "sent": bool(state["outgoing"]), "subject": subject}


def _remember(doc, recipients):
	"""ERPNext fills Raised By with whoever typed the Issue; once we have written
	to the customer, it is the customer."""
	first = (recipients or "").replace(";", ",").split(",")[0].strip()
	if first and not doc.get("custom_customer_email"):
		doc.custom_customer_email = first
	if doc.get("custom_customer_email"):
		doc.raised_by = doc.custom_customer_email


def _log(doc, subject, body, sender, to, cc, filenames, note, delivery):
	listing = "".join(f"<li>{escape_html(n)}</li>" for n in filenames)
	attached = f"<p><b>{_('Attached')}:</b></p><ul>{listing}</ul>" if listing else ""
	comm = frappe.get_doc({
		"doctype": "Communication", "communication_type": "Communication", "communication_medium": "Email",
		"sent_or_received": "Sent", "subject": subject or doc.subject,
		"content": f"{body}<hr>{attached}<p class='text-muted'>{note}</p>",
		"sender": sender, "recipients": to, "cc": cc,
		"reference_doctype": "Issue", "reference_name": doc.name, "status": "Linked",
		"delivery_status": delivery,
	})
	if doc.get("custom_sales_order"):
		comm.append("timeline_links", {"link_doctype": "Sales Order", "link_name": doc.custom_sales_order})
	comm.flags.ignore_permissions = True
	comm.insert(ignore_permissions=True)
