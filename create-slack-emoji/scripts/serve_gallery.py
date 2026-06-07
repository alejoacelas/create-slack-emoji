# /// script
# requires-python = ">=3.11"
# ///
"""Serve a live proofing gallery for generated Slack emoji files."""

from __future__ import annotations

import argparse
import html
import json
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlparse


IMAGE_EXTENSIONS = {".png", ".gif", ".jpg", ".jpeg", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve a live Slack emoji proofing gallery.")
    parser.add_argument("gallery_dir", type=Path, help="Directory containing final emoji files only.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def list_images(gallery_dir: Path) -> list[dict]:
    images = []
    gallery_dir.mkdir(parents=True, exist_ok=True)
    for path in gallery_dir.iterdir():
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        stat = path.stat()
        images.append(
            {
                "name": path.name,
                "url": f"/files/{path.name}",
                "bytes": stat.st_size,
                "modified": stat.st_mtime,
            }
        )
    return sorted(images, key=lambda item: (item["modified"], item["name"]), reverse=True)


def page_html(gallery_dir: Path) -> bytes:
    title = f"Slack Emoji Proofs - {gallery_dir.name}"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f6f4ef;
      --ink: #171411;
      --muted: #746d63;
      --line: #d9d2c7;
      --panel: #fffdf8;
      --accent: #0d6efd;
      --slack-blue: #1264a3;
      --slack-blue-soft: rgba(29, 155, 209, .2);
      --slack-bg: #1d1c1d;
      --slack-rail: #350d36;
      --slack-msg: #222529;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 3;
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
      background: color-mix(in srgb, var(--panel) 92%, transparent);
      backdrop-filter: blur(12px);
    }}
    .slack-guide {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
    }}
    .slack-guide h1 {{
      margin: 0;
      font-size: 24px;
      line-height: 1.2;
    }}
    .guide-steps {{
      margin-top: 6px;
      color: var(--ink);
      font-size: 15px;
      font-weight: 750;
      line-height: 1.35;
    }}
    .guide-link {{
      min-height: 40px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0 14px;
      border-radius: 7px;
      background: var(--slack-blue);
      color: #fff;
      font-size: 14px;
      font-weight: 900;
      text-decoration: none;
      white-space: nowrap;
    }}
    .guide-link:hover {{
      background: #0f5f9a;
    }}
    .visually-hidden {{
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }}
    .notice {{
      position: fixed;
      top: 72px;
      left: 50%;
      z-index: 5;
      transform: translateX(-50%) translateY(-10px);
      opacity: 0;
      pointer-events: none;
      border: 1px solid rgba(18, 100, 163, .25);
      border-radius: 999px;
      background: #e7f5ff;
      color: #064b78;
      padding: 8px 12px;
      font-size: 13px;
      box-shadow: 0 12px 28px rgba(18, 100, 163, .14);
      transition: opacity .18s ease, transform .18s ease;
    }}
    .notice.is-visible {{
      opacity: 1;
      transform: translateX(-50%) translateY(0);
    }}
    main {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 340px;
      gap: 18px;
      padding: 18px;
    }}
    .proofs {{
      display: grid;
      gap: 14px;
      align-content: start;
    }}
    .toolbar {{
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 12px;
    }}
    .toggle {{
      min-height: 38px;
      padding: 0 13px;
      border: 1px solid var(--slack-blue);
      border-radius: 7px;
      background: #fff;
      color: var(--slack-blue);
      font-size: 13px;
      font-weight: 900;
      white-space: nowrap;
      cursor: pointer;
    }}
    .toggle[aria-pressed="true"] {{
      background: var(--slack-blue);
      color: #fff;
    }}
    .groups {{
      display: grid;
      gap: 18px;
      align-content: start;
    }}
    .group {{
      display: grid;
      gap: 10px;
    }}
    .group-head {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      padding-bottom: 6px;
      border-bottom: 1px solid var(--line);
    }}
    .group-meta {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .group-title {{
      font-size: 13px;
      font-weight: 950;
      letter-spacing: 0;
    }}
    .group-count {{
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }}
    .section-toggle {{
      min-height: 30px;
      padding: 0 10px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      color: var(--ink);
      font-size: 12px;
      font-weight: 850;
      white-space: nowrap;
      cursor: pointer;
    }}
    .section-toggle:hover {{
      border-color: var(--slack-blue);
      color: var(--slack-blue);
    }}
    .group-grid,
    .flat-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
      gap: 14px;
      align-content: start;
    }}
    .card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      overflow: hidden;
      transition: opacity .16s ease, filter .16s ease, transform .16s ease, border-color .16s ease;
      cursor: pointer;
    }}
    .card:hover {{
      transform: translateY(-1px);
      border-color: color-mix(in srgb, var(--accent) 38%, var(--line));
    }}
    .card.is-new {{
      animation: pop .22s ease-out;
      outline: 2px solid var(--slack-blue);
      box-shadow: 0 0 0 6px var(--slack-blue-soft);
    }}
    .card.is-active {{
      border-color: color-mix(in srgb, var(--slack-blue) 62%, var(--line));
      box-shadow: 0 0 0 1px rgba(29, 155, 209, .18), 0 14px 26px rgba(29, 155, 209, .08);
    }}
    .card.is-inactive {{
      background: #f7f7f4;
    }}
    .card.is-inactive .stage img,
    .card.is-inactive .sizes img {{
      opacity: .46;
      filter: grayscale(.9) saturate(.35);
    }}
    .card.is-inactive .name,
    .card.is-inactive .facts {{
      color: #73736b;
    }}
    @keyframes pop {{
      from {{ opacity: 0; transform: translateY(-6px) scale(.98); }}
      to {{ opacity: 1; transform: none; }}
    }}
    .stage {{
      display: grid;
      place-items: center;
      min-height: 190px;
      padding: 20px;
      background:
        linear-gradient(45deg, rgba(0,0,0,.04) 25%, transparent 25%),
        linear-gradient(-45deg, rgba(0,0,0,.04) 25%, transparent 25%),
        linear-gradient(45deg, transparent 75%, rgba(0,0,0,.04) 75%),
        linear-gradient(-45deg, transparent 75%, rgba(0,0,0,.04) 75%);
      background-size: 18px 18px;
      background-position: 0 0, 0 9px, 9px -9px, -9px 0;
    }}
    .stage img {{
      width: 150px;
      height: 150px;
      object-fit: contain;
      image-rendering: auto;
    }}
    .details {{
      padding: 12px;
      border-top: 1px solid var(--line);
    }}
    .name {{
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
      line-height: 1.3;
      overflow-wrap: anywhere;
    }}
    .facts {{
      display: flex;
      justify-content: space-between;
      gap: 8px;
      margin-top: 10px;
      color: var(--muted);
      font-size: 12px;
    }}
    .state {{
      margin-top: 8px;
      color: #075985;
      font-size: 12px;
      font-weight: 800;
    }}
    .card.is-active .state {{
      color: #12643a;
    }}
    .sizes {{
      display: flex;
      align-items: center;
      gap: 12px;
      margin-top: 12px;
      min-height: 38px;
    }}
    .sizes img:nth-child(1) {{ width: 64px; height: 64px; }}
    .sizes img:nth-child(2) {{ width: 32px; height: 32px; }}
    .sizes img:nth-child(3) {{ width: 22px; height: 22px; }}
    .actions {{
      margin-top: 12px;
    }}
    .download {{
      width: 100%;
      min-height: 42px;
      border: 0;
      border-radius: 7px;
      background: var(--slack-blue);
      color: #fff;
      font-size: 13px;
      font-weight: 900;
      cursor: pointer;
      box-shadow: 0 8px 18px rgba(18, 100, 163, .2);
    }}
    .download:hover {{
      background: #0f5f9a;
    }}
    .slack {{
      position: sticky;
      top: 82px;
      height: calc(100vh - 100px);
      min-height: 520px;
      border-radius: 8px;
      overflow: hidden;
      border: 1px solid #2f3034;
      background: var(--slack-bg);
      color: #f8f8f8;
      display: grid;
      grid-template-columns: 56px 1fr;
    }}
    .rail {{ background: var(--slack-rail); }}
    .thread {{
      padding: 16px;
      overflow: hidden;
    }}
    .channel {{
      padding-bottom: 12px;
      border-bottom: 1px solid #3a3d42;
      font-weight: 700;
    }}
    .message {{
      margin-top: 16px;
      padding: 12px;
      border-radius: 8px;
      background: var(--slack-msg);
    }}
    .message strong {{
      display: block;
      margin-bottom: 6px;
      font-size: 13px;
    }}
    .message p {{
      margin: 0;
      color: #d1d2d3;
      font-size: 13px;
      line-height: 1.4;
    }}
    .reactions {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 10px;
    }}
    .reaction {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
      height: 30px;
      padding: 3px 7px;
      border: 1px solid #2b87c8;
      border-radius: 16px;
      background: #124f7c;
      font-size: 12px;
      color: #fff;
      box-shadow: 0 0 0 1px rgba(29, 155, 209, .25), 0 0 18px rgba(29, 155, 209, .18);
      cursor: pointer;
      transition: opacity .12s ease, transform .12s ease;
    }}
    .reaction:hover {{
      transform: translateY(-1px);
    }}
    .reaction.is-new {{
      box-shadow: 0 0 0 2px rgba(29, 155, 209, .45), 0 0 24px rgba(29, 155, 209, .32);
    }}
    .reaction img {{
      width: 22px;
      height: 22px;
      object-fit: contain;
    }}
    .reaction-empty {{
      color: #b6b7ba;
      font-size: 12px;
      line-height: 1.35;
    }}
    .empty {{
      padding: 32px;
      border: 1px dashed var(--line);
      border-radius: 8px;
      color: var(--muted);
      background: var(--panel);
    }}
    @media (max-width: 900px) {{
      main {{ grid-template-columns: 1fr; }}
      .slack {{ position: static; height: auto; min-height: 420px; }}
      .slack-guide {{ align-items: flex-start; flex-direction: column; }}
      .guide-link {{ width: 100%; }}
    }}
  </style>
</head>
<body>
  <div id="notice" class="notice" role="status" aria-live="polite"></div>
  <header>
    <div class="slack-guide">
      <div>
        <h1>Add custom emoji to Slack</h1>
        <div class="guide-steps">Slack desktop: emoji picker -> Add emoji -> Upload image -> give it a name -> Save.</div>
      </div>
      <a class="guide-link" href="https://slack.com/hc/en-us/articles/206870177-Add-custom-emoji" target="_blank" rel="noreferrer">Slack guide</a>
    </div>
    <span id="status" class="visually-hidden">watching</span>
  </header>
  <main>
    <section class="proofs" aria-label="Emoji options">
      <div class="toolbar">
        <button id="active-toggle" class="toggle" type="button" aria-pressed="false">Show Only Active</button>
      </div>
      <div id="gallery" class="groups"><div class="empty">Waiting for final emoji files.</div></div>
    </section>
    <aside class="slack" aria-label="Slack preview">
      <div class="rail"></div>
      <div class="thread">
        <div class="channel">#ai-adoption</div>
        <div class="message">
          <strong>Alejo</strong>
          <p id="preview-copy">Someone found a workflow that might become a reflex. Which reaction would people actually click?</p>
          <div id="reactions" class="reactions"></div>
        </div>
      </div>
    </aside>
  </main>
  <script>
    let known = new Set();
    let latestImages = [];
    let noticeTimer = null;
    let activeOnly = localStorage.getItem("activeOnlyEmojiProofs") === "true";
    let seededDefaultActive = false;
    const cards = new Map();
    const groupSections = new Map();
    const reactionButtons = new Map();
    const active = new Set(JSON.parse(localStorage.getItem("activeEmojiProofs") || "[]"));
    const gallery = document.getElementById("gallery");
    const activeToggle = document.getElementById("active-toggle");
    const reactions = document.getElementById("reactions");
    const status = document.getElementById("status");
    const notice = document.getElementById("notice");
    const previewCopy = document.getElementById("preview-copy");

    const previewLines = [
      "Someone found a workflow that might become a reflex. Which reaction would people actually click?",
      "The team is about to turn a tiny reaction into culture. Pick the one that survives at Slack size.",
      "A useful AI habit just landed in chat. The emoji should make trying it feel obvious.",
      "This is the moment between demo and adoption. Choose the reaction with the cleanest signal.",
    ];

    function kb(bytes) {{
      return (bytes / 1024).toFixed(1) + "KB";
    }}

    function shortcode(name) {{
      return ":" + name.replace(/\\.[^.]+$/, "").replace(/[^a-zA-Z0-9_]+/g, "_").toLowerCase() + ":";
    }}

    function ideaKey(name) {{
      const stem = name.replace(/\\.[^.]+$/, "");
      return stem.includes("-v-") ? stem.split("-v-")[0] : "misc";
    }}

    function ideaLabel(key) {{
      const labels = {{
        ai_slop: "AI SLOP",
        human_loop: "HUMAN LOOP",
        lets_go: "LET'S GO",
        ship_it: "SHIP IT",
        we_ll_try_it: "WE'LL TRY IT",
      }};
      return labels[key] || key.replace(/[_-]+/g, " ").toUpperCase();
    }}

    function saveActive() {{
      localStorage.setItem("activeEmojiProofs", JSON.stringify([...active]));
    }}

    function versionedSrc(item) {{
      return item.url + (item.modified ? "?t=" + Math.floor(item.modified) : "");
    }}

    function showNotice(count) {{
      notice.textContent = count === 1 ? "1 new emoji option appeared" : count + " new emoji options appeared";
      notice.classList.add("is-visible");
      clearTimeout(noticeTimer);
      noticeTimer = setTimeout(() => notice.classList.remove("is-visible"), 2600);
    }}

    function stableLine(images) {{
      if (!images.length) return previewLines[0];
      const index = images.reduce((sum, item) => sum + item.name.length, 0) % previewLines.length;
      return previewLines[index];
    }}

    function toggleActive(name, shouldActivate = !active.has(name)) {{
      if (shouldActivate) active.add(name);
      else active.delete(name);
      saveActive();
      applyCardState(latestImages);
      if (activeOnly) renderLayout(latestImages);
      syncActiveToggle(latestImages);
      renderReactions(latestImages);
    }}

    function setGroupActive(key, shouldActivate) {{
      for (const item of latestImages) {{
        if (ideaKey(item.name) !== key) continue;
        if (shouldActivate) active.add(item.name);
        else active.delete(item.name);
      }}
      saveActive();
      applyCardState(latestImages);
      renderLayout(latestImages);
      syncActiveToggle(latestImages);
      renderReactions(latestImages);
    }}

    function setActiveOnly(nextActiveOnly) {{
      activeOnly = nextActiveOnly;
      localStorage.setItem("activeOnlyEmojiProofs", activeOnly ? "true" : "false");
      syncActiveToggle(latestImages);
      renderLayout(latestImages);
    }}

    function syncActiveToggle(images) {{
      const activeCount = images.filter((item) => active.has(item.name)).length;
      activeToggle.textContent = activeOnly ? "Show All Groups" : "Show Only Active";
      activeToggle.setAttribute("aria-pressed", activeOnly ? "true" : "false");
      activeToggle.title = activeOnly
        ? "Return to grouped emoji ideas"
        : "Collapse groups and show only active emoji options";
      status.textContent = images.length + " files · " + activeCount + " active" + (activeOnly ? " · active only" : "");
    }}

    async function downloadImage(name) {{
      const item = latestImages.find((candidate) => candidate.name === name);
      if (!item) return;
      const suggestedName = item.name.replace(/[^a-zA-Z0-9_.-]+/g, "_");
      const response = await fetch(versionedSrc(item), {{ cache: "no-store" }});
      if (!response.ok) throw new Error("Could not download " + item.name);
      const blob = await response.blob();

      if (window.showSaveFilePicker) {{
        try {{
          const handle = await window.showSaveFilePicker({{
            suggestedName,
            types: [{{
              description: "PNG image",
              accept: {{ "image/png": [".png"] }},
            }}],
          }});
          const writable = await handle.createWritable();
          await writable.write(blob);
          await writable.close();
          return;
        }} catch (error) {{
          if (error && error.name === "AbortError") return;
          console.warn("Save picker failed, falling back to browser download", error);
        }}
      }}

      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = suggestedName;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    }}

    function createCard(item) {{
      const src = versionedSrc(item);
      const card = document.createElement("article");
      card.className = "card";
      card.dataset.name = item.name;
      card.tabIndex = 0;
      card.innerHTML = `
        <div class="stage"><img src="${{src}}" alt="${{item.name}}"></div>
        <div class="details">
          <div class="name">${{item.name}}</div>
          <div class="facts"><span>${{shortcode(item.name)}}</span><span>${{kb(item.bytes)}}</span></div>
          <div class="state"></div>
          <div class="sizes">
            <img src="${{src}}" alt="">
            <img src="${{src}}" alt="">
            <img src="${{src}}" alt="">
          </div>
          <div class="actions"><button class="download" type="button">Download PNG</button></div>
        </div>`;
      card.addEventListener("click", () => toggleActive(item.name));
      card.addEventListener("keydown", (event) => {{
        if (event.key === "Enter" || event.key === " ") {{
          event.preventDefault();
          toggleActive(item.name);
        }}
      }});
      card.querySelector(".download").addEventListener("click", (event) => {{
        event.stopPropagation();
        downloadImage(item.name).catch((error) => console.error("Download failed", error));
      }});
      cards.set(item.name, card);
      return card;
    }}

    function updateCard(card, item) {{
      const src = versionedSrc(item);
      const images = card.querySelectorAll("img");
      for (const image of images) {{
        if (image.getAttribute("src") !== src) image.setAttribute("src", src);
      }}
      card.querySelector(".facts span:last-child").textContent = kb(item.bytes);
    }}

    function applyCardState(images) {{
      images.forEach((item) => {{
        const card = cards.get(item.name);
        if (!card) return;
        const isActive = active.has(item.name);
        card.classList.toggle("is-active", isActive);
        card.classList.toggle("is-inactive", !isActive);
        card.style.order = "";
        card.setAttribute(
          "aria-label",
          isActive ? item.name + " shown in Slack preview. Click to hide." : item.name + ". Click to show in Slack preview."
        );
        card.querySelector(".state").textContent = isActive ? "showing in Slack preview - click to hide" : "click to show in Slack preview sidebar";
      }});
    }}

    function createGroupSection(key) {{
      const section = document.createElement("section");
      section.className = "group";
      section.dataset.group = key;
      section.innerHTML = `
        <div class="group-head">
          <div class="group-title"></div>
          <div class="group-meta">
            <div class="group-count"></div>
            <button class="section-toggle" type="button"></button>
          </div>
        </div>
        <div class="group-grid"></div>`;
      section.querySelector(".section-toggle").addEventListener("click", () => {{
        const groupImages = latestImages.filter((item) => ideaKey(item.name) === key);
        const allActive = groupImages.length > 0 && groupImages.every((item) => active.has(item.name));
        setGroupActive(key, !allActive);
      }});
      groupSections.set(key, section);
      return section;
    }}

    function renderLayout(images) {{
      if (!images.length) {{
        gallery.className = "groups";
        gallery.innerHTML = '<div class="empty">Waiting for final emoji files.</div>';
        return;
      }}

      if (activeOnly) {{
        gallery.className = "flat-grid";
        const activeImages = images.filter((item) => active.has(item.name));
        if (!activeImages.length) {{
          gallery.innerHTML = '<div class="empty">No active emoji yet. Use Show All Groups, then click options to add them here.</div>';
          return;
        }}
        const fragment = document.createDocumentFragment();
        for (const item of activeImages) {{
          const card = cards.get(item.name);
          if (card) fragment.appendChild(card);
        }}
        gallery.replaceChildren(fragment);
        return;
      }}

      gallery.className = "groups";
      const groups = new Map();
      for (const item of images) {{
        const key = ideaKey(item.name);
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(item);
      }}

      for (const key of [...groupSections.keys()]) {{
        if (!groups.has(key)) groupSections.delete(key);
      }}

      const fragment = document.createDocumentFragment();
      for (const [key, groupImages] of groups) {{
        const section = groupSections.get(key) || createGroupSection(key);
        section.querySelector(".group-title").textContent = ideaLabel(key);
        const activeInGroup = groupImages.filter((item) => active.has(item.name)).length;
        section.querySelector(".group-count").textContent = activeInGroup + "/" + groupImages.length + " active";
        const sectionToggle = section.querySelector(".section-toggle");
        const allActive = activeInGroup === groupImages.length;
        sectionToggle.textContent = allActive ? "Deactivate Section" : "Activate Section";
        sectionToggle.title = allActive ? "Hide every option in this section from the Slack preview" : "Show every option in this section in the Slack preview";
        const groupGrid = section.querySelector(".group-grid");
        const groupFragment = document.createDocumentFragment();
        for (const item of groupImages) {{
          const card = cards.get(item.name);
          if (card) groupFragment.appendChild(card);
        }}
        groupGrid.replaceChildren(groupFragment);
        fragment.appendChild(section);
      }}
      gallery.replaceChildren(fragment);
    }}

    function renderReactions(images, addedNames = new Set()) {{
      const activeImages = images.filter((item) => active.has(item.name));
      const activeNames = new Set(activeImages.map((item) => item.name));
      for (const [name, button] of reactionButtons) {{
        if (!activeNames.has(name)) {{
          button.remove();
          reactionButtons.delete(name);
        }}
      }}
      reactions.querySelector(".reaction-empty")?.remove();
      if (!activeImages.length) {{
        reactions.innerHTML = '<div class="reaction-empty">Click an emoji card to show it here.</div>';
        return;
      }}
      for (const item of activeImages) {{
        let reaction = reactionButtons.get(item.name);
        const src = versionedSrc(item);
        if (!reaction) {{
          reaction = document.createElement("button");
          reaction.type = "button";
          reaction.className = "reaction";
          reaction.title = "Hide " + item.name + " from preview";
          reaction.innerHTML = `<img src="${{src}}" alt=""> <span>1</span>`;
          reaction.addEventListener("click", () => toggleActive(item.name, false));
          reactionButtons.set(item.name, reaction);
        }} else {{
          const image = reaction.querySelector("img");
          if (image.getAttribute("src") !== src) image.setAttribute("src", src);
        }}
        reaction.classList.toggle("is-new", addedNames.has(item.name));
        reactions.appendChild(reaction);
      }}
    }}

    async function refresh() {{
      const res = await fetch("/api/images", {{ cache: "no-store" }});
      const images = await res.json();
      latestImages = images;
      const current = new Set(images.map((item) => item.name));
      const added = images.filter((item) => !known.has(item.name));
      const removed = [...known].filter((name) => !current.has(name));
      const hadCards = cards.size > 0;
      known = current;
      previewCopy.textContent = stableLine(images);

      for (const name of removed) {{
        cards.get(name)?.remove();
        cards.delete(name);
        active.delete(name);
      }}
      if (removed.length) saveActive();

      if (!seededDefaultActive && images.length && !images.some((item) => active.has(item.name))) {{
        active.add(images[0].name);
        seededDefaultActive = true;
      }}

      for (const item of images) {{
        const card = cards.get(item.name) || createCard(item);
        updateCard(card, item);
        if (hadCards && added.some((addedItem) => addedItem.name === item.name)) {{
          card.classList.add("is-new");
          setTimeout(() => card.classList.remove("is-new"), 2800);
        }}
      }}
      applyCardState(images);
      renderLayout(images);
      syncActiveToggle(images);
      renderReactions(images, hadCards ? new Set(added.map((item) => item.name)) : new Set());
      if (added.length && hadCards) showNotice(added.length);
    }}

    activeToggle.addEventListener("click", () => setActiveOnly(!activeOnly));
    refresh();
    setInterval(refresh, 2000);
  </script>
</body>
</html>
""".encode()


class GalleryHandler(SimpleHTTPRequestHandler):
    gallery_dir: Path

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            body = page_html(self.gallery_dir)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        if parsed.path == "/api/images":
            body = json.dumps(list_images(self.gallery_dir)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path.startswith("/files/"):
            name = Path(unquote(parsed.path.removeprefix("/files/"))).name
            target = self.gallery_dir / name
            if target.is_file() and target.suffix.lower() in IMAGE_EXTENSIONS:
                body = target.read_bytes()
                content_type = {
                    ".gif": "image/gif",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".webp": "image/webp",
                }.get(target.suffix.lower(), "application/octet-stream")
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

        self.send_error(404)


def main() -> int:
    args = parse_args()
    gallery_dir = args.gallery_dir.resolve()
    gallery_dir.mkdir(parents=True, exist_ok=True)

    class Handler(GalleryHandler):
        pass

    Handler.gallery_dir = gallery_dir
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Serving {gallery_dir} at http://{args.host}:{args.port}/")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
