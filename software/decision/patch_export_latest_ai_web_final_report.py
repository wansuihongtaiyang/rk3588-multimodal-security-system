#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path

TARGET = Path("/home/elf/sensor_work/day30_web/export_latest_ai_web.py")


def main():
    if not TARGET.exists():
        raise SystemExit(f"target not found: {TARGET}")

    s = TARGET.read_text(encoding="utf-8", errors="replace")
    backup = TARGET.with_name(TARGET.name + ".bak_final_display_report")
    backup.write_text(s, encoding="utf-8")

    if "final_display_report.txt" not in s:
        old = 'ai_txt = read_text(event_dir / "event_ai_report.txt")'
        new = '''ai_txt = read_text(event_dir / "event_ai_report.txt")
    final_display_report = read_text(event_dir / "final_display_report.txt", limit=120000)
    final_display_json = read_json(event_dir / "final_display_report.json")'''

        if old not in s:
            raise SystemExit("patch point 1 not found: ai_txt line")

        s = s.replace(old, new, 1)

    if "<h2>最终安全决策报告</h2>" not in s:
        old = '''<div class="card">
<h2>最终 AI 报告</h2>
<pre>{esc(final_report or ai_txt)}</pre>
</div>'''

        new = '''<div class="card">
<h2>最终安全决策报告</h2>
<pre>{esc(final_display_report or final_report or ai_txt)}</pre>
</div>

<div class="card">
<h2>原始 AI 报告</h2>
<pre>{esc(final_report or ai_txt)}</pre>
</div>'''

        if old not in s:
            raise SystemExit("patch point 2 not found: final AI report card")

        s = s.replace(old, new, 1)

    TARGET.write_text(s, encoding="utf-8")

    print("patch ok")
    print("target =", TARGET)
    print("backup =", backup)


if __name__ == "__main__":
    main()