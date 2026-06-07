# create-slack-emoji

A skill for Claude Code and Codex that turns a phrase, vibe, or idea into tiny, high-signal Slack custom emoji. It explores five directions, generates them with the latest image models, and opens a live gallery to pick from.

## Setup

You need an image-generation API key from **one** provider:

- **OpenAI** — set `OPENAI_API_KEY` (uses `gpt-image-2`)
- **Google Gemini** — set `GEMINI_API_KEY` (uses `gemini-3.1-flash-image`, aka Nano Banana 2)

Put it in your shell environment or in `~/.config/credentials/.env`.

## Use

Just ask for what you want:

```
/create-slack-emoji a raccoon hyped about shipping code
```

You get five options in a live gallery — tell it which is closest and what to change.

## Install

Paste this to your coding agent:

> Download https://github.com/alejoacelas/create-slack-emoji and install the `create-slack-emoji/` folder into my agent's skills directory (`.claude/skills/` for Claude Code, `.codex/skills/` for Codex).
