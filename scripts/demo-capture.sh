#!/usr/bin/env bash
# Pre-capture real (colored) CLI output for the VHS demo, then render.
#
# Why: the flagship commands are network-bound (the archive fetch for `plan`
# across a few subs takes ~20s), which is too slow to record live. So we run
# each command ONCE under a pty (so the CLI keeps its ANSI colors — it only
# colors a real TTY), stash the output, and a tiny shim replays it instantly
# during the recording. The content is the tool's real output; only the network
# wait is removed.
#
# Usage:
#   scripts/demo-capture.sh          # capture + write shim to /tmp/demo
#   scripts/demo-capture.sh --render # also run `vhs scripts/demo.tape`
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

RG=(python -m src.cli)
[ -d .venv ] && source .venv/bin/activate 2>/dev/null || true
OUT=/tmp/demo
mkdir -p "$OUT"

# pty capture helper — runs a command on a pseudo-terminal so isatty() is true
cat > "$OUT/capture.py" <<'PY'
import os, pty, sys, select, subprocess, struct, fcntl, termios
master, slave = pty.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 45, 118, 0, 0))
p = subprocess.Popen(sys.argv[1:], stdout=slave, stderr=subprocess.DEVNULL,
                     stdin=slave, close_fds=True)
os.close(slave)
buf = []
while True:
    try:
        r, _, _ = select.select([master], [], [], 0.2)
    except (OSError, ValueError):
        break
    if r:
        try:
            data = os.read(master, 65536)
        except OSError:
            break
        if not data:
            break
        buf.append(data)
    elif p.poll() is not None:
        break
try:
    os.close(master)
except OSError:
    pass
p.wait()
sys.stdout.buffer.write(b"".join(buf))
PY

cap() { echo "capturing $1..."; python "$OUT/capture.py" "${RG[@]}" "${@:2}" > "$OUT/$1.out"; }

cap plan     plan singularity LocalLLaMA mcp --tz 7
cap draft    draft ClaudeAI --title "I built a Reddit-growth MCP with Claude Code" --type video
cap compare  compare singularity LocalLLaMA mcp

# replay shim: clears the screen, reprints the command for context, replays output
cat > "$OUT/reddit-growth" <<'SHIM'
#!/usr/bin/env bash
case "$1" in
  plan)    cmd="reddit-growth plan singularity LocalLLaMA mcp --tz 7"; f=plan.out ;;
  draft)   cmd='reddit-growth draft ClaudeAI --title "I built a Reddit-growth MCP with Claude Code" --type video'; f=draft.out ;;
  compare) cmd="reddit-growth compare singularity LocalLLaMA mcp"; f=compare.out ;;
  *) cmd="reddit-growth $*"; f="" ;;
esac
printf '\033[2J\033[3J\033[H'
printf '\033[38;5;245m$\033[0m %s\n' "$cmd"
[ -n "$f" ] && cat "/tmp/demo/$f"
SHIM
chmod +x "$OUT/reddit-growth"
echo "shim + captures ready in $OUT"

if [ "${1:-}" = "--render" ]; then
  echo "rendering..."; vhs scripts/demo.tape && echo "→ ~/Desktop/reddit-growth-demo.mp4"
fi
