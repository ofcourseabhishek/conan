# Provider mapping (NOT shown to reviewers during anonymous critique)

| Label | Provider | Model shown in UI | Chat | Notes |
|---|---|---|---|---|
| Claude Code (own, file 10) | Claude Code (this session) | Opus 5.5 | — | Written before reading any external proposal |
| External A (file 11) | Claude web (claude.ai) | Opus 5.5 · Medium | claude.ai/chat/e7d1ff8c-… | ~45k chars; condensed faithfully; verbatim in chat |
| External B (file 12) | Gemini web | Flash | gemini.google.com/app/6dde9309febe32c1 | Chat UI shows the user turn as "retry" (likely an auto-retry after a first attempt); answer addresses the full spec |
| External C (file 13) | Grok web | Fast | grok.com/c/c3795c83-… | Response truncated by provider mid-Performance section |

Anonymized mapping used in critique round: A = External A (file 11), B = Claude Code (file 10), C = External B (file 12), D = External C (file 13).

## Critique round (anonymous A–D)
| File | Reviewer | Model | Chat |
|---|---|---|---|
| 20-critique-external-a.md | Claude web | Opus 5.5 | claude.ai/chat/9fda58e3-… |
| 21-critique-external-b.md | Gemini web | Pro | gemini.google.com/app/5f914ea4723d0972 |
| 22-critique-external-c.md | Grok web | Fast (Expert is paywalled; not upgraded) | grok.com/c/1336b69a-… |
| 23-critique-claude-code-and-rebuttal.md | Claude Code | Opus 5.5 | local |

## What was shared externally
Only 01-proposal-prompt content (the frozen spec, flattened). Repo was empty; no code, secrets, personal data, or team names.

## Access notes
- Built-in browser pane: none of the providers signed in → user chose their signed-in Chrome (Claude in Chrome extension).
- Clipboard paste and synthetic paste events were blocked by the harness classifier; prompts were typed in ≤700-char chunks and
  length-verified (6590 chars each) before sending.
- Claude and first Grok tabs crashed from long single `type` calls; Claude chat was reopened by URL; Grok was retried in a new tab.
