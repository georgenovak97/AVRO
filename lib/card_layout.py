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


def compute_grid_metrics(viewport_w, min_w=132.0, max_w=220.0,
                         base_w=156.0, base_h=182.0, margin=8.0):
    """Return grid geometry with identical outer margins and cell gaps.

    The available width remainder is assigned to card widths, not to the
    margins. This keeps the grid inset stable while allowing fractional WPF
    card widths when the viewport cannot be divided into whole pixels.
    """
    try:
        viewport_w = max(1.0, float(viewport_w))
        min_w = max(1.0, float(min_w))
        max_w = max(min_w, float(max_w))
        base_w = max(1.0, float(base_w))
        base_h = max(1.0, float(base_h))
        margin = max(0.0, float(margin))
    except Exception:
        viewport_w = 800.0
        min_w = 132.0
        max_w = 220.0
        base_w = 156.0
        base_h = 182.0
        margin = 8.0

    gap = margin
    inner_w = max(1.0, viewport_w - 2.0 * margin)
    cols = max(1, int((inner_w + gap) / (min_w + gap)))
    card_w = (inner_w - max(0, cols - 1) * gap) / float(cols)

    while card_w > max_w and cols < 10000:
        next_cols = cols + 1
        next_w = (inner_w - (next_cols - 1) * gap) / float(next_cols)
        if next_w < min_w:
            break
        cols = next_cols
        card_w = next_w

    card_h = card_w * (base_h / base_w)
    return (
        cols,
        float(card_w),
        float(card_h),
        float(gap),
        float(viewport_w),
        float(margin),
        float(margin),
        float(margin),
    )
