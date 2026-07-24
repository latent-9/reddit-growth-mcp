# reddit-growth-mcp demo — rendered headlessly with VHS (charmbracelet).
#   brew install vhs
#   # commands are network-bound (~20s), so we replay pre-captured colored
#   # output via a tiny shim on PATH (see scripts/demo-capture.sh). Content is
#   # the real tool output, just not waiting on the archive live.
#   vhs scripts/demo.tape   →   ~/Desktop/reddit-growth-demo.{mp4,gif}
Output "/Users/alf/Desktop/reddit-growth-demo.mp4"

Set Shell "bash"
Set FontSize 15
Set Width 1200
Set Height 720
Set Padding 22
Set Theme "Catppuccin Mocha"
Set TypingSpeed 32ms

# --- hidden setup: put the replay shim first on PATH + a tidy prompt
Hide
Type "export PATH=/tmp/demo:$PATH; export PS1='$ '; clear"
Enter
Sleep 800ms
Show

Sleep 800ms
Type "# reddit-growth-mcp: where to post, what to post, and when. No Reddit API key."
Enter
Sleep 3s

# 1) the money shot: one command -> where + what + when (times in your tz)
Type "reddit-growth plan singularity LocalLLaMA mcp --tz 7"
Enter
Sleep 10s

# 2) score a draft BEFORE you publish (0-100 + acceptance risk)
Type 'reddit-growth draft ClaudeAI --title "I built a Reddit-growth MCP with Claude Code" --type video'
Enter
Sleep 8s

# 3) rank candidate subs by growth, traffic, and how strict removal is
Type "reddit-growth compare singularity LocalLLaMA mcp"
Enter
Sleep 8s

Type "# get it:  claude mcp add reddit-growth-mcp -- uvx reddit-growth-mcp"
Enter
Sleep 4s
