# Readiness gates

Status after the StudioNet demo. These are evidence gates, not a steward acceptance or points guarantee.

| Gate | Status | Evidence / gap |
| --- | --- | --- |
| Technical | PASS | GenVM lint and 18 direct tests pass. The runner probe and CycleClear deployment finalized with leader `SUCCESS`; the live three-edge positive cycle cleared, a duplicate join failed without changing state, and a conflicting instruction-injection edge returned `NO_MATCH` before rejection. |
| Distinctiveness | PASS | At design level, three-owner reservations, three edge findings, and atomic reassignment differ from WaiverClock/AgentPermit/ToolBond mechanisms; no steward determination is promised. |
| Evidence | PASS | Public repo and full-commit source/evidence URLs, deployed-source byte match, 21 finalized CycleClear transactions with execution results/votes, final on-chain read-backs, and a read-only proof verifier are recorded in `deploy/proof.json`. |

The source and evidence are synthetic claim descriptions, not proof of delivered goods, copyright, or payment. A reviewer may judge distinctiveness or utility differently. Portal submission remains the user's action; do not treat these gates as acceptance.
