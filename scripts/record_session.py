"""Record a terminal session to an asciicast v2 file (.cast), optionally interrupting it with Ctrl-C.

    python3 scripts/record_session.py --out runs/<run>/recording/interrupt.cast --interrupt-after 90 -- \\
        .venv/bin/python -m insight run --input data/analysis_200k.csv --run-dir runs/<run> ...

The command runs in a pseudo-terminal, so output looks exactly as in a terminal. With --interrupt-after N
the recorder sends SIGINT (what Ctrl-C does) to the command after N seconds, and records the graceful stop.
Play back with any asciinema player (the dashboard embeds one) or read the companion .txt transcript.
Standard library only.
"""

import argparse
import json
import os
import pty
import select
import signal
import sys
import time
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--title", default="")
    ap.add_argument("--interrupt-after", type=float, default=None, help="send SIGINT to the command after N seconds")
    ap.add_argument("--cols", type=int, default=140)
    ap.add_argument("--rows", type=int, default=40)
    ap.add_argument("command", nargs=argparse.REMAINDER)
    args = ap.parse_args(argv)
    cmd = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if not cmd:
        raise SystemExit("give the command after --")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pid, fd = pty.fork()
    if pid == 0:
        os.environ["COLUMNS"], os.environ["LINES"] = str(args.cols), str(args.rows)
        os.execvp(cmd[0], cmd)
    start = time.monotonic()
    header = {"version": 2, "width": args.cols, "height": args.rows, "timestamp": int(time.time()),
              "title": args.title or " ".join(cmd), "env": {"SHELL": os.environ.get("SHELL", ""), "TERM": "xterm-256color"}}
    interrupted = False
    transcript = []
    with open(args.out, "w", encoding="utf-8") as cast:
        cast.write(json.dumps(header) + "\n")
        prompt = f"$ {' '.join(cmd)}\r\n"
        cast.write(json.dumps([0.0, "o", prompt]) + "\n")
        transcript.append(prompt)
        while True:
            if args.interrupt_after is not None and not interrupted and time.monotonic() - start >= args.interrupt_after:
                os.kill(pid, signal.SIGINT)
                interrupted = True
                note = f"\r\n[recorder] sent SIGINT (Ctrl-C) after {args.interrupt_after:.0f} s\r\n"
                cast.write(json.dumps([round(time.monotonic() - start, 6), "o", note]) + "\n")
                transcript.append(note)
            r, _, _ = select.select([fd], [], [], 0.2)
            if fd in r:
                try:
                    data = os.read(fd, 65536)
                except OSError:
                    break
                if not data:
                    break
                text = data.decode("utf-8", errors="replace")
                cast.write(json.dumps([round(time.monotonic() - start, 6), "o", text]) + "\n")
                cast.flush()
                transcript.append(text)
                sys.stdout.write(text)
                sys.stdout.flush()
            else:
                done, status = os.waitpid(pid, os.WNOHANG)
                if done:
                    break
        try:
            _, status = os.waitpid(pid, 0)
        except ChildProcessError:
            status = 0
        code = os.waitstatus_to_exitcode(status) if status else 0
        end = f"\r\n[recorder] command exited with code {code} after {time.monotonic() - start:.1f} s\r\n"
        cast.write(json.dumps([round(time.monotonic() - start, 6), "o", end]) + "\n")
        transcript.append(end)
    args.out.with_suffix(".txt").write_text("".join(transcript).replace("\r\n", "\n").replace("\r", "\n"), encoding="utf-8")
    print(f"\n[recorder] wrote {args.out} and {args.out.with_suffix('.txt')}")
    return code


if __name__ == "__main__":
    sys.exit(main())
