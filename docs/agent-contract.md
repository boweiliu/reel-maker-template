# Handing your work to Reel maker

The creator answers through the Reel maker app, not this chat. Each message names one stage and the reel folder. Do
that stage of the skill, write its file there, write `status.json` as `{"stage": "<stage>", "state": "done"}` (or
`"failed"` with an `"error"` sentence), and stop until the next message.

| Stage | Read | Write |
| --- | --- | --- |
| `research` | `request.json` | `interview.json` |
| `story` | `answers.json` | `tones.json` |
| `script` | `choice.json`, `change.json` if present | `script.json` |
| `footage` | `script.json` | `footage/*.mp4`, `footage.json` |
| `edit` | the take named in `choice.json`, `change.json` if present | `reel.mp4`, `reel.json` |

```
interview.json  {"questions": [{"q", "help", "guess", "quote"?}]}      quote: the creator's first prompt
tones.json      {"story", "tones": [{"key", "name", "hook", "recommended"?}],
                 "directions": [{"key", "name", "summary", "recommended"?}]}
script.json     {"lines": [{"say", "screen", "shot": "face|chat|prompt|app|end"}]}
footage.json    {"clips": [{"file", "caption"}], "privacy": [...]}
reel.json       {"caption", "checks": [...], "notes": [...]}
```
