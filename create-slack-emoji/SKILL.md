---
name: create-slack-emoji
description: "Create and proof tiny Slack custom emoji from a phrase, theme, vibe, or cultural idea. Starts a gallery, prepares a five-option batch, generates Slack-ready files, and presents the explored directions for user feedback."
---

# Create Slack Emoji

Make tiny, high-signal Slack reaction emoji. This file is the source of truth; do not start by reading extra references.

Default output goes in `./slack-emojis/` relative to the current working directory, not inside the skill folder. The helper creates `slack-emojis/generated/<run>/` for final assets and `slack-emojis/work/<run>/` for manifests, gallery state, and intermediates.

Preference memory path: `<skill-dir>/emoji-preferences.md`. Do not create or edit this file unless the user explicitly approves saving preference notes.

## Image Generation Requirement

The creative emoji candidates must come from an image-generation model through the bundled generation script. Do not create candidate art yourself with local drawing code such as Pillow, canvas, SVG, CSS, icon libraries, ASCII art, or programmatic shape composition. Local scripts in this skill are only for setup, parallel API generation, gallery serving, slicing contact sheets, chroma-key cleanup, resizing, compression, validation, and other mechanical export tasks around model-generated source images.

Use `scripts/generate_images.py` for batch generation. It reads `options.json`, calls the image API for every option in parallel, stores raw model outputs under `slack-emojis/work/<run>/model/`, and writes Slack-ready transparent PNGs into `slack-emojis/generated/<run>/`. It supports two providers, each pinned to that provider's latest image model — OpenAI `gpt-image-2` (default) and Google `gemini-3.1-flash-image` (Nano Banana 2) — and keys the `#00ff00` chroma background out to transparency itself, so there is no separate background-cleanup step. Do not manually call image tools one at a time or decide whether to run sequentially.

If no script-supported image credential is available, stop and ask for access instead of using native tool calls, placeholder art, or deterministic PNG fallbacks.

## Image Credentials Preflight

Before creating a batch or gallery, make sure image generation is available.

1. Run:
   ```bash
   uv run <skill-dir>/scripts/check_image_credentials.py
   ```
2. If the script finds a usable OpenAI or Google credential, continue without asking; the generator defaults to OpenAI when both are present. Never print or paste secret values.
3. If no script-supported provider is found, ask before doing any batch/gallery work:
   ```text
   I need an OpenAI or Google (Gemini) API key or env file so the Slack emoji generator script can create the batch in parallel. Do you have one you want me to use?
   ```

Look for credentials in the current process environment, repo `.env`/`.env.local`, the user's global `~/.config/credentials/.env`, and any file or folder path the user points to. If the user provides a key and asks or agrees to save it, prefer saving it in `~/.config/credentials/.env` as `OPENAI_API_KEY` (or `GEMINI_API_KEY`), not in the skill folder. If a repo needs local access, keep only a local `.env` reference/value there and ensure `.env` is ignored by git. Never commit credentials.

## Design Rules

- Slack emoji are tiny. Optimize for the 22-32px reaction chip.
- Use one instantly recognizable visual element by default, maximum two.
- Text counts as a visual element. Keep text to a short word/acronym when it carries the idea.
- Text-led and image-led options are equally valid. Include both when both are plausible.
- Tiny-readable does not mean flat icon-like. Use texture/material when it helps: real flame, molten goo, chrome, rubber-stamp ink, torn paper, clay, gel, glass, neon, pixel art, risograph, marker, airbrush, enamel pin.
- Big shape first, surface character second. If texture muddies the 22px read, simplify the texture, not the whole concept into a generic icon.
- Avoid scenes, screenshots, small facial expressions, tiny props, official logos, and close character lookalikes.
- Generate on a flat solid `#00ff00` chroma-key background; today's top models render opaque, so `generate_images.py` keys this color out to transparency automatically. The subject itself may use gradients, grain, glow, shine, brush texture, or material lighting, but must never use `#00ff00`.

## Fast Workflow

1. Internally choose five option specs. Do not ask the user to choose concepts first.
2. Start the batch and launch generation with one command. Use this skill's directory as `<skill-dir>`:
   ```bash
   uv run <skill-dir>/scripts/start_batch.py --run YYYY-MM-DD-short-run --open --generate \
     --option "fire-v-real-flame|real flame texture|<image prompt>" \
     --option "fire-v-neon|neon tube flame|<image prompt>" \
     --option "fire-v-stamp|hot warning stamp|<image prompt>" \
     --option "fire-v-gel|glossy gel flame|<image prompt>" \
     --option "fire-v-simple|simple bold silhouette|<image prompt>"
   ```
   This writes `options.json`, starts (or reuses) the gallery, and `--generate` launches all five image generations as one durable background process. It returns immediately, printing the gallery `url=` and a `generation=launched` line.
   - `--generate` runs the generator with `start_new_session` so it keeps running after the command returns. **Never launch generation yourself with a trailing shell `&` (or a host "run in background" wrapper around the raw command).** That detaches the real process from the shell, which then exits and kills it — leaving an empty `generated/` folder. Let `--generate` own the backgrounding.
   - It auto-selects the provider from available credentials (OpenAI `gpt-image-2` by default, Google `gemini-3.1-flash-image` otherwise). Add `--provider google` or `--model <id>` to override. Transparent backgrounds and Slack-ready resizing (under 128KB) are handled inside the generator.
   - Generation is owned by the script: do not dispatch sub-agents and do not call the image model per option.
   - Do not substitute locally generated art when the image model is slow, unavailable, expensive, or inconvenient. Ask for credentials/access or report the blocker.
3. Immediately reply using the Response Rule below — the gallery link, a one-line note that the five options are generating, and the five directions. Do not wait for images to finish.
4. Final transparent Slack-ready PNGs land in `slack-emojis/generated/<run>/` as each option finishes, and appear in the gallery live.
5. (Optional) Confirm every file arrived with watch mode:
   ```bash
   uv run <skill-dir>/scripts/start_batch.py --run YYYY-MM-DD-short-run --watch
   ```

## Response Rule

Do background/setup/tool work silently except for required tool-progress messages from the host environment.

Reply with the gallery link, a one-line note that generation is in progress, and the five directions:

```text
Gallery: http://127.0.0.1:<port>/

Generating five options now — each will appear in the gallery above as soon as it is ready.

I explored five directions:
- `<filename>` - <idea/theme>; <what this option tests>.
- `<filename>` - <idea/theme>; <what this option tests>.
- `<filename>` - <idea/theme>; <what this option tests>.
- `<filename>` - <idea/theme>; <what this option tests>.
- `<filename>` - <idea/theme>; <what this option tests>.

Which one is closest, and what would you change?
```

The generation-status line tells the user what is happening so an empty gallery does not look broken while images render. Keep it to that one line plus the ideas — skip setup play-by-play like "I started the gallery," "I wrote the manifest," or "I saved logs."

## Preference Memory

At the end of a session, if the user clearly liked or rejected specific emoji traits, invite them to save those preferences. Keep this separate from the first substantive reply and from normal batch setup.

Use this shape:

```text
I noticed a few Slack emoji preferences from this batch:
- <short preference>
- <short preference>

Would you like me to save these in `<skill-dir>/emoji-preferences.md` so future emoji batches fit your taste better?
```

If the user says yes, show the exact Markdown you plan to save and ask:

```text
Anything you would change before I save this to your emoji preferences?
```

Only after explicit approval, append or update `<skill-dir>/emoji-preferences.md`. Keep entries short, dated, and focused on reusable taste preferences, not a transcript of the session.

## Prompt Template

Use one prompt per option:

```text
Create one Slack custom emoji candidate.

Use case: logo-brand
Asset type: Slack custom emoji / reaction sticker
Concept: <short concept>
Meaning: <when someone should use this reaction>
Subject: <single central text/object/action>
Style/medium: <specific style or material, not generic icon style>
Composition/framing: centered square emoji subject, fills 85-92% of canvas, readable at 22-32px
Text (verbatim): "<exact short text>" OR "none"
Typography: if text is used, heavy condensed lettering, exact spelling once
Tiny constraints: one visual element by default, maximum two; no tiny helper details; no watermark; no logos
Background: perfectly flat solid #00ff00 chroma-key background, no shadows, gradients, or texture in the background; do not use #00ff00 in the subject
```

If text comes back wrong after one retry, switch to a pictorial prompt or add the corrected text in post-processing on top of a model-generated image. Do not replace the candidate with a fully local drawing.

## Export And QA

- Slack target: square PNG/GIF, transparent background, under 128KB.
- `generate_images.py` already writes Slack-ready transparent PNGs under 128KB into `generated/<run>/`; the steps below are for manual touch-ups, animated GIFs, or contact sheets.
- Inspect at 128px, 64px, 32px, and 22px.
- Use `scripts/prepare_slack_emoji.py` to (re)downscale/validate a single file, e.g. a hand-edited frame or a GIF.
- If generating contact sheets, use `scripts/slice_contact_sheet.py`; the chroma key is already removed by `generate_images.py`.

## Files

- `scripts/check_image_credentials.py` - safe credential preflight; reports provider presence without printing secret values.
- `scripts/generate_images.py` - parallel image generation from `options.json` via OpenAI (`gpt-image-2`) or Google (`gemini-3.1-flash-image`); keys the `#00ff00` background out to transparency and writes raw model outputs plus Slack-ready PNGs.
- `scripts/start_batch.py` - one-command batch setup, prompt manifest, gallery start/reuse, and watch mode.
- `scripts/start_gallery.py` - lower-level gallery launcher.
- `scripts/serve_gallery.py` - live proofing gallery.
- `scripts/prepare_slack_emoji.py` - Slack-ready PNG/GIF exporter.
- `scripts/slice_contact_sheet.py` - contact-sheet slicer.
