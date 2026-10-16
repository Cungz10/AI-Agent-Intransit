import pytest
from jobs.approval_handler import process_command
from core import config

def test_approval_unauthorized():
    res = process_command(sender_wa="6289999999999", message_body="OK 1")
    assert res["status"] == "unauthorized"

def test_approval_command_pattern_mismatch():
    config.OWNER_WA = "628123456789"
    res = process_command(sender_wa="628123456789", message_body="HALO BRO")
    assert res["status"] == "ignored"
