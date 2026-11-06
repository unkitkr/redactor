# Redactor design

## Implemented foundation and measured limits

Part A freezes inputs and runtime fingerprints, then extracts, analyzes, resolves
identities, rewrites, independently verifies saved bytes and publishes. SQLite WAL
owns tasks and checkpoints; encrypted private state holds identity evidence and
model responses. Typed rules and local GLiNER handle text; OCR, barcode and face
localization handle images. Unsupported or unassessed surfaces quarantine.

Corroborating identifiers establish patient identity; names alone cannot merge
people. Providers have a separate namespace, including when a person has both
roles. Linked patients share deterministic surrogates and date offsets. Ages at
least 90 become 90+; FHIR records a masked birth date with age-band and birth-year
upper-bound extensions. Clinical values remain unchanged. Saved images must match
source pixels plus recorded masks; PNG/TIFF preserve other pixels exactly, while
JPEG uses a defined codec round trip.

The [complete 100,000-row run](benchmarks/bulk-100k-v29.json) published 19.18 MB
in 286.56 seconds under two CPUs and 1,000,000,000 bytes of RAM, with no swap or
external calls. Independent verification took 178.70 seconds; peak memory was
970.94 MB. An auxiliary artifact observer was included in these unadjusted totals.
This subset does not establish large-file throughput. **A7 remains failed:** the
[full 2 GiB v18 run](benchmarks/large-csv-2g-v18.json) timed out at 1,800.25 seconds,
having analyzed 1.82 million of 11.2 million rows and published none.

The [v28 text accuracy record](benchmarks/accuracy-v28.json) binds measurements to
source, corpus and model hashes. Its 40 reused development cases are not new
full-document labels or a general recall guarantee. [README.md](README.md) records
supplied-file outcomes separately. Native adapter support does not imply publication;
model disagreement and incomplete clinical evidence still cause valid files to quarantine.

## 1. Unit of work and parallelism

For 1 PB in object storage, register immutable object versions as parent tasks.
Dispatch bounded record batches for CSV/JSON streams, worksheet partitions for
workbooks, and pages for scanned documents. A parent retains ordering, relationships,
metadata and final assembly responsibility. Never split arbitrary CSV byte ranges
inside quoted records. Separate extraction, model, rendering and verification queues
scale independently. CPU OCR and verification are likely initial bottlenecks for
scans; remote inference eventually hits a fixed fleet quota. Measure each before
adding workers. Part A's single SQLite writer, global resolution barrier and growing
per-record evidence do not scale; replace them with a transactional distributed
ledger, compact evidence batches and partitioned execution.

## 2. Shared identity state

An encrypted relational identity store uses tenant, issuer, role and normalized
identifier as keys. Extraction writes idempotent evidence batches. Resolve connected
components before rewriting and freeze a versioned identity snapshot. Unique
constraints and compare-and-swap revisions serialize concurrent assignments;
conflicting identifiers quarantine the affected component instead of taking the
last writer. A component merge invalidates dependent work. Workers cache immutable
bindings; batch lookups and partitioned indexes limit central traffic. HMAC-derived
surrogates use a protected, versioned secret. Name-only ambiguity remains unresolved;
key rotation or changed identity policy creates a new output version.

## 3. Large single files

For a 2 GB CSV, build complete-record boundary checkpoints while streaming, then
process batches capped by both rows and decoded bytes. Persist row ranges, hashes
and identity evidence; assemble verified batches in order and reconcile every row.
Bound buffers independently of total file size. This is a proposed replacement for
the measured slow path, not an A7 pass.

For a 400,000-cell workbook, stream worksheet XML and externalize shared strings;
inventory formulas, comments, relationships, hidden sheets, drawings and metadata.
Partition cell assessment while retaining workbook-wide references. Rewrite a new
archive and verify all parts and cell counts. Current native size limits and parser
behavior do not establish this capability.

For a 3,000-page scanned PDF, inventory pages and non-page objects, render one page
at bounded resolution, and checkpoint OCR, masks and independent verification per
page. Limit concurrent decoded pixels, not just compressed bytes. Reassemble and
verify page order, geometry, attachments and metadata. Reserve per-file CPU time,
page and model budgets before dispatch. Exhaustion pauses or quarantines the parent;
no prefix is published. None of these designs permits truncation to meet a deadline.

## 4. Cost assumptions and estimate

These are planning assumptions, not market quotes or achieved throughput. Use decimal
1 PB = 1,000 TB. Assume 80% structured/text bytes and 20% scanned bytes, with scans
averaging 0.5 MB/page: 400,000 scanned pages per TB. Assume a 2-vCPU, 4-GiB worker
costs $0.10/hour; complete text processing, including verification, sustains 0.24 GB/hour;
rendering, two OCR passes and pixel checks consume two worker-seconds/page.

| Component | Assumption per input TB | Cost/TB |
| --- | --- | ---: |
| Text processing | 800 GB / 0.24 GB/hour | $333.33 |
| Scan processing | 400,000 pages × 2 seconds | $22.22 |
| Storage | Three TB copies retained three months, $10/TB-month | $90.00 |
| Object operations and ledger | Provisional allowance | $5.00 |
| Selective remote inference | Calculation below | $40.08 |
| Total with 20% contingency | Compute, storage and inference | **$588.76** |

The corresponding 1 PB estimate is **$588,760**, excluding human review and egress.
Local-only planning cost is approximately **$540.67/TB**, or **$540,670/PB**.

For the model allowance, assume four bytes/token for text, 1,000 OCR tokens/page,
1,000-token candidate chunks, and remote selection of 0.1% of chunks. That gives
200,400 requests/TB, each with 1,000 input and 100 output tokens. Assumed prices of
$0.15/million input and $0.50/million output tokens yield $40.08/TB. Prompt overhead
must fit those caps; retries consume contingency. Tenfold selection multiplies the
model line tenfold. Smaller scanned pages increase pages/TB and OCR cost. Benchmark
real mixtures before procurement. The text rate is rounded from the 100,000-row
measurement; neither that subset nor the unmeasured scan rate establishes fleet throughput.

## 5. Fleet limits and hard budgets

A central transactional allocator reserves maximum request tokens, output tokens,
requests and dollars against run and file ceilings before dispatch. Shared token
buckets enforce provider limits; completed receipts settle reservations, while
uncertain responses retain them. No worker owns an independent spend allowance.
Cache completed responses by input, policy and model fingerprint. Apply backoff with
jitter; exhausted budgets use verified local handling or quarantine. Adding workers
past quota grows waiting time, not throughput. At 1,000 requests/minute, the assumed
200.4 million calls for 1 PB alone require at least 139 days, before retries or tighter
token limits. Selective inference therefore needs explicit scheduling and deadlines.

## 6. Failure, recovery and backpressure

A worker dying on file four loses its lease; another resumes the last durable batch
or page. Write immutable artifacts before committing checkpoints. Attempt fencing
rejects stale completions; conditional publication accepts one logical result even
if execution duplicates. Model billing cannot be exactly once without provider
support. Bound retries, then dead-letter with reason and checkpoint references.
Stop upstream dispatch when staged bytes, queue age, memory pressure or budget
reservations exceed limits. Recovery must not accumulate unbounded intermediate data.

## 7. Completeness and correctness

Freeze an inventory of object version, size and content hash. Reconcile every parent
and expected record, cell, page and embedded surface to verified publication or an
explicit quarantine. Bind verdicts to input/output hashes, identity snapshot, policy
and model versions. The run finishes only when all inventory entries have terminal
outcomes and no leases or unaccounted artifacts remain. Independent scans, exact
clinical comparisons, adversarial tests and stratified fresh labels provide evidence;
they cannot prove universal absence of PHI. Missing coverage blocks publication.

## 8. Locality and immutable storage

Run workers in the data's region and residency boundary. Use scoped object access,
private networking and managed encryption keys. Keep originals unchanged; stage
outputs under content-addressed, versioned names. Publish a conditional manifest
pointing to verified immutable objects. Separate quarantine access and retention.
Cross-region transfer requires an explicit policy and cost decision.

## 9. Observability

Track input bytes reconciled, verified bytes published, records/cells/pages covered,
OCR pixels, clinical-change failures, quarantine bytes by reason, queue age, stage
latency, checkpoint lag, memory, temporary-storage growth, identity conflicts, model
tokens, reservations and settled spend. Alert on stalled byte/page progress, coverage
gaps, elevated rejection rates and projected budget/deadline breaches. File counts
alone hide large incomplete objects. Logs contain hashes and reason codes, never PHI.

## 10. Unsupported long tail

Detect content signatures, inventory containers recursively within explicit limits,
and reject corrupt, encrypted, active or unsupported content. Preserve originals in
restricted quarantine with machine-readable reasons. Prioritize new adapters by
quarantined bytes and risk; each needs extraction coverage, native preservation and
independent saved-output tests. Reprocess against a new versioned policy. Converting
an unknown format or silently dropping its hidden parts is not a safe fallback.
