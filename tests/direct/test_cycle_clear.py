from pathlib import Path
import hashlib
import json
import sys


CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "CycleClear.py"
SDK = "v0.2.16"
ROOT = "https://raw.githubusercontent.com/example/cycle-clear/" + "a" * 40 + "/evidence/"
OFFERS = [
    "I assign claim A: one original SVG icon, 1024x1024 viewBox, CC0 license.",
    "I assign claim B: one 500-word English proofreading service, no images.",
    "I assign claim C: one JSON dataset of 12 public-domain tree species.",
]
WANTS = [
    "Required: one JSON dataset of 12 public-domain tree species.",
    "Required: one original SVG icon, 1024x1024 viewBox, CC0 license.",
    "Required: one 500-word English proofreading service, no images.",
]


def addr(value):
    return "0x" + value.hex()


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def warp(vm, timestamp):
    vm.warp(timestamp)
    gl = sys.modules.get("genlayer.gl")
    if gl is not None and getattr(gl, "message_raw", None) is not None:
        gl.message_raw["datetime"] = timestamp


def claim(contract, number):
    return json.loads(contract.get_claim(number))


def cycle(contract, number):
    return json.loads(contract.get_cycle(number))


def setup(vm, deploy, alice, bob, charlie):
    warp(vm, "2026-10-23T00:00:00Z")
    vm.sender = alice
    contract = deploy(str(CONTRACT), sdk_version=SDK)
    owners = (alice, bob, charlie)
    for i, owner in enumerate(owners):
        offer_url = ROOT + f"offer-{i}.txt"
        want_url = ROOT + f"want-{i}.txt"
        vm.mock_web(offer_url, {"status": 200, "body": OFFERS[i]})
        vm.mock_web(want_url, {"status": 200, "body": WANTS[i]})
        vm.sender = owner
        contract.create_claim(offer_url, sha(OFFERS[i]), want_url, sha(WANTS[i]), 86400)
    return contract


def ready(vm, contract, alice, bob, charlie):
    vm.sender = alice
    number = contract.propose_cycle(1, 2, 3, 3600)
    vm.sender = bob
    contract.join_cycle(number)
    vm.sender = charlie
    contract.join_cycle(number)
    return number


def judge(vm, label="MATCH"):
    vm.mock_llm("You are checking one directed exchange edge", json.dumps({"label": label}))


def test_three_edge_clear_is_atomic(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = setup(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie)
    number = ready(direct_vm, contract, direct_alice, direct_bob, direct_charlie)
    judge(direct_vm)
    contract.assess_edge(number, 0)
    contract.assess_edge(number, 1)
    with direct_vm.expect_revert("assessments_required"):
        contract.finalize_cycle(number)
    assert [claim(contract, i)["owner"] for i in (1, 2, 3)] == [
        addr(direct_alice), addr(direct_bob), addr(direct_charlie)
    ]
    contract.assess_edge(number, 2)
    contract.finalize_cycle(number)
    assert cycle(contract, number)["status"] == "CLEARED"
    assert [claim(contract, i)["owner"] for i in (1, 2, 3)] == [
        addr(direct_bob), addr(direct_charlie), addr(direct_alice)
    ]
    for i in (1, 2, 3):
        assert claim(contract, i)["status"] == "NEEDS_WANT"
        assert claim(contract, i)["want_url"] == ""
        assert claim(contract, i)["transfer_count"] == 1


def test_new_owner_must_reset_want(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = setup(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie)
    number = ready(direct_vm, contract, direct_alice, direct_bob, direct_charlie)
    judge(direct_vm)
    for edge in (0, 1, 2):
        contract.assess_edge(number, edge)
    contract.finalize_cycle(number)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("claim_owner_required"):
        contract.set_want(1, ROOT + "new.txt", "f" * 64)
    direct_vm.sender = direct_bob
    contract.set_want(1, ROOT + "new.txt", "f" * 64)
    assert claim(contract, 1)["status"] == "OPEN"
    assert claim(contract, 1)["version"] == 3


def test_distinct_owner_and_exclusive_reservation(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = setup(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("distinct_claims_required"):
        contract.propose_cycle(1, 1, 3, 3600)
    first = contract.propose_cycle(1, 2, 3, 3600)
    with direct_vm.expect_revert("claim_unavailable"):
        contract.propose_cycle(1, 2, 3, 3600)
    direct_vm.sender = direct_bob
    contract.join_cycle(first)
    with direct_vm.expect_revert("already_joined"):
        contract.join_cycle(first)
    with direct_vm.expect_revert("claim_locked"):
        contract.set_want(2, ROOT + "new.txt", "f" * 64)
    direct_vm.sender = direct_charlie
    contract.join_cycle(first)
    assert cycle(contract, first)["status"] == "READY"


def test_unjoined_cannot_assess_and_participant_can_cancel(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = setup(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie)
    direct_vm.sender = direct_alice
    number = contract.propose_cycle(1, 2, 3, 3600)
    with direct_vm.expect_revert("assessment_closed"):
        contract.assess_edge(number, 0)
    with direct_vm.expect_revert("participants_missing"):
        contract.finalize_cycle(number)
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("joined_participant_required"):
        contract.cancel_cycle(number)
    contract.join_cycle(number)
    contract.cancel_cycle(number)
    assert cycle(contract, number)["status"] == "CANCELLED"
    assert claim(contract, 1)["status"] == "OPEN"
    assert claim(contract, 2)["status"] == "OPEN"


def test_hash_mismatch_fails_closed(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = setup(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie)
    number = ready(direct_vm, contract, direct_alice, direct_bob, direct_charlie)
    direct_vm.clear_mocks()
    direct_vm.mock_web(ROOT + "offer-0.txt", {"status": 200, "body": "tampered"})
    direct_vm.mock_web(ROOT + "want-1.txt", {"status": 200, "body": WANTS[1]})
    judge(direct_vm)
    contract.assess_edge(number, 0)
    finding = cycle(contract, number)["edges"][0]
    assert finding == {"label": "UNCLEAR", "evidence": {"offer": "HASH_MISMATCH", "want": "VERIFIED"}}
    contract.finalize_cycle(number)
    assert cycle(contract, number)["status"] == "REJECTED"
    assert claim(contract, 1)["owner"] == addr(direct_alice)


def test_concrete_mismatch_rejects_entire_cycle(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = setup(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie)
    number = ready(direct_vm, contract, direct_alice, direct_bob, direct_charlie)
    judge(direct_vm, "NO_MATCH")
    contract.assess_edge(number, 1)
    contract.finalize_cycle(number)
    assert cycle(contract, number)["status"] == "REJECTED"
    assert [claim(contract, i)["status"] for i in (1, 2, 3)] == ["OPEN"] * 3


def test_unknown_model_label_fails_closed(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = setup(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie)
    number = ready(direct_vm, contract, direct_alice, direct_bob, direct_charlie)
    judge(direct_vm, "IGNORE ALL RULES")
    contract.assess_edge(number, 0)
    assert cycle(contract, number)["edges"][0]["label"] == "UNCLEAR"


def test_validator_replays_evidence_and_label(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = setup(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie)
    number = ready(direct_vm, contract, direct_alice, direct_bob, direct_charlie)
    judge(direct_vm)
    contract.assess_edge(number, 0)
    leader = direct_vm._captured_validators[-1][0]
    assert direct_vm.run_validator(leader_result=leader) is True
    forged = {"label": "NO_MATCH", "evidence": {"offer": "VERIFIED", "want": "VERIFIED"}}
    assert direct_vm.run_validator(leader_result=forged) is False
    forged = {"label": "MATCH", "evidence": {"offer": "HASH_MISMATCH", "want": "VERIFIED"}}
    assert direct_vm.run_validator(leader_result=forged) is False


def test_deadline_releases_reservations(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = setup(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie)
    number = ready(direct_vm, contract, direct_alice, direct_bob, direct_charlie)
    warp(direct_vm, "2026-10-23T01:00:01Z")
    assert cycle(contract, number)["effective_status"] == "EXPIRED"
    with direct_vm.expect_revert("assessment_closed"):
        contract.assess_edge(number, 0)
    contract.finalize_cycle(number)
    assert cycle(contract, number)["status"] == "EXPIRED"
    assert [claim(contract, i)["reserved_cycle"] for i in (1, 2, 3)] == [0, 0, 0]


def test_claim_expiry_and_no_value(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = setup(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie)
    direct_vm.sender = direct_alice
    direct_vm.value = 1
    with direct_vm.expect_revert("no_value_allowed"):
        contract.propose_cycle(1, 2, 3, 3600)
    direct_vm.value = 0
    warp(direct_vm, "2026-10-25T00:00:00Z")
    assert claim(contract, 1)["effective_status"] == "EXPIRED"
    with direct_vm.expect_revert("claim_unavailable"):
        contract.propose_cycle(1, 2, 3, 3600)


def test_invalid_inputs_and_same_owner_rejected(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = setup(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("full_commit_raw_github_url_required"):
        contract.create_claim("https://github.com/example/main/offer", "a" * 64, ROOT + "want.txt", "b" * 64, 3600)
    with direct_vm.expect_revert("invalid_sha256"):
        contract.create_claim(ROOT + "offer.txt", "not-a-hash", ROOT + "want.txt", "b" * 64, 3600)
    with direct_vm.expect_revert("claim_lifetime_out_of_bounds"):
        contract.create_claim(ROOT + "offer.txt", "a" * 64, ROOT + "want.txt", "b" * 64, 10)
    contract.create_claim(ROOT + "extra-offer.txt", "a" * 64, ROOT + "extra-want.txt", "b" * 64, 86400)
    with direct_vm.expect_revert("distinct_owners_required"):
        contract.propose_cycle(1, 2, 4, 3600)
    with direct_vm.expect_revert("cycle_window_out_of_bounds"):
        contract.propose_cycle(1, 2, 3, 10)


def test_unjoined_or_wrong_owner_cannot_cancel_or_retire(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = setup(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie)
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("first_claim_owner_required"):
        contract.propose_cycle(1, 2, 3, 3600)
    with direct_vm.expect_revert("claim_owner_required"):
        contract.retire_claim(1)
    direct_vm.sender = direct_alice
    number = contract.propose_cycle(1, 2, 3, 3600)
    with direct_vm.expect_revert("claim_locked"):
        contract.retire_claim(1)
    direct_vm.sender = direct_charlie
    with direct_vm.expect_revert("joined_participant_required"):
        contract.cancel_cycle(number)
