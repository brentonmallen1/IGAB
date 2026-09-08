# Hand-testing the AI chat sidebar

Everything below has automated coverage and a scripted smoke test against a
stub model. What none of that can tell you is whether a **real local model**
behaves — whether it picks sensible tools, whether its figures match the grid,
and whether the panel is pleasant to use. That is what this list is for.

## Setup

```bash
just dev-migrate          # adds ai_conversations, ai_messages, ai_calls, ai_call_payloads
just dev-backend          # or `just dev`
just dev-frontend
```

Then **System → AI**:

1. Turn **AI features** on.
2. Point **Ollama host** at your server.
3. Leave **chat model** empty to use the main model, or set one.

> The chat model must advertise the `tools` capability. Ollama reports it via
> `/api/show`; `ollama show <model>` lists it. Without it the panel still opens
> and says plainly that it cannot look anything up — that path is worth seeing
> once on purpose.

## The things most likely to be wrong

### 1. The figures must match the grid — this is the one that matters

Open the budget page for a month with real activity. Ask:

> Why is <envelope> overspent?

Then check, **in this order**:

1. Expand **"Looked up N things"** under the answer. Are the tool and the
   arguments the ones you would have chosen?
2. If "actually ran" appears in amber beside "asked for", the model wrote
   something the server had to correct. Read both.
3. Only then compare the figures in the prose against the grid behind the
   panel. **They must be identical.** A mismatch is the bug this whole design
   exists to prevent — report it with the tool trace.

### 2. Vague questions are where small models fail

> How am I doing?

There is no obviously right tool here, so this is where a 7–8B model reaches
for the wrong one or invents a date range. Check the trace, not just the prose.

### 3. Ask something it cannot answer

> What did I spend at a shop I have never been to?

It should say it found nothing, not invent a plausible figure.

### 4. Page context

Open the panel on several pages and ask "what am I looking at?". It should know
the budget month, which report tab, that you are in an account register. On a
page it does not recognise it should say nothing rather than guess.

### 5. Interrupt it

Send a question, then **Stop** mid-answer, or close the panel. Then open
**AI Activity → Model calls**: the interrupted call should be recorded, not
missing. This is the one behaviour that silently regresses if the recorder ever
starts awaiting.

## The panel itself

- Toggle from the header (the robot icon, right of the search box). It should
  only appear when AI is enabled.
- Drag the panel's **left edge** to resize; double-click to reset. Focus the
  edge and use arrow keys.
- On the budget page with an envelope selected, the category inspector and the
  chat panel are both open. Below ~1400px this gets tight — worth judging
  whether it is annoying enough to make the chat collapse the inspector.
- On a phone (or a narrow window) the panel should be full-screen, and the
  keyboard should not push the composer off-screen.
- Cycle a few themes with the panel open, light and dark. Nothing should be
  unreadable.

## AI Activity

**Scans** — unchanged. Confirm existing receipt scans still list, still show
their prompt and raw response, and still approve. This is the retrofit's main
regression risk.

**Chats** — past conversations; opening one puts it back in the panel; deleting
one leaves its model calls behind.

**Model calls** — one row **per model round trip**, so a question that used a
tool produces two rows. Check the token counts look sane (these are new — the
app used to discard them). Then **Delete stored prompts**: the rows must stay
and the detail must say the prompt aged out, not render blank.

## Regression checks on existing AI

Every AI feature now goes through the new gateway, so re-run each once:

- **Receipt scan** from mobile quick-add — still creates a transaction, still
  shows the prompt and response on its job.
- **"Describe it"** natural-language entry.
- **Category suggestion** in the transaction editor.
- **Regex suggestion** in the payee merge dialog.

Then open **Model calls**. All four should be listed. Three of them
(`suggest_category`, `suggest_regex`, `spending_insights`) recorded *nothing*
before this change and swallow their own failures — so if one of them has been
quietly failing, this is the first time you will see it. **An error row
appearing here is a discovery, not a new bug.**

## Fixed in the polish pass — worth re-checking

These were found by review rather than by use, so they are the least
hand-tested part:

- **On a phone the panel is now the app's BottomSheet**, not a hand-rolled
  full-screen div. Check: swipe-to-dismiss, Android back, the close button
  under the notch, and that the keyboard does *not* come up the instant you
  open it.
- **Ranked results.** Ask "who did I pay the most?" on a budget with more than
  25 payees. The answer must not state a total number of payees — the tool no
  longer claims one. If it says "you paid 25 payees", the prompt needs work.
- **Interrupt it again.** Closing the panel mid-answer should still record the
  call *and* keep whatever the model had already said.
- **Markdown.** Ask something whose answer wants a table. Check it scrolls
  inside its own box rather than widening the panel, and that money columns
  right-align.
- **Try again** appears on a failed turn and re-sends the same question.

## Known and deliberate

- **Read-only.** It advises; it never moves money. If it ever claims to have
  changed something, that is a prompt bug worth reporting.
- **A dropped stream is a lost turn.** The assistant message is written once, at
  the end, so a half-answer never lands looking complete.
- **Conversations are excluded from budget snapshots** on purpose — a snapshot
  is a file you might hand to someone else.
