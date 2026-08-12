# -*- coding: utf-8 -*-
"""Pure card/preview geometry helpers (no WPF)."""


def compute_preview_box(card_w, card_h, base_pw=96.0, base_ph=67.0,
                        h_pad=24.0, text_zone=78.0):
    """
    Preview box size inside a card cell.

    Keeps base aspect ratio (base_ph / base_pw) while fitting into the card.
    """
    try:
        card_w = float(card_w)
        card_h = float(card_h)
        base_pw = float(base_pw)
        base_ph = float(base_ph)
        h_pad = float(h_pad)
        text_zone = float(text_zone)
    except Exception:
        return 96.0, 67.0

    if base_pw <= 0:
        base_pw = 96.0
    if base_ph <= 0:
        base_ph = 67.0

    aspect = base_ph / base_pw
    max_pw = max(48.0, card_w - h_pad)
    max_ph = max(40.0, card_h - text_zone)

    pw = max_pw
    ph = pw * aspect
    if ph > max_ph:
        ph = max_ph
        pw = ph / aspect if aspect > 0 else pw
        if pw > max_pw:
            pw = max_pw
            ph = pw * aspect
            if ph > max_ph:
                ph = max_ph
    return float(pw), float(ph)
