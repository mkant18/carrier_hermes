#!/usr/bin/env python3
"""Compat shim — canonical module is or_billing_policy.py."""
from __future__ import annotations

from or_billing_policy import *  # noqa: F403
from or_billing_policy import self_test

if __name__ == "__main__":
    self_test()
    print("billing_policy: self_test OK (shim → or_billing_policy)")
