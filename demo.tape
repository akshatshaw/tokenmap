# tokenmap README demo — rendered with VHS (https://github.com/charmbracelet/vhs)
#
#   brew install vhs        # one-time (pulls in ttyd + ffmpeg)
#   vhs demo.tape           # writes tokenmap-demo.gif
#
# Tune Width/Height/FontSize/Sleep below to trade off clarity vs. file size
# (keep the GIF under ~10 MB so it renders on PyPI as well as GitHub).

Output tokenmap-demo.gif

Set Shell "zsh"
Set FontSize 14
Set Width 1200
Set Height 1000
Set Padding 16
Set Framerate 24
Set CursorBlink false

# --- Off-camera setup: activate the venv and use a clean, generic prompt
#     (avoids baking your username/hostname into a public GIF) ---
Hide
Type "export VIRTUAL_ENV_DISABLE_PROMPT=1 && source .venv/bin/activate && PS1='$ ' && clear" Enter
Sleep 800ms
Show

# --- The money shot: one command -> heatmap + estimated cost breakdown ---
Type "tokenmap" Sleep 600ms Enter
Sleep 5s

# --- Show off the new filters (date range + single model) ---
Type "tokenmap --since 2026-01-01 --model opus" Sleep 600ms Enter
Sleep 5s
