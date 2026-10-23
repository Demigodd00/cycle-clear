# CycleClear — Intelligent Contract submission handoff

Contribution type: **Builder → Intelligent Contracts** (not Project). Contribution date: **23 October 2026** if submitting today; use the actual date if later.

Title: **CycleClear — Three-Party Semantic Claim Clearing**

Notes / Description (under 1,000 characters):

> CycleClear is a standalone GenLayer Intelligent Contract for clearing a directed three-owner exchange of on-chain claim rights. Three owners register full-commit, SHA-256-bound offer and want terms, explicitly reserve their claims, and validators independently assess each of the three offer→want edges. Deterministic contract logic transfers all three claim records atomically only when every edge is a verified MATCH; any mismatch, unclear evidence, cancellation, or deadline blocks clearing and releases reservations. On StudioNet, a three-edge cycle finalized and cleared, a duplicate join failed without state change, and a separate injection-bearing mismatched offer returned NO_MATCH and rejected its cycle. The deployed source byte-matches the public Git commit; 18 direct tests and a read-only proof check pass. CycleClear transfers its own claim records, not off-chain goods, rights, payment, or proof of delivery.

Evidence links to add:

1. [Explorer contract](https://explorer-studio.genlayer.com/address/0xaBf2790581cA42cD296C3CE7Ab1Db195BBA2d744)
2. [Dedicated public repository](https://github.com/Demigodd00/cycle-clear)
3. [Contract source at deployed commit](https://github.com/Demigodd00/cycle-clear/blob/9993c5c1e7e8ce3f92f1d5a04971b35e697184fa/contracts/CycleClear.py)
4. [Proof manifest](https://github.com/Demigodd00/cycle-clear/blob/main/deploy/proof.json)
5. [Positive clear transaction](https://explorer-studio.genlayer.com/tx/0xb7c3b8cd5391f9c4cb4551b1ca658e3b61e9b40c377a17c30b6842cfd2bb4597)
6. [Expected duplicate-join failure](https://explorer-studio.genlayer.com/tx/0x020393ab443697ac11ee1b720f1a90a3d1d6c38304d6b038c143b33140e42df5)
7. [Negative injection-bearing edge](https://explorer-studio.genlayer.com/tx/0x7a4eed972f4e804290420896c11f5dcb9da1012f2cce734d2d98b9132e20b566) and [rejection](https://explorer-studio.genlayer.com/tx/0x20df917266ea7945e9c7a9639b32a20a01412008f5d557d23a8931647be86def)

Reviewer steps: Open the proof manifest and verify `source_commit`, `source_sha256`, `contract_address`, and all transaction `status`, `execution`, and votes. Inspect the three positive edge findings in `readbacks` and the `positive_cleared` ownership array. Compare with `negative_edge_0` and `negative_rejected`: the bad offer was hash-verified but judged `NO_MATCH`, and its owners did not change. The duplicate join is deliberately `FINALIZED` with leader `ERROR`; it is an expected guard failure, not a successful execution. Run `python scripts/verify_proof.py` for independent read-only checks if desired. No wallet connection is needed to inspect the evidence.

Expected outcome: three claims reassign together only after all three verified `MATCH` findings. A failed or mismatched edge cannot transfer any of them.
