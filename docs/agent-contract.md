# How Reel maker talks to its reel agent

Each reel gets its own Studio chat (the reel agent), created by the app through the chat app. The agent follows
`.agents/skills/make-app-reel/SKILL.md` (Lauren's skill, unchanged), with one difference: the creator talks to it
through the Reel maker app instead of the chat. The app and the agent exchange files in the reel's folder,
`data/.apps/reel-maker/reels/<reel id>/` (the "reel folder"), and the app sends the agent one chat message per request.

## The rules for the agent

- **Never ask the creator anything in chat.** Every question goes in the files below; the app shows it.
- **Work from the files, not your memory.** The creator can edit what you wrote (above all the script) before the
  next stage. A message that names files the creator just saved means re-read them; they win over what you remember.
- **Do one request, then stop.** Each app message names one stage. Do that stage, write its output file, set
  `status.json` to `done` for it, and end your turn. Wait for the next message.
- **Keep `status.json` current while you work** (it drives the app's waiting screen):

  ```json
  {"stage": "script", "state": "working", "items": [
    {"label": "Finding the hook", "state": "done"},
    {"label": "Writing every line", "state": "active"},
    {"label": "Planning what's on screen", "state": "todo"}]}
  ```

  `state` is `working`, `done` or `failed` (then add `"error": "<one plain sentence>"`). Labels are plain words for
  a non-technical creator. Write the file atomically (write `status.json.tmp`, then rename). Update it every time an
  item starts or finishes, not only at the end: the creator watches it, and an item stuck on "active" for 10 minutes
  looks like a hang.
- **Write every output atomically** the same way, as UTF-8 JSON. Videos too: work in a scratch folder outside the
  reel folder (`/var/tmp/reel-<id>/`), and move the finished `reel.mp4` or clip into place only when it is final. The
  phone page shows `reel.mp4` as soon as it appears.
- **Plain words.** Everything the app shows is read by the creator: no file names, no tool names.
- The skill's rules all hold: made-up data only on screen, words are sacred, original music, and the rest.
- **Memory is tight** (stages `footage`, `edit`, `revise-reel`). The workspace's memory guard stops big processes,
  and a browser filming at 1080x1920 plus ffmpeg is the biggest thing a reel runs. Film one shot per process and close
  the browser before encoding; render frames at 720x1280 and scale up in the encode; run ffmpeg with `-threads 1` and
  a fast preset; never keep two browsers open. Before a heavy step, read `MemAvailable` in `/mngr-vol/.host-meminfo`
  (the machine this workspace shares) and wait for about 1 GB. A run that still gets stopped is retried from the
  last finished clip, not from scratch: keep finished clips in `footage/`.

## Stages

Each message from the app starts with `REEL STAGE: <stage>` and names the reel folder.

| Stage | The agent reads | The agent writes |
| --- | --- | --- |
| `research` | `request.json` (`app`: the app's name and description) | `interview.json` |
| `story` | `answers.json` | `tones.json` |
| `script` | `answers.json`, `choice.json` (`tone`, optional `direction`) | `script.json` |
| `revise-script` | `script.json`, `change.json` (`text`) | `script.json` (rewritten), `status.json` |
| `footage` | `script.json` (as locked) | `footage/*.mp4`, `footage.json` |
| `edit` | `takes/<chosen take>` (named in `choice.json` as `take`) | `reel.mp4`, `reel.json` |
| `revise-reel` | `reel.json`, `change.json` | `reel.mp4` (new cut), `reel.json` (`version` + 1) |

### `interview.json` (stage `research`)

Skill step 1. Find the app and the chat it was built in (the `find-transcripts` skill), quote the creator's first
prompt, and make a first guess at every interview question.

```json
{"app": "Deck List", "app_blurb": "Magic deck builder with drag-to-tag",
 "first_prompt": "i'm building a list of 99 for my ulalek deck, ...",
 "questions": [
   {"q": "What's the most interesting thing about Deck List?",
    "help": "The part a stranger would say \"wait, it does that?\" about.",
    "guess": "Drag-to-tag: you pick up a card and drop it on a zone to tag it."}]}
```

Seven questions, in the skill's order. The question about the first prompt carries `"quote": "<the prompt>"`.

### `tones.json` (stage `story`)

Skill steps 2 and 3: the story and 2-3 tones that fit, each with the hook in that tone, one marked recommended.

```json
{"story": "Before and after: a clicking chore, one prompt to Studio, then the app makes it effortless.",
 "tones": [{"key": "calm", "name": "Calm and matter-of-fact", "hook": "...", "recommended": true}],
 "directions": [{"key": "before-after", "name": "Before and after", "summary": "...", "recommended": true}]}
```

### `script.json` (stages `script`, `revise-script`)

Skill step 4. `shot` is one of `face`, `chat`, `prompt`, `app`, `end`.

```json
{"tone": "calm", "direction": "before-after", "seconds": 30,
 "lines": [{"say": "Putting one card in three categories on Archidekt? That's a lot of clicking.",
            "screen": "Your face, Studio icon in a corner", "shot": "face"}]}
```

### `footage.json` (stage `footage`)

Skill step 5. Clips go in `footage/`, named `<line number>-<slug>.mp4`.

```json
{"clips": [{"file": "footage/2-first-prompt.mp4", "caption": "Your first prompt", "line": 2}],
 "privacy": ["Your first prompt ends with part of your email address. It gets cropped out."]}
```

### `reel.json` (stages `edit`, `revise-reel`)

Skill steps 7 and 8. `reel.mp4` is the finished reel.

```json
{"version": 1, "caption": "A ready-to-post caption in the creator's voice",
 "checks": ["Pauses and \"um\"s cut, every word kept", "Captions match what you said"],
 "notes": ["Watch it with sound on before you post it."]}
```

## Files the app writes

`request.json`, `answers.json` (`{"answers": ["...", ...]}` in question order), `choice.json` (`tone`, `direction`,
`take`), `change.json`, and `takes/take-<n>.<ext>` uploaded from the phone. `state.json` is the app's own record
(step, chat id); the agent never edits it.
