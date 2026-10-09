# How to write an SOP

An SOP is read by someone who has a job to do now: a storekeeper with a truck
at the gate, a sales executive with an order to accept, an auditor with a
clause to check. They should understand it in two minutes and find their own
step in ten seconds. If the text needs a second read, it isn't finished.

## The shape: the same for every SOP

| Section | What goes in it | Length |
| --- | --- | --- |
| **Purpose** | Why the process exists, in one sentence. | 1 line |
| **Scope** | What it covers, and what it doesn't if that's unclear. | 1 line |
| **Workflow** | The process as a chain of steps: `Receipt → Inspection → Accept / Reject → Store`. | 1 line |
| **Who does what** | One row per position: the job title from the org chart, not a department. | 1 line per role |
| **Procedure** | One row per step: **Activity · Who · What happens · In ERPNext**. | 1–3 short sentences per step |
| **Records** | The forms and registers the process produces. | list |
| **References** | The ISO clause, and any document it depends on. | list |
| **Definitions** | Only words a new employee wouldn't know (MTC, LD, CAPA). | usually 0–3 |

The print follows this order and numbers the sections itself.

## Rules for the text

1. **One step, one action.** "Quality inspects the material" is a step. A step
   that needs "and then" is two steps.
2. **Name who does it.** Use the position (Sales Executive, Quality Manager),
   not "the concerned department" and not "personnel".
3. **Say where it happens.** Every step that leaves a record names the ERPNext
   screen: *Purchase Receipt*, *Quality Inspection (FRM-006)*. If a step happens
   only on paper or on the shop floor, say so: *on the shop floor*.
4. **Say what the system enforces.** If ERPNext blocks something, the SOP says
   so plainly: "A Sales Order of ₹5 lakh or more can't be submitted without
   it." People trust a rule they can see work.
5. **Short words, present tense, active voice.** "Stores checks the challan",
   not "The delivery challan shall be verified by the Stores Department".
6. **No padding.** Cut these on sight: *shall be ensured that*, *as applicable*,
   *in a timely manner*, *appropriate*, *systematic*, *effective*, *robust*,
   *wherever necessary*, *etc.* If the condition matters, state it: *where the
   item group requires one*.
7. **No lists of everything.** "Training may include technical, quality,
   safety, process…" tells nobody what to do. Name what's actually checked, or
   leave it out.
8. **Only cite documents that exist.** Never write a form number that isn't in
   REG-001. Transactional records (quotation, purchase order, customer PO) are
   ERPNext screens, not controlled forms.
9. **Promise only what you can show.** An auditor will ask for the evidence of
   each step. If there's no record, the step must say where the evidence is, or
   it doesn't belong in the SOP.
10. **Numbers as numbers.** ₹5,00,000, 12 months, 7 days, not "a defined period".

## Before and after

> **Before:** All incoming materials shall be inspected by the Quality
> Department in accordance with the applicable inspection criteria, and the
> results thereof shall be recorded in a systematic manner to ensure
> traceability.

> **After:** Quality inspects the material against the item's inspection
> template and records it as an Incoming Inspection Report (FRM-006) on the
> goods receipt.

## The test before release

Read the SOP aloud to someone who does the job. It passes when they can say:

- what starts the process, and what ends it;
- which step is theirs, and what the next person needs from them;
- where in ERPNext they record it;
- what the system stops them doing.

Then hand it to someone who doesn't do the job. It passes when they can find
any step's record in ERPNext without asking.

## Where the text lives

SOP text is seed data: `iso_compliance/seed_data/controlled_documents.json`,
under each SOP's `sop` key (`purpose`, `scope`, `workflow`, `responsibilities`,
`procedure_steps` with `step_title` / `responsible` / `step_content` /
`erp_record`, `records_generated`). After editing it, reseed the document set
(see `PRODUCTION_INSTALL.md`). On a live site, a change to an Active SOP goes
through a Document Change Request (SOP-001).
