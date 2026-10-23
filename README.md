# CycleClear

CycleClear is a standalone GenLayer Intelligent Contract for clearing a directed, three-owner cycle of **on-chain claim rights**. It has no frontend, token, or payable path. A [StudioNet deployment](https://explorer-studio.genlayer.com/address/0xaBf2790581cA42cD296C3CE7Ab1Db195BBA2d744) is backed by the [live proof manifest](deploy/proof.json); its deployed source bytes match [commit `9993c5c`](https://github.com/Demigodd00/cycle-clear/blob/9993c5c1e7e8ce3f92f1d5a04971b35e697184fa/contracts/CycleClear.py).

Each owner registers one claim with an offer and a want, each supplied as a raw GitHub URL pinned to a full 40-character commit and a SHA-256 digest. Owner A proposes the ordering A → B → C → A; B and C explicitly join, reserving their claims. GenLayer validators independently fetch and hash the offer and want for each directed edge, then judge whether the offer text satisfies the receiving owner's want text. Three `MATCH` findings allow one transaction to reassign all three claim records. Any `NO_MATCH`, `UNCLEAR`, or missing/tampered evidence prevents clearing. Cancellation and a bounded deadline release reservations.

The contract transfers recorded claim ownership, **not** the referenced files, services, copyright, payment, or off-chain delivery. A `MATCH` means the validators found the *texts* compatible; it is not proof that a contributor performed an obligation or that the evidence author was truthful. Do not use the contract as a substitute for legal or financial settlement.

```text
A's offer ──MATCH──> B's want
B's offer ──MATCH──> C's want     three independent findings
C's offer ──MATCH──> A's want     → one atomic three-claim reassignment
```

The live demo recorded three `MATCH` findings and [cleared the cycle](https://explorer-studio.genlayer.com/tx/0xb7c3b8cd5391f9c4cb4551b1ca658e3b61e9b40c377a17c30b6842cfd2bb4597). A [duplicate join failed](https://explorer-studio.genlayer.com/tx/0x020393ab443697ac11ee1b720f1a90a3d1d6c38304d6b038c143b33140e42df5) without changing state. A distinct [adversarial evidence edge returned `NO_MATCH`](https://explorer-studio.genlayer.com/tx/0x7a4eed972f4e804290420896c11f5dcb9da1012f2cce734d2d98b9132e20b566), and that [cycle was rejected](https://explorer-studio.genlayer.com/tx/0x20df917266ea7945e9c7a9639b32a20a01412008f5d557d23a8931647be86def) without transferring its claims. See [reviewer instructions](docs/SUBMISSION.md).

## Files

- `contracts/CycleClear.py`: deployable, pinned-runner contract.
- `tests/direct/test_cycle_clear.py`: local direct-mode state, failure, and validator-replay tests.
- `docs/PROTOCOL.md`: state machine, security assumptions, and distinctiveness.
- `docs/READINESS.md`: separate technical, distinctiveness, and evidence gates.
- `evidence/demo/`: small immutable demo offer/want terms, including an adversarial instruction embedded as untrusted evidence.
- `scripts/live_demo.py`: resumable StudioNet runner probe, positive three-party clear, expected duplicate-join failure, and negative prompt-injection cycle. It stores disposable test-only signer keys locally in ignored `.private/`; do not fund them or commit that directory.
- `scripts/verify_proof.py`: read-only verifier for pinned source/evidence bytes, finalized transaction execution, and final on-chain ownership invariants.

## Local verification

Requires Python 3.12 and dependencies in `requirements.txt`.

```powershell
python -m pip install -r requirements.txt
genvm-lint check contracts/CycleClear.py --json
pytest tests/direct -q
```

Direct tests use synthetic web and LLM responses and are separate from the finalized StudioNet proof above.

For a live demonstration after committing and pushing the evidence to a public repository, run `python scripts/live_demo.py probe` followed by `python scripts/live_demo.py demo`. Each submitted transaction hash is saved before polling in ignored `deploy/progress.json`; a completed run writes `deploy/proof.json` for review.
After committing that manifest, `python scripts/verify_proof.py` rechecks it without sending transactions.

## Minimal flow

1. Each of three distinct senders calls `create_claim(offer_url, offer_sha256, want_url, want_sha256, lifetime_seconds)`.
2. The first claim's owner calls `propose_cycle(first_id, second_id, third_id, window_seconds)`. This reserves the first claim and fixes owner/version snapshots.
3. The second and third owners each call `join_cycle(cycle_id)`. Their claims become exclusively reserved.
4. Anyone calls `assess_edge(cycle_id, 0)`, then edges `1` and `2`. Edge `i` compares claim `i`'s offer with claim `(i+1)%3`'s want.
5. Anyone calls `finalize_cycle(cycle_id)`. All three must have `MATCH` findings before any owner changes. New owners must call `set_want` before reusing transferred claims in another cycle.

See `docs/PROTOCOL.md` for timeouts, cancellation, and limitations.
