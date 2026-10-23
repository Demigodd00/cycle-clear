"""Resumable StudioNet probe and CycleClear demo; never prints demo private keys."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from eth_account import Account
from eth_utils import to_checksum_address
from genlayer_py import create_client
from genlayer_py.assertions import tx_execution_succeeded
from genlayer_py.chains import studionet
from genlayer_py.exceptions import GenLayerError
from genlayer_py.types import TransactionHashVariant, TransactionStatus


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"
PRIVATE = ROOT / ".private"
PROGRESS = DEPLOY / "progress.json"
PROBE_PROGRESS = DEPLOY / "probe-progress.json"
KEYS = PRIVATE / "demo-accounts.json"
BASE = "https://raw.githubusercontent.com/Demigodd00/cycle-clear/"
RUNNER = "1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6"
PATHS = (
    "evidence/demo/offer-a.txt", "evidence/demo/want-a.txt",
    "evidence/demo/offer-b.txt", "evidence/demo/want-b.txt",
    "evidence/demo/offer-c.txt", "evidence/demo/want-c.txt",
    "evidence/demo/injection-offer.txt",
)
PROBE_CODE = f'''# {{ "Depends": "py-genlayer:{RUNNER}" }}
from genlayer import *
class RunnerProbe(gl.Contract):
    count: u256
    def __init__(self):
        self.count = u256(0)
    @gl.public.write
    def bump(self) -> None:
        self.count = u256(int(self.count) + 1)
    @gl.public.view
    def get_count(self) -> u256:
        return self.count
'''


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def retry_network(action, label: str):
    for attempt in range(6):
        try:
            return action()
        except (GenLayerError, OSError) as error:
            if attempt == 5:
                raise
            print(json.dumps({"step": "network_retry", "label": label,
                              "attempt": attempt + 1, "error": str(error)[:140]}), flush=True)
            time.sleep(5)


def tx_hex(value: object) -> str:
    rendered = str(value)
    return rendered if rendered.startswith("0x") else "0x" + bytes(value).hex()


def account_keys() -> list:
    if not KEYS.exists():
        accounts = [Account.create() for _ in range(3)]
        save(KEYS, {"warning": "Disposable StudioNet-only accounts. Never fund or commit these keys.",
                    "keys": ["0x" + account.key.hex() for account in accounts]})
    record = load(KEYS)
    if len(record.get("keys", [])) != 3:
        raise RuntimeError("demo account file is incomplete")
    return [Account.from_key(key) for key in record["keys"]]


def summarize(receipt: dict) -> dict:
    consensus_data = receipt.get("consensus_data") or {}
    leader_receipt = consensus_data.get("leader_receipt") or []
    if isinstance(leader_receipt, dict):
        leader_receipt = [leader_receipt]
    leader = leader_receipt[0] if leader_receipt else {}
    votes = consensus_data.get("votes") or {}
    return {
        "status": receipt.get("status_name") or receipt.get("statusName"),
        "execution": leader.get("execution_result"),
        "consensus": receipt.get("result_name") or receipt.get("resultName"),
        "votes": {"agree": sum(v == "agree" for v in votes.values()),
                  "disagree": sum(v == "disagree" for v in votes.values()),
                  "total": len(votes)},
    }


def wait(client, transaction: str, expected_success: bool = True) -> dict:
    receipt = None
    for attempt in range(10):
        try:
            receipt = client.wait_for_transaction_receipt(
                transaction_hash=transaction,
                status=TransactionStatus.FINALIZED,
                interval=5_000,
                retries=120,
                full_transaction=True,
            )
            break
        except GenLayerError as error:
            print(json.dumps({"step": "poll_retry", "transaction": transaction,
                              "attempt": attempt + 1, "error": str(error)[:180]}), flush=True)
            time.sleep(5)
    if receipt is None:
        raise RuntimeError("receipt polling failed repeatedly: " + transaction)
    outcome = summarize(receipt)
    if outcome["status"] != TransactionStatus.FINALIZED.value:
        raise RuntimeError("not finalized: " + json.dumps(outcome))
    succeeded = tx_execution_succeeded(receipt)
    if succeeded != expected_success:
        raise RuntimeError("unexpected execution result: " + json.dumps(outcome))
    if succeeded and outcome["consensus"] not in (None, "AGREE", "MAJORITY_AGREE"):
        raise RuntimeError("unexpected consensus result: " + json.dumps(outcome))
    return outcome


def transaction(client, state: dict, state_path: Path, name: str, submit, expected_success=True) -> dict:
    entry = state.setdefault("transactions", {}).get(name)
    if entry is None:
        transaction_id = tx_hex(submit())
        entry = {"hash": transaction_id, "expected_success": expected_success}
        state["transactions"][name] = entry
        save(state_path, state)  # Persist the hash before any long polling.
        print(json.dumps({"step": name, "transaction": transaction_id, "submitted": True}), flush=True)
    if "receipt" not in entry or entry["receipt"].get("execution") is None:
        entry["receipt"] = wait(client, entry["hash"], expected_success)
        save(state_path, state)
    return entry


def deployed_address(client, transaction_id: str) -> str:
    receipt = client.wait_for_transaction_receipt(
        transaction_hash=transaction_id, status=TransactionStatus.FINALIZED,
        interval=5_000, retries=120, full_transaction=True)
    if not tx_execution_succeeded(receipt):
        raise RuntimeError("deployment execution failed")
    for key in ("tx_data_decoded", "data"):
        item = receipt.get(key)
        if isinstance(item, dict) and item.get("contract_address"):
            return to_checksum_address(str(item["contract_address"]))
    raise RuntimeError("deployment receipt omitted contract address")


def fresh_commit() -> str:
    if git("status", "--porcelain"):
        raise RuntimeError("commit all source and demo evidence before deployment")
    commit = git("rev-parse", "HEAD").decode().strip()
    remote = git("ls-remote", "origin", "refs/heads/main").decode().split()[0]
    if commit != remote:
        raise RuntimeError("pushed main must match local HEAD")
    return commit


def public_evidence(commit: str, path: str) -> dict:
    expected = git("show", "HEAD:" + path)
    url = BASE + commit + "/" + path
    with urllib.request.urlopen(url, timeout=30) as response:
        actual = response.read(4001)
    if actual != expected or len(actual) > 4000:
        raise RuntimeError("public evidence mismatches Git blob or exceeds cap: " + path)
    return {"url": url, "sha256": hashlib.sha256(expected).hexdigest(), "bytes": len(expected)}


def read_json(client, address: str, method: str, number: int) -> dict:
    raw = retry_network(lambda: client.read_contract(
        address=address, function_name=method, args=[number],
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL), method)
    return json.loads(raw) if isinstance(raw, str) else raw


def write(client, account, state: dict, name: str, method: str, args: list,
          expected_success: bool = True) -> dict:
    address = state["contract_address"]
    return transaction(client, state, PROGRESS, name,
                       lambda: client.write_contract(address=address, function_name=method,
                                                     account=account, args=args), expected_success)


def probe() -> None:
    state = load(PROBE_PROGRESS)
    accounts = account_keys()
    client = create_client(chain=studionet, account=accounts[0])
    deploy_entry = transaction(client, state, PROBE_PROGRESS, "deploy",
                               lambda: client.deploy_contract(code=PROBE_CODE, account=accounts[0], args=[]))
    if "contract_address" not in state:
        state["contract_address"] = deployed_address(client, deploy_entry["hash"])
        save(PROBE_PROGRESS, state)
    address = state["contract_address"]
    transaction(client, state, PROBE_PROGRESS, "bump",
                lambda: client.write_contract(address=address, function_name="bump", account=accounts[0], args=[]))
    raw = retry_network(lambda: client.read_contract(
        address=address, function_name="get_count", args=[],
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL), "get_count")
    if int(raw) != 1:
        raise RuntimeError("runner probe read-back did not equal 1")
    state["readback"] = 1
    state["runner"] = RUNNER
    state["network"] = "studionet"
    save(PROBE_PROGRESS, state)
    print(json.dumps({"step": "probe_pass", "address": address, "count": 1}), flush=True)


def demo() -> None:
    probe_state = load(PROBE_PROGRESS)
    if probe_state.get("readback") != 1 or probe_state.get("runner") != RUNNER:
        raise RuntimeError("run the live runner probe first")
    commit = fresh_commit()
    source_bytes = git("show", "HEAD:contracts/CycleClear.py")
    if (ROOT / "contracts" / "CycleClear.py").read_bytes() != source_bytes:
        raise RuntimeError("working contract bytes differ from Git blob")
    evidence = {path: public_evidence(commit, path) for path in PATHS}
    public_evidence(commit, "contracts/CycleClear.py")
    accounts = account_keys()
    client = create_client(chain=studionet, account=accounts[0])
    state = load(PROGRESS)
    if state.get("source_commit", commit) != commit:
        raise RuntimeError("existing progress belongs to a different source commit")
    state.setdefault("network", "studionet")
    state.setdefault("chain_id", 61999)
    state.setdefault("source_commit", commit)
    state.setdefault("source_sha256", hashlib.sha256(source_bytes).hexdigest())
    state.setdefault("source_blob", git("rev-parse", "HEAD:contracts/CycleClear.py").decode().strip())
    state.setdefault("runner", RUNNER)
    state.setdefault("evidence", evidence)
    state.setdefault("participants", [account.address for account in accounts])
    save(PROGRESS, state)
    deploy_entry = transaction(client, state, PROGRESS, "deploy",
                               lambda: client.deploy_contract(code=source_bytes.decode("utf-8"),
                                                              account=accounts[0], args=[]))
    if "contract_address" not in state:
        state["contract_address"] = deployed_address(client, deploy_entry["hash"])
        save(PROGRESS, state)
    address = state["contract_address"]
    encoded = retry_network(lambda: client.provider.make_request(
        "gen_getContractCode", [address]).get("result"), "get_contract_code")
    if not isinstance(encoded, str) or base64.b64decode(encoded, validate=True) != source_bytes:
        raise RuntimeError("deployed source bytes do not equal pushed Git blob")
    state["source_verified"] = True
    save(PROGRESS, state)

    def ref(name: str) -> list:
        item = evidence["evidence/demo/" + name + ".txt"]
        return [item["url"], item["sha256"]]

    offers = ("offer-a", "offer-b", "offer-c")
    wants = ("want-a", "want-b", "want-c")
    for i in range(3):
        write(client, accounts[i], state, f"positive_create_{i+1}", "create_claim",
              ref(offers[i]) + ref(wants[i]) + [30 * 86400])
        observed = read_json(client, address, "get_claim", i + 1)
        if observed["owner"].lower() != accounts[i].address.lower():
            raise RuntimeError("claim owner read-back mismatch")
        state.setdefault("readbacks", {})[f"claim_{i+1}_created"] = observed
        save(PROGRESS, state)

    write(client, accounts[0], state, "positive_propose", "propose_cycle", [1, 2, 3, 7 * 86400])
    write(client, accounts[1], state, "positive_join_b", "join_cycle", [1])
    duplicate = write(client, accounts[1], state, "expected_failure_duplicate_join",
                      "join_cycle", [1], expected_success=False)
    duplicate["label"] = "EXPECTED FAILURE: a claim owner cannot join the same cycle twice"
    unchanged = read_json(client, address, "get_cycle", 1)
    if unchanged["status"] != "JOINING" or unchanged["joined"] != [True, True, False]:
        raise RuntimeError("duplicate join changed the cycle despite execution failure")
    state.setdefault("readbacks", {})["after_duplicate_join"] = unchanged
    save(PROGRESS, state)
    write(client, accounts[2], state, "positive_join_c", "join_cycle", [1])
    current = read_json(client, address, "get_cycle", 1)
    if current["status"] != "READY":
        raise RuntimeError("positive cycle did not reach READY")
    state["readbacks"]["positive_ready"] = current
    save(PROGRESS, state)

    for edge in range(3):
        write(client, accounts[0], state, f"positive_edge_{edge}", "assess_edge", [1, edge])
        current = read_json(client, address, "get_cycle", 1)
        finding = current["edges"][edge]
        state["readbacks"][f"positive_edge_{edge}"] = finding
        save(PROGRESS, state)
        print(json.dumps({"step": f"positive_edge_{edge}", "finding": finding}), flush=True)
        if finding != {"label": "MATCH", "evidence": {"offer": "VERIFIED", "want": "VERIFIED"}}:
            raise RuntimeError("unexpected positive edge judgment; investigate before continuing")

    write(client, accounts[0], state, "positive_finalize", "finalize_cycle", [1])
    current = read_json(client, address, "get_cycle", 1)
    claims = [read_json(client, address, "get_claim", i + 1) for i in range(3)]
    if current["status"] != "CLEARED" or any(
        claims[i]["owner"].lower() != accounts[(i + 1) % 3].address.lower() or
        claims[i]["status"] != "NEEDS_WANT" for i in range(3)
    ):
        raise RuntimeError("atomic reassignment read-back mismatch")
    state["readbacks"]["positive_cleared"] = {"cycle": current, "claims": claims}
    save(PROGRESS, state)

    write(client, accounts[1], state, "new_owner_set_want", "set_want", [1] + ref("want-c"))
    refreshed = read_json(client, address, "get_claim", 1)
    if refreshed["status"] != "OPEN" or refreshed["owner"].lower() != accounts[1].address.lower():
        raise RuntimeError("transferred claim cannot be reused")
    state["readbacks"]["new_owner_set_want"] = refreshed
    save(PROGRESS, state)

    # A verified prompt-injection file explicitly lacks B's requested SVG entitlement.
    for i in range(3):
        offer = "injection-offer" if i == 0 else offers[i]
        write(client, accounts[i], state, f"negative_create_{i+4}", "create_claim",
              ref(offer) + ref(wants[i]) + [30 * 86400])
    write(client, accounts[0], state, "negative_propose", "propose_cycle", [4, 5, 6, 7 * 86400])
    write(client, accounts[1], state, "negative_join_b", "join_cycle", [2])
    write(client, accounts[2], state, "negative_join_c", "join_cycle", [2])
    write(client, accounts[0], state, "negative_edge_0", "assess_edge", [2, 0])
    current = read_json(client, address, "get_cycle", 2)
    finding = current["edges"][0]
    state["readbacks"]["negative_edge_0"] = finding
    save(PROGRESS, state)
    print(json.dumps({"step": "negative_edge_0", "finding": finding}), flush=True)
    if finding["label"] not in ("NO_MATCH", "UNCLEAR"):
        raise RuntimeError("injected evidence unexpectedly passed; investigate before continuing")
    write(client, accounts[0], state, "negative_finalize", "finalize_cycle", [2])
    current = read_json(client, address, "get_cycle", 2)
    negative_claims = [read_json(client, address, "get_claim", i) for i in (4, 5, 6)]
    if current["status"] != "REJECTED" or any(
        negative_claims[i]["owner"].lower() != accounts[i].address.lower() for i in range(3)
    ):
        raise RuntimeError("negative cycle did not reject without transfer")
    state["readbacks"]["negative_rejected"] = {"cycle": current, "claims": negative_claims}
    save(PROGRESS, state)

    proof = {
        "network": "studionet", "chain_id": 61999,
        "source_commit": commit, "source_blob": state["source_blob"],
        "source_sha256": state["source_sha256"], "runner": RUNNER,
        "source_url": BASE + commit + "/contracts/CycleClear.py",
        "source_verified": True, "contract_address": address,
        "explorer": "https://explorer-studio.genlayer.com/address/" + address,
        "probe": probe_state,
        "evidence": evidence, "participants": state["participants"],
        "transactions": state["transactions"], "readbacks": state["readbacks"],
        "toolchain": {"genlayer_py": "0.16.3", "genvm_linter": "0.11.0"},
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "limitations": "Synthetic claim terms; no proof of off-chain delivery, copyright, or payment.",
    }
    save(DEPLOY / "proof.json", proof)
    print(json.dumps({"step": "demo_complete", "address": address,
                      "proof": str(DEPLOY / "proof.json")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("probe", "demo"))
    args = parser.parse_args()
    if args.phase == "probe":
        probe()
    else:
        demo()
