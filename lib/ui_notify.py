# -*- coding: utf-8 -*-
"""Hooks so open tool windows can refresh when language changes in Settings."""
from __future__ import print_function

_listeners = []


def register(listener):
    if listener is not None and listener not in _listeners:
        _listeners.append(listener)


def unregister(listener):
    try:
        _listeners.remove(listener)
    except ValueError:
        pass


def notify_language_changed():
    for fn in list(_listeners):
        try:
            fn()
        except Exception:
            pass
