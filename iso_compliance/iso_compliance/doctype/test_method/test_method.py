# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""A test performed the same way on many parts (mV drop, hardness, HV withstand…).
Defined once here; template rows point at it and may override its set values."""

import frappe
from frappe.model.document import Document


class TestMethod(Document):
	pass
