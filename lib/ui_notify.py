# -*- coding: utf-8 -*-
"""Hooks so open tool windows can refresh when language or theme changes."""
from __future__ import print_function

_language_listeners = []
_theme_listeners = []


def register(listener):
    register_language_listener(listener)


def register_language_listener(listener):
    if listener is not None and listener not in _language_listeners:
        _language_listeners.append(listener)


def register_theme_listener(listener):
    if listener is not None and listener not in _theme_listeners:
        _theme_listeners.append(listener)


def unregister(listener):
    unregister_language_listener(listener)
    unregister_theme_listener(listener)


def unregister_language_listener(listener):
    try:
        _language_listeners.remove(listener)
    except ValueError:
        pass


def unregister_theme_listener(listener):
    try:
        _theme_listeners.remove(listener)
    except ValueError:
        pass


def notify_language_changed():
    for fn in list(_language_listeners):
        try:
            fn()
        except Exception:
            pass


def notify_theme_changed():
    for fn in list(_theme_listeners):
        try:
            fn()
        except Exception:
            pass
