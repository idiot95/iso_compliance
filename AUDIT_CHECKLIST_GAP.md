# Master Audit Checklist vs REG-001

Comparison of the customer's Master Audit Checklist against the document set
recorded in REG-001. Run on 2026-08-05.

## Headline

| | Checklist requires | REG-001 has |
| --- | --- | --- |
| Procedures | 38 | 18 SOPs + 15 Work Instructions |
| Records | 79 | 31 Forms + 26 Registers |

Roughly **17 of the 38 required procedures** have a clear equivalent in REG-001,
and **41 of the 79 required records** map onto an existing form or register.

## The checklist is not an ISO 9001 checklist

Items 29 to 34 are ISO 14001 (environmental) and ISO 45001 (occupational health
and safety):

- Environmental Management, Environmental Aspect & Impact Assessment, Waste Management
- Occupational Health & Safety, Hazard Identification & Risk Assessment (HIRA),
  Emergency Preparedness & Response

with matching records: Environmental Aspect Register, Waste Disposal Records,
Environmental Monitoring Reports, HIRA Register, PPE Issue Register, Safety
Training Records, Incident/Near Miss Register, Emergency Drill Reports, Medical
Examination Records.

REG-001 addresses none of this, because REG-001 is a 9001 document set. This is a
scope question for the business, not a documentation gap to close quietly: it
either means the customer expects 14001 and 45001 certification, or the checklist
is a generic supplier questionnaire that needs sections marked not applicable.
**Confirm before writing 6 procedures and 9 registers nobody asked for.**

## Procedures with no equivalent in REG-001

Within 9001 scope:

| Checklist procedure | Note |
| --- | --- |
| Management Responsibility & Leadership | POL-001/POL-002 are policies, not procedures |
| Organization Roles & Responsibilities | REG-013 is a register; no governing procedure |
| Customer Complaint Handling | REG-008 and FRM-028 exist as records only |
| Customer Specification & Drawing Control | REG-026 exists as a record only |
| Subcontractor Control | nothing |
| Work Instruction Control | SOP-001 covers documents generally |
| Special Process Control (welding, heat treatment, coating) | nothing |
| NDT | nothing |
| Control of Customer Property & Confidential Information | nothing |
| Change Management | FRM-001 exists as a form; now also a DocType |

Out of 9001 scope: the six environmental and OH&S procedures listed above.

## Records with no equivalent

The substantive clusters, beyond the environmental and OH&S ones:

- **Special process**: WPS, PQR, Welder Qualification, Heat Treatment Records,
  Coating Inspection Reports
- **Inspection depth**: Material Test Certificates (MTC), Inspection & Test Plan
  (ITP), NDT Reports, MSA Records
- **Manufacturing**: Route Card, Production Log Sheet, Production Planning Sheet,
  Production Capacity Plan
- **Nonconformity**: Rework Records, Scrap Records
- **Code of conduct**: Acknowledgement, Ethics Training, Supplier CoC Acceptance
- **Document control**: Master List of Records, Document Distribution List,
  Standards Register

Note that several apparent gaps are false alarms: Quality Policy is POL-001,
Approved Supplier List is REG-007, Non-Conforming Product Register is REG-009,
and Document Revision History is now the Change History sheet this app produces.

## What this changes

Nothing in REG-001 is wrong. The checklist is simply a wider scope than the
document set was built for, and it leans toward fabricated/welded steel supply
(NDT, WPS, PQR, heat treatment) rather than carbon brush manufacture. Some of it
may genuinely not apply.

The order of work that follows from this:

1. Confirm whether 14001 and 45001 are in scope.
2. Confirm which special-process items apply to what HCCPL actually makes.
3. Only then extend REG-001, so the register does not acquire another 40 entries
   marked Active with no document behind them.
