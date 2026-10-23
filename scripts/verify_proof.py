"""Read-only verifier for a completed CycleClear StudioNet proof manifest."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path

from eth_account import Account
from genlayer_py import create_client
from genlayer_py.assertions import tx_execution_succeeded
from genlayer_py.chains import studionet
from genlayer_py.types import TransactionHashVariant, TransactionStatus


ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "deploy" / "proof.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def git_blob(commit: str, path: str) -> bytes:
    return subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT,
                          check=True, capture_output=True).stdout


def read(client, address: str, method: str, number: int) -> dict:
    raw = client.read_contract(address=address, function_name=method, args=[number],
                               transaction_hash_variant=TransactionHashVariant.LATEST_FINAL)
    return json.loads(raw) if isinstance(raw, str) else raw


def main() -> None:
    proof = json.loads(PROOF.read_text(encoding="utf-8"))
    require(proof["network"] == "studionet" and proof["chain_id"] == 61999,
            "unexpected network or chain")
    commit = proof["source_commit"]
    source = git_blob(commit, "contracts/CycleClear.py")
    require(hashlib.sha256(source).hexdigest() == proof["source_sha256"],
            "source digest mismatch")
    with urllib.request.urlopen(proof["source_url"], timeout=30) as response:
        require(response.read() == source, "public source differs from pinned Git blob")
    for path, entry in proof["evidence"].items():
        expected = git_blob(commit, path)
        require(len(expected) <= 4000 and hashlib.sha256(expected).hexdigest() == entry["sha256"],
                "evidence digest/size mismatch: " + path)
        with urllib.request.urlopen(entry["url"], timeout=30) as response:
            require(response.read() == expected, "public evidence differs: " + path)

    client = create_client(chain=studionet, account=Account.create())
    address = proof["contract_address"]
    encoded = client.provider.make_request("gen_getContractCode", [address]).get("result")
    require(isinstance(encoded, str) and base64.b64decode(encoded, validate=True) == source,
            "deployed code differs from pinned source")
    for name, entry in proof["transactions"].items():
        receipt = client.wait_for_transaction_receipt(
            transaction_hash=entry["hash"], status=TransactionStatus.FINALIZED,
            interval=5_000, retries=20, full_transaction=True)
        require(receipt.get("status_name") == "FINALIZED", "not finalized: " + name)
        require(tx_execution_succeeded(receipt) == entry["expected_success"],
                "execution outcome mismatch: " + name)
        leader = (receipt.get("consensus_data") or {}).get("leader_receipt") or []
        if isinstance(leader, dict):
            leader = [leader]
        require(bool(leader) and leader[0].get("execution_result") == entry["receipt"]["execution"],
                "leader execution mismatch: " + name)

    positive = read(client, address, "get_cycle", 1)
    negative = read(client, address, "get_cycle", 2)
    require(positive["status"] == "CLEARED", "positive cycle not cleared")
    require(negative["status"] == "REJECTED", "negative cycle not rejected")
    require([edge["label"] for edge in positive["edges"]] == ["MATCH"] * 3,
            "positive edge findings changed")
    require(negative["edges"][0]["label"] in ("NO_MATCH", "UNCLEAR"),
            "negative edge unexpectedly passed")
    participants = [value.lower() for value in proof["participants"]]
    for i in range(3):
        claim = read(client, address, "get_claim", i + 1)
        require(claim["owner"].lower() == participants[(i + 1) % 3],
                "atomic transfer owner mismatch")
        require(claim["transfer_count"] == 1, "transfer count mismatch")
        rejected_claim = read(client, address, "get_claim", i + 4)
        require(rejected_claim["owner"].lower() == participants[i],
                "negative cycle transferred a claim")
    require(read(client, address, "get_claim", 1)["status"] == "OPEN",
            "new owner did not restore claim to OPEN")
    print(json.dumps({"verified": True, "network": "studionet", "contract": address,
                      "source_commit": commit, "transactions": len(proof["transactions"])}))


if __name__ == "__main__":
    main()
