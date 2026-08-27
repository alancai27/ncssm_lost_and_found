Original photos, kept so the backgrounds can be regenerated with different
settings later. `scripts/set_background.py` turns these into
`static/assets/<campus>-bg.webp`; it does not read from here automatically.

    python3 scripts/set_background.py durham    source-images/durham-aerial-snow.jpg
    python3 scripts/set_background.py morganton source-images/morganton-aerial.webp

Both are lower resolution than ideal and get upscaled. If you ever obtain the
full-resolution originals, replace these and re-run -- the script will
downscale instead, which looks better.
