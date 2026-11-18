# Hardening pass

Tests (130) for the API, the stall watcher and the pages in a browser; see `docs/tests.md`.

Fixed along the way:

- The phone page's takes could not be played back: their videos pointed at a path the server does not serve.
- A video being watched on the phone restarted every five seconds, when the page checked for news.
- A caption containing `</textarea>` or other markup broke the caption box on the reel screens.
- A stage now takes only its own inputs (it used to accept any file name except three), and "Edit" needs a take that
  exists; a malformed input is a clear refusal instead of an error.
- A reel whose chat could not be started no longer stays in the list as a dead entry.
- An upload that is cut off, refused or empty leaves nothing behind in the reel's folder.
- A double click (or two windows) can no longer start the same stage twice, and "Try again" on a finished stage is
  refused.
- The stall watcher no longer reopens a stage the agent finished while it was deciding.
- A reel keeps its newest 12 takes; older ones are deleted as new ones arrive.
