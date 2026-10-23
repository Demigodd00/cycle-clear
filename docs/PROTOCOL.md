# CycleClear protocol

## State and authority

`create_claim` mints a claim record owned by the caller. Each record has an immutable issuer, mutable owner, immutable offer reference, mutable want reference, monotonically increasing version, bounded lifetime, and `OPEN`, `RESERVED`, `NEEDS_WANT`, or `RETIRED` status. The issuer is historical and has no privileged veto after transfer. The offer is not automatically verified at minting: verification occurs at assessment.

`propose_cycle` requires exactly three different claim IDs and three different current owners. The proposer must own the first claim. It snapshots all owners and versions, requires all three claims to remain live beyond the bounded cycle window, and reserves the first claim. `join_cycle` can be called only by the second and third snapshotted owners. It checks current ownership, version, availability, and expiry before reserving each claim. An owner cannot join on behalf of another.

Once all three have joined, the cycle is `READY`. Three separately callable `assess_edge` operations inspect edges 0→1, 1→2, and 2→0. They cannot overwrite a prior finding. The offer and want must come from separate URLs and hashes. Each nondeterministic result records a finding label plus the offer/want evidence states. Validators independently repeat both web fetches and the semantic judgment; equivalence requires exact equality of all returned fields, not merely valid JSON shape.

`finalize_cycle` may clear only when all three stored findings equal `MATCH`, the deadline has not passed, and every claim remains reserved by the cycle with the snapshotted owner and version. All three owner changes occur in one contract transaction. Each claim's want is cleared, version and transfer count increment, and status becomes `NEEDS_WANT`. A new owner must set a new want before participating in another cycle. A concrete `NO_MATCH` or any `UNCLEAR` rejects the full cycle and releases reservations. A missing finding keeps the cycle pending until assessment or deadline. A deadline can be closed by anyone; it releases reservations even if a participant disappears. While `JOINING`, any already joined participant can cancel and release all joined reservations.

No GEN is accepted by write methods. The contract does not custody funds.

## Evidence and consensus

- URLs must be `raw.githubusercontent.com/{owner}/{repo}/{full-commit}/{path}`. SHA-256 binds each file's exact bytes. Fetches returning non-200, empty, oversized, invalid UTF-8, unavailable, or hash-mismatched content become `UNCLEAR` rather than a pass.
- The LLM receives only the two verified texts and is instructed to treat both as untrusted data. It returns `MATCH`, `NO_MATCH`, or `UNCLEAR`; malformed labels fail closed to `UNCLEAR`.
- Distinct evidence references prevent a claim from using the *same* URL or digest for its own offer and want. This does not prove the two files are independent or truthful.
- Exact-output equivalence is strict: it can cause a disputed or non-finalized assessment if independent validators disagree. That is safer than accepting a materially different label but may reduce liveness. A timed-out cycle releases locks.
- A Git commit pin and hash prove only that the fetched bytes match the submitted reference. They do not authenticate authorship, availability forever, ownership of intellectual property, delivery of an off-chain good, or safety of content. The underlying GitHub account and repository can become inaccessible.

## Difference from other contracts

CycleClear's core mechanism is a three-party, opt-in, exclusively reserved *cycle* with three edge-specific findings and one atomic reassignment. It does not issue a policy exception (WaiverClock), one-use agent authorization (AgentPermit), or a funded tool/service escrow (ToolBond). The three linked findings are essential: no pair of participants can clear alone, and a single failed edge blocks all three transfers.

## Explicit non-goals

No frontend, payment, escrow, automatic asset delivery, reputation scoring, legal assignment guarantee, or general N-party graph solver. The contract only records and conditionally reassigns its own claim records. Off-chain representations must explain that limitation accurately.
