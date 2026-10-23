# CycleClear

CycleClear is a standalone GenLayer Intelligent Contract for clearing a directed, three-owner cycle of **on-chain claim rights**. It has no frontend, token, or payable path.

Each owner registers one claim with an offer and a want, each supplied as a raw GitHub URL pinned to a full 40-character commit and a SHA-256 digest. Owner A proposes the ordering A → B → C → A; B and C explicitly join, reserving their claims. GenLayer validators independently fetch and hash the offer and want for each directed edge, then judge whether the offer text satisfies the receiving owner's want text. Three `MATCH` findings allow one transaction to reassign all three claim records. Any `NO_MATCH`, `UNCLEAR`, or missing/tampered evidence prevents clearing. Cancellation and a bounded deadline release reservations.

The contract transfers recorded claim ownership, **not** the referenced files, services, copyright, payment, or off-chain delivery. A `MATCH` means the validators found the *texts* compatible; it is not proof that a contributor performed an obligation or that the evidence author was truthful. Do not use the contract as a substitute for legal or financial settlement.

## Files

- `contracts/CycleClear.py`: deployable, pinned-runner contract.
- `tests/direct/test_cycle_clear.py`: local direct-mode state, failure, and validator-replay tests.
- `docs/PROTOCOL.md`: state machine, security assumptions, and distinctiveness.
- `docs/READINESS.md`: separate technical, distinctiveness, and evidence gates.

## Local verification

Requires Python 3.12 and dependencies in `requirements.txt`.

```powershell
python -m pip install -r requirements.txt
genvm-lint check contracts/CycleClear.py --json
pytest tests/direct -q
```

Direct tests use synthetic web and LLM responses. They are not live consensus or Explorer evidence. No live deployment is claimed in this repository until an Explorer address, matching Git commit, and transaction links are recorded here.

## Minimal flow

1. Each of three distinct senders calls `create_claim(offer_url, offer_sha256, want_url, want_sha256, lifetime_seconds)`.
2. The first claim's owner calls `propose_cycle(first_id, second_id, third_id, window_seconds)`. This reserves the first claim and fixes owner/version snapshots.
3. The second and third owners each call `join_cycle(cycle_id)`. Their claims become exclusively reserved.
4. Anyone calls `assess_edge(cycle_id, 0)`, then edges `1` and `2`. Edge `i` compares claim `i`'s offer with claim `(i+1)%3`'s want.
5. Anyone calls `finalize_cycle(cycle_id)`. All three must have `MATCH` findings before any owner changes. New owners must call `set_want` before reusing transferred claims in another cycle.

See `docs/PROTOCOL.md` for timeouts, cancellation, and limitations.
