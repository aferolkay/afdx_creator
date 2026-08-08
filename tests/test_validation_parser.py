"""Parser tests using output shapes captured from real simulator runs."""

from __future__ import annotations

from afdx_generator.validation.parser import parse_output

CLEAN_RUN = """
OMNeT++ Discrete Event Simulation
Setting up Cmdenv...
Loading NED files from .:  3
Preparing for running configuration simpleNetwork, run #0...
Setting up network "simpleNetwork"...
Initializing...
Running simulation...
** Event #0   t=0   Elapsed: 2e-05s (0m 00s)  0% completed
     Messages:  created: 65   present: 65   in FES: 12
** Event #78069   t=1   Elapsed: 1.9s (0m 01s)  100% completed

<!> Simulation time limit reached -- at t=1s, event #78069

Calling finish() at end of Run #0...
undisposed object: (omnetpp::cOutVector) simpleNetwork.ES[0].afdxMarshall.E2ELatency_VL1 -- check module destructor
undisposed object: (omnetpp::cOutVector) simpleNetwork.ES[3].messageSink.E2ELatency_VLb -- check module destructor

End.
"""

POLICER_DROPS = """
Running simulation...
TOKEN_INSUFFICIENT (VL:7) SW:0
TOKEN_INSUFFICIENT (VL:7) SW:0
TOKEN_INSUFFICIENT (VL:7) SW:0
TOKEN_INSUFFICIENT (VL:6) SW:1
TOKEN_INSUFFICIENT (VL:9) SW:2

<!> Simulation time limit reached -- at t=1s, event #500

End.
"""

MISSING_VL = """
Setting up network "simpleNetwork"...
Running simulation...

<!> Error: Key Not Found in VL Table! -- in module (afdx::VLRouter) simpleNetwork.SwitchA[2].switchFabric.router

End.
"""

QUEUE_OVERFLOW = """
Running simulation...

<!> Error: Max limit for VLID queue is reached.(vlid:7) -- in module (afdx::RegulatorLogic) simpleNetwork.ES[5].regulatorLogic

End.
"""


def test_clean_run_passes():
    result = parse_output(CLEAN_RUN, exit_code=0)
    assert result.passed
    assert result.issues == []


def test_undisposed_object_noise_is_not_a_failure():
    """The library emits these on every healthy run; flagging them would cry wolf every time."""
    assert "undisposed object" in CLEAN_RUN
    assert parse_output(CLEAN_RUN, exit_code=0).passed


def test_time_limit_reached_is_not_a_failure():
    """A bounded run ends this way by design."""
    assert parse_output("<!> Simulation time limit reached -- at t=1s", exit_code=0).passed


def test_policer_drops_are_aggregated_per_link_and_switch():
    result = parse_output(POLICER_DROPS, exit_code=0)
    assert not result.passed

    drops = [i for i in result.issues if i.kind == "policer_drop"]
    assert len(drops) == 3  # (VL7,SW0), (VL6,SW1), (VL9,SW2) -- not 5 separate lines

    worst = drops[0]  # sorted by count descending
    assert worst.virtual_link == "7" and worst.switch == "0" and worst.count == 3
    assert "sigma" in worst.hint


def test_missing_vl_table_entry_is_detected():
    result = parse_output(MISSING_VL, exit_code=1)
    assert not result.passed
    assert any(i.kind == "missing_vl_entry" for i in result.issues)


def test_queue_overflow_is_detected_with_link_id():
    result = parse_output(QUEUE_OVERFLOW, exit_code=1)
    assert not result.passed
    overflow = next(i for i in result.issues if i.kind == "queue_overflow")
    assert overflow.virtual_link == "7"


def test_nonzero_exit_without_recognised_message_still_fails():
    result = parse_output("Running simulation...\n", exit_code=139)
    assert not result.passed
    assert result.exit_code == 139


def test_timeout_is_reported():
    result = parse_output("Running simulation...\n", exit_code=None, timed_out=True)
    assert not result.passed
    assert result.timed_out
    assert any("did not finish" in i.message for i in result.issues)
