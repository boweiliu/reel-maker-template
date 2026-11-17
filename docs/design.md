# Design

## The flow

Seven steps, in the order Lauren's `make-app-reel` skill works:

1. **Pick your app.** App cards, Studio's pick marked.
2. **Answer a few questions.** The skill's seven interview questions, one per screen with a progress bar. Each shows
   Studio's guess and a "That's right" button, so most answers are one click. Question 5 quotes the person's real first
   prompt from the chat they built the app in.
3. **Pick a tone.** Two or three tones that fit the app, each with the opening line in that tone.
4. **See your script.** A phone-shaped storyboard plays the script beat by beat with captions; every line can be edited
   in place, and "Ask Studio" sends a change.
5. **Check the footage.** The screen clips Studio filmed on made-up data, with its privacy check.
6. **Film your take.** A QR code and the plain link to the phone page; takes appear on the computer as they arrive.
7. **Watch your reel.** The finished video, save and share buttons, a ready-made caption, and "Ask Studio" for changes.

Between steps where Studio works, a **waiting screen** names what it is doing and ticks each part off. It says the
person can close the window and will be told when it is ready. A change asked for on a step comes back to that same
step (the reel gets a new version number). A change to the spoken words means a new take, so it goes back to filming
with the new script on the phone.

**Example mode** (`?example=1`) runs the same pages filled in with a finished reel, so people can see every step before
making their own; its step list can be clicked to jump anywhere.

## Save and share

On a phone, "Share..." and every platform button open the phone's own share sheet with the video file attached (Web
Share API with files), which is how TikTok and Instagram take a video. On a computer the platform buttons save the
video, copy the caption and open the platform's upload page: no platform lets another site post a video directly.

## What the real version adds

- A background Studio agent per reel, running `skills/make-app-reel/` unchanged. The app sends it the person's
  answers and shows what it returns (guesses, tones, script, footage, the edit); the waiting screen shows its progress.
- Takes uploaded straight from the phone page to the app, kept under `data/.apps/reel-maker/`.
- Real state per reel (answers, script versions, takes, reel versions) instead of the hard-coded example.

## Rules

- The creator's real data never goes on screen: footage is filmed on a private copy of their app with made-up data
  (the skill's rule).
- Lauren's skill is reused as-is. Improvements to it go to her, not into this repo's copy.
