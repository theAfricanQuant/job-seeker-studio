# Typst CV Studio project

- `cv-content.typ` — the only file holding content, plus the optional `style:` dict.
- `adapters/*.typ` — one thin file per template; settings copied from that package's own template.
- `vendor/` — template packages not published to Typst Universe.
- `out/` — rendered PDFs, `manifest.json`, `audit.json`, `choose-template.html`.

    python3 /tmp/field-notes-typst.umeB7q/repo/scripts/vendor_packages.py .
    python3 /tmp/field-notes-typst.umeB7q/repo/scripts/render_all.py .
    python3 /tmp/field-notes-typst.umeB7q/repo/scripts/audit.py .
    python3 /tmp/field-notes-typst.umeB7q/repo/scripts/make_chooser.py .

Want a change the template does not do? Add it to `style:` in cv-content.typ, not to an adapter —
that keeps every template in step and leaves the original design intact.
