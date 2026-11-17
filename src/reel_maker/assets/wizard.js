// The Reel maker walkthrough. A real reel's content comes from its folder through /api/reels/<id> (written by the
// reel's Studio chat, see docs/agent-contract.md); the example run (?example=1) shows the same screens filled in from
// EXAMPLE_REEL, which has the same shape.
const params = new URLSearchParams(location.search);
const EXAMPLE = params.has("example");
let reelId = params.get("reel") || "";

const EXAMPLE_REEL = {
  id: "example",
  state: { app: "deck-list", chat_id: "" },
  request: { app: { name: "deck-list", display_name: "Deck List", description: "Magic deck builder with drag-to-tag" } },
  status: { stage: "edit", state: "done", items: [] },
  interview: {
    app: "Deck List",
    first_prompt: "i'm building a list of 99 for my ulalek deck, i kind of just need, to start with, a place to write down card names and have them autocomplete. Once i see that i'll know what else i want",
    questions: [
      { q: "What's the most interesting thing about Deck List?", help: "The part a stranger would say \"wait, it does that?\" about.",
        guess: "Drag-to-tag. You pick up a card, the screen splits into zones, and you drop it on one to tag it." },
      { q: "What was deckbuilding like before it?", help: "The annoyance, the mess, the thing you kept putting off.",
        guess: "Tools like Archidekt make you tag cards from a menu, one card and one tag at a time." },
      { q: "What made you finally build it?", help: "The moment that tipped it, if there was one.", guess: "Building the 99 for your Ulalek deck." },
      { q: "What was the most fun or easiest part of building it?", help: "The specific moment: one sentence you typed, the first time it worked.",
        guess: "The first time autocomplete worked." },
      { q: "Is this what you typed to start it?", help: "Studio found this in the chat where you built Deck List. Your real words beat a paraphrase.",
        quote: "i'm building a list of 99 for my ulalek deck, i kind of just need, to start with, a place to write down card names and have them autocomplete. Once i see that i'll know what else i want",
        guess: "Yes, use that one." },
      { q: "What surprised you?", help: "Something it did that you didn't expect, or did better than you pictured.", guess: "Auto-tag sorting your lands and ramp correctly." },
      { q: "What's different now?", help: "One concrete after-picture, not a list of features.", guess: "Your list sits at 99 cards, every one tagged." },
    ],
  },
  answers: { answers: [
    "Drag-to-tag, and having all of Scryfall locally so everything is super snappy.",
    "Archidekt, and multi-tagging one card was a pain.", "",
    "Getting all the Scryfall data and tags loaded locally.", "Yes, use that one.",
    "How fast the card images load.", "Search, add and the deck are all on one screen.",
  ] },
  tones: {
    story: "Before and after: a clicking chore, one prompt to Studio, then the app makes it effortless.",
    tones: [
      { key: "calm", name: "Calm and matter-of-fact", hook: "Putting one card in three categories on Archidekt? That's a lot of clicking.", recommended: true },
      { key: "curious", name: "Curious and nerdy", hook: "I wanted my own copy of every Magic card ever printed. So I asked for one." },
      { key: "dry", name: "Dry and deadpan", hook: "Archidekt makes you tag cards one menu at a time. My deck has 99 cards." },
    ],
    directions: [
      { key: "before-after", name: "Before and after", summary: "A clicking chore, one prompt to Studio, then the app makes it effortless.", recommended: true },
      { key: "mystery", name: "Small mystery", summary: "Opens on a search that knows every Magic card ever printed, then rewinds to the prompt." },
      { key: "tour", name: "Matter-of-fact tour", summary: "\"This is how I build Commander decks now.\" Plain, and lets the footage do the work." },
    ],
  },
  choice: { tone: "calm", direction: "before-after", take: "take-2.mp4" },
  script: { tone: "calm", direction: "before-after", seconds: 30, lines: [
    { say: "Putting one card in three categories on Archidekt? That's a lot of clicking.", screen: "Your face, Studio icon in a corner", shot: "face" },
    { say: "So I asked Studio to build me my own.", screen: "The build chat, scrolling up", shot: "chat" },
    { say: "First: copy all of Scryfall. Every card, every tag.", screen: "Your first prompt, then a counter to 39,000 cards", shot: "prompt" },
    { say: "Then: a place to write down card names, with autocomplete. That's it.", screen: "Your second prompt, word for word", shot: "prompt" },
    { say: "Search is instant. Even the pictures pop right in.", screen: "Typing a name, the card appears with its picture", shot: "app" },
    { say: "And tagging? I just drag a card toward a category.", screen: "A card dragged onto \"ramp\", it gets its tag", shot: "app" },
    { say: "Search, add, tag. All on one screen.", screen: "The full list, scrolling", shot: "app" },
    { say: "Ninety-nine cards. Zero menus.", screen: "End card: Deck List, its icon, \"Made with Studio\"", shot: "end" },
  ] },
  footage: {
    clips: [
      { file: "shots/2-first-prompt.mp4", caption: "2. Your first prompt" },
      { file: "shots/3-scryfall-count.mp4", caption: "3. 39,000 cards counter" },
      { file: "shots/4-second-prompt.mp4", caption: "4. Your second prompt" },
      { file: "shots/5-search.mp4", caption: "5. Search" },
      { file: "shots/6-drag-to-tag.mp4", caption: "6. Drag to tag" },
      { file: "shots/8-end-card.mp4", caption: "8. End card" },
    ],
    privacy: ["Your first prompt ends with part of your email address. It gets cropped out.", "Everything in the app shots is made up. Your real lists never show."],
  },
  reel: {
    version: 1,
    caption: "Archidekt made me click through menus to tag every card, so I asked Studio to build me my own deck builder. 99 cards, zero menus. Made with Studio.",
    checks: ["Pauses and \"um\"s cut, every word kept", "Captions match what you said", "Music written for this reel", "Footage laid over your voice"],
  },
  takes: [{ name: "take-1.mp4", number: 1 }, { name: "take-2.mp4", number: 2 }],
  has_reel_video: true,
};

const STEPS = [
  { key: "app", title: "Pick your app", next: "Start the interview" },
  { key: "interview", title: "Answer a few questions", next: "Choose a tone", stage: "story" },
  { key: "tone", title: "Pick a tone", next: "Write my script", stage: "script" },
  { key: "script", title: "See your script", next: "Lock the script and film the app", stage: "footage" },
  { key: "footage", title: "Check the footage", next: "Film my take" },
  { key: "film", title: "Film your take", next: "Edit my reel", stage: "edit" },
  { key: "edit", title: "Watch your reel", next: null },
];
const stepIndex = (key) => STEPS.findIndex((s) => s.key === key);

// What the waiting screen says for each stage, and the step the creator lands on when Studio is done.
const STAGES = {
  research: { title: (app) => `Studio is reading up on ${app}`, items: ["Finding the chat you built it in", "Pulling out your first prompt", "Making a first guess at each answer"], lands: "interview" },
  story: { title: () => "Studio is finding your story", items: ["Reading your answers", "Picking the tones that fit"], lands: "tone" },
  script: { title: () => "Studio is writing your script", items: ["Finding the hook", "Trying story directions", "Writing every line", "Planning what's on screen"], lands: "script" },
  "revise-script": { title: () => "Studio is rewriting your script", items: ["Reading your note", "Rewriting the lines it touches", "Checking the story still holds"], lands: "script" },
  footage: { title: (app) => `Studio is filming ${app}`, items: ["Setting up a private copy with made-up data", "Filming your prompts from the build chat", "Filming the app", "Making the end card", "Checking nothing private shows"], lands: "footage" },
  edit: { title: () => "Studio is editing your reel", items: ["Cutting pauses, keeping every word", "Writing the captions", "Writing music for this reel", "Laying footage over your voice", "Checking every word survived"], lands: "edit" },
  "revise-reel": { title: () => "Studio is making your changes", items: ["Reading your note", "Re-cutting the reel", "Checking every word survived"], lands: "edit" },
};

const SHOT_LOOK = {
  face: { label: "You, talking to camera", bg: "#3a3a3a" },
  chat: { label: "The chat you built it in", bg: "#f4f1ea" },
  prompt: { label: "Your prompt, highlighted", bg: "#fffbe6" },
  app: { label: "Your app, on made-up data", bg: "#f6efe2" },
  end: { label: "Made with Studio", bg: "#492222" },
};

let reel = EXAMPLE ? EXAMPLE_REEL : null;
let current = 0;
let question = 0;
let answers = [];
let script = [];
let selectedApp = "";
let pendingStage = null;
let pollTimer = null;
let takesTimer = null;
const done = new Set();

const $ = (id) => document.getElementById(id);
const escapeHtml = (text) => String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const appName = () => reel?.interview?.app || reel?.request?.app?.display_name || "your app";
const mediaUrl = (file) => (EXAMPLE ? `/_media/deck-list-reel/${file}` : `/api/reels/${reelId}/files/${file}`);
const reelVideoUrl = () => (EXAMPLE ? "/_media/deck-list-reel/deck-list-reel.mp4" : `/api/reels/${reelId}/files/reel.mp4?v=${reel?.reel?.version || 1}`);

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "Something went wrong. Try again.");
  return body;
}

// Studio's chat for this reel, in the workspace's chat app (same workspace address, with the chat app's name).
function chatLink() {
  const chatId = reel?.state?.chat_id;
  if (!chatId) return "";
  const host = location.hostname.replace(/^reel-maker([.-])/, "chat$1");
  const base = host !== location.hostname ? `${location.protocol}//${host}${location.port ? ":" + location.port : ""}` : document.body.dataset.chatAddress || "";
  return base ? `${base.replace(/\/$/, "")}/?chat=${encodeURIComponent(chatId)}` : "";
}

function renderStepper() {
  $("stepper").innerHTML = STEPS.map((s, i) => {
    const state = i === current ? (pendingStage ? "current working" : "current") : done.has(i) ? "done" : "";
    const locked = !EXAMPLE && i > current && !done.has(i);
    return `<button class="stepper-item ${state}" data-index="${i}" ${locked || pendingStage ? "disabled" : ""}>
      <span class="num">${done.has(i) && i !== current ? "&#10003;" : i + 1}</span>${s.title}</button>`;
  }).join("");
  $("stepper").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    const index = Number(b.dataset.index);
    // In the example run any step can be jumped to; the steps before it count as done.
    if (EXAMPLE) for (let j = 0; j < index; j += 1) done.add(j);
    go(index);
  }));
  $("stepper").querySelector(".current")?.scrollIntoView({ block: "nearest", inline: "center" });
}

function go(index) {
  clearTimeout(pollTimer);
  clearTimeout(takesTimer);
  pendingStage = null;
  current = index;
  for (let j = 0; j < index; j += 1) done.add(j);
  document.querySelectorAll(".step").forEach((el) => { el.hidden = el.dataset.step !== STEPS[index].key; });
  const step = STEPS[index];
  document.querySelector(".step-nav").hidden = false;
  $("next").hidden = !step.next;
  $("next").disabled = false;
  $("next").textContent = step.next || "";
  $("back").style.visibility = index === 0 ? "hidden" : "visible";
  $("project-name").textContent = reel ? `${appName()} reel` : "";
  ({ app: renderApps, interview: renderQuestion, tone: renderTones, script: renderScript, footage: renderFootage, film: renderFilm, edit: renderEdit })[step.key]();
  document.querySelectorAll(".step video").forEach((v) => (v.closest(".step").hidden ? v.pause() : null));
  renderStepper();
  $("panel").scrollTop = 0;
}

// ---- Step 1: pick the app ----
async function renderApps() {
  if (EXAMPLE) {
    $("app-grid").innerHTML = `<button class="app-tile selected"><span class="tile-icon" style="background:#492222;color:#F5D6A0">DL</span><b>Deck List</b><span>Magic deck builder with drag-to-tag</span></button>`;
    return;
  }
  if (reel) {
    const app = reel.request.app;
    $("app-grid").innerHTML = `<div class="app-tile selected"><b>${escapeHtml(app.display_name)}</b><span>${escapeHtml(app.description)}</span></div>`;
    $("next").textContent = "Continue";
    return;
  }
  $("next").disabled = !selectedApp;
  const [{ apps }, { reels }] = await Promise.all([api("/api/apps"), api("/api/reels")]);
  $("app-grid").innerHTML = apps.length ? apps.map((a) => `
    <button class="app-tile ${a.name === selectedApp ? "selected" : ""}" data-app="${escapeHtml(a.name)}">
      ${a.icon ? `<img class="tile-icon" alt="" src="data:image/svg+xml,${encodeURIComponent(a.icon)}">` : `<span class="tile-icon">${escapeHtml(a.display_name.slice(0, 2))}</span>`}
      <b>${escapeHtml(a.display_name)}</b><span>${escapeHtml(a.description)}</span></button>`).join("")
    : `<p class="lede">You haven't built an app in this workspace yet. Build one in a Studio chat, then come back.</p>`;
  $("app-grid").querySelectorAll("[data-app]").forEach((tile) => tile.addEventListener("click", () => {
    selectedApp = tile.dataset.app;
    $("app-grid").querySelectorAll(".app-tile").forEach((t) => t.classList.toggle("selected", t === tile));
    $("next").disabled = false;
  }));
  $("past-reels").hidden = reels.length === 0;
  $("past-reel-list").innerHTML = reels.map((r) => `<a class="past-reel" href="/?reel=${escapeHtml(r.id)}">${escapeHtml(r.app)} <span>${new Date(r.created_at * 1000).toLocaleString()}</span></a>`).join("");
}

// ---- Step 2: the interview ----
function renderQuestion() {
  const questions = reel.interview?.questions || [];
  if (!answers.length) answers = (reel.answers?.answers || questions.map(() => "")).slice();
  const item = questions[question];
  if (!item) return;
  $("q-count").textContent = `Question ${question + 1} of ${questions.length}`;
  $("q-bar").style.width = `${((question + 1) / questions.length) * 100}%`;
  $("question-host").innerHTML = `
    <h1>${escapeHtml(item.q)}</h1>
    <p class="lede">${escapeHtml(item.help)}</p>
    ${item.quote ? `<blockquote>${escapeHtml(item.quote)}</blockquote>` : ""}
    <div class="guess"><span>Studio's guess</span><p>${escapeHtml(item.guess)}</p><button class="ghost small" id="use-guess">That's right</button></div>
    <textarea id="answer" rows="4" placeholder="In your own words. Short is fine; specific details help most.">${escapeHtml(answers[question] || "")}</textarea>`;
  $("use-guess").addEventListener("click", () => { $("answer").value = item.guess; answers[question] = item.guess; });
  $("answer").addEventListener("input", (e) => { answers[question] = e.target.value; });
  $("q-prev").disabled = question === 0;
  $("q-next").textContent = question === questions.length - 1 ? "Done with questions" : "Next question";
}

// ---- Step 3: tone ----
function renderTones() {
  const tones = reel.tones || { tones: [] };
  const chosen = reel.choice?.tone || tones.tones.find((t) => t.recommended)?.key || tones.tones[0]?.key;
  $("story-line").textContent = tones.story ? `The story: ${tones.story}` : "";
  $("tones").innerHTML = tones.tones.map((t) => `
    <label class="tone"><input type="radio" name="tone" value="${escapeHtml(t.key)}" ${t.key === chosen ? "checked" : ""}>
      <div><b>${escapeHtml(t.name)}</b> ${t.recommended ? '<em class="badge">Studio\'s pick</em>' : ""}<p>"${escapeHtml(t.hook)}"</p></div></label>`).join("");
}

// ---- Step 4: script and storyboard ----
function renderScript() {
  script = (reel.script?.lines || []).map((line) => ({ ...line }));
  const directions = reel.tones?.directions || [];
  const direction = directions.find((d) => d.key === (reel.script?.direction || reel.choice?.direction)) || directions.find((d) => d.recommended);
  $("direction-text").textContent = direction ? `${direction.name}. ${direction.summary}` : reel.tones?.story || "";
  $("other-directions").hidden = directions.length < 2;
  $("script-lines").innerHTML = script.map((line, i) => `
    <li data-line="${i}">
      <div class="say" contenteditable="true" spellcheck="false">${escapeHtml(line.say)}</div>
      <div class="screen-note">On screen: ${escapeHtml(line.screen)}</div>
    </li>`).join("");
  $("script-lines").querySelectorAll(".say").forEach((el, i) => el.addEventListener("input", () => { script[i].say = el.textContent; }));
  const total = script.reduce((sum, l) => sum + secondsFor(l.say), 0);
  $("animatic-time").textContent = `0:00 / ${fmt(total)}`;
  if (script.length) showBeat(0);
}

const secondsFor = (text) => Math.max(1.6, text.split(/\s+/).length / 2.7);
const fmt = (s) => `0:${String(Math.round(s)).padStart(2, "0")}`;
let animaticTimer = null;

function showBeat(i) {
  const line = script[i];
  const look = SHOT_LOOK[line.shot] || SHOT_LOOK.app;
  const shot = $("animatic-shot");
  shot.style.background = look.bg;
  shot.className = `shot shot-${line.shot}`;
  shot.textContent = line.shot === "app" ? `${appName()}, on made-up data` : line.shot === "end" ? `${appName()}\nMade with Studio` : look.label;
  $("animatic-face").hidden = line.shot === "face" || line.shot === "end";
  $("animatic-caption").textContent = line.say;
  $("script-lines").querySelectorAll("li").forEach((li, j) => li.classList.toggle("playing", j === i));
}

function playAnimatic() {
  clearTimeout(animaticTimer);
  const total = script.reduce((sum, l) => sum + secondsFor(l.say), 0);
  let i = 0;
  let elapsed = 0;
  $("animatic").classList.add("running");
  const step = () => {
    if (i >= script.length) {
      $("animatic").classList.remove("running");
      $("script-lines").querySelectorAll("li").forEach((li) => li.classList.remove("playing"));
      return;
    }
    showBeat(i);
    $("animatic-time").textContent = `${fmt(elapsed)} / ${fmt(total)}`;
    const length = secondsFor(script[i].say);
    elapsed += length;
    i += 1;
    animaticTimer = setTimeout(step, length * 1000);
  };
  step();
}

// ---- Step 5: footage ----
function renderFootage() {
  const footage = reel.footage || { clips: [], privacy: [] };
  $("clips").innerHTML = footage.clips.map((c) => `
    <figure><video src="${escapeHtml(mediaUrl(c.file))}" muted loop playsinline autoplay></video><figcaption>${escapeHtml(c.caption)}</figcaption></figure>`).join("");
  $("privacy-list").innerHTML = (footage.privacy || []).map((p) => `<li>${escapeHtml(p)}</li>`).join("");
}

// ---- Step 6: film the take on the phone ----
function renderFilm() {
  const phonePath = EXAMPLE ? "phone?example=1" : `phone?reel=${encodeURIComponent(reelId)}`;
  const target = (document.body.dataset.publicAddress || location.origin + "/") + phonePath;
  $("qr").src = "/qr.svg?data=" + encodeURIComponent(target);
  $("phone-url").href = target;
  $("phone-url").textContent = target;
  $("phone-link").href = "/" + phonePath;
  document.querySelector(".on-phone").href = "/" + phonePath;
  $("simulate-take").hidden = true;
  renderTakes();
  if (!EXAMPLE) {
    const poll = async () => {
      try { reel = (await api(`/api/reels/${reelId}`)).reel; renderTakes(); } catch (error) { /* try again next tick */ }
      takesTimer = setTimeout(poll, 3000);
    };
    takesTimer = setTimeout(poll, 3000);
  }
}

function renderTakes() {
  const takes = reel.takes || [];
  const chosen = reel.choice?.take || takes[takes.length - 1]?.name;
  $("desk-takes").innerHTML = takes.length
    ? takes.map((t) => `<div class="take-row got ${t.name === chosen ? "chosen" : ""}"><span class="dot"></span> Take ${t.number} &middot; from your phone ${t.name === chosen ? '<em class="badge">Using this one</em>' : ""}</div>`).join("")
    : '<div class="take-row waiting"><span class="dot"></span> Waiting for your take...</div>';
  if (current === stepIndex("film")) $("next").disabled = !takes.length;
}

// ---- Step 7: the reel ----
function renderEdit() {
  const result = reel.reel || {};
  $("edit-version").textContent = `Version ${result.version || 1}`;
  if ($("final-video").dataset.src !== reelVideoUrl()) {
    $("final-video").src = reelVideoUrl();
    $("final-video").dataset.src = reelVideoUrl();
  }
  $("reel-checks").innerHTML = (result.checks || []).map((c) => `<li class="done">${escapeHtml(c)}</li>`).join("");
  $("reel-notes").innerHTML = (result.notes || []).map((n) => `<li>${escapeHtml(n)}</li>`).join("");
  const appSlug = (reel.request?.app?.name || "my-app").replace(/[^a-z0-9-]/gi, "");
  renderShare($("desk-share"), { videoUrl: reelVideoUrl(), fileName: `${appSlug}-reel.mp4`, caption: result.caption || "" });
}

// ---- Waiting on Studio ----
function showPending(stage, landsOn) {
  clearTimeout(pollTimer);
  pendingStage = stage;
  current = stepIndex(landsOn ?? STAGES[stage].lands);
  document.querySelectorAll(".step").forEach((el) => { el.hidden = el.dataset.step !== "pending"; });
  document.querySelectorAll(".step video").forEach((v) => v.pause());
  document.querySelector(".step-nav").hidden = true;
  $("pending-title").textContent = STAGES[stage].title(appName());
  $("pending-error").hidden = true;
  $("skip-wait").hidden = !EXAMPLE;
  const link = chatLink();
  $("pending-chat").hidden = !link;
  $("pending-chat").href = link || "#";
  renderStepper();
  $("panel").scrollTop = 0;
  if (EXAMPLE) { tickExample(STAGES[stage].items, 0); return; }
  poll();
}

function drawItems(items) {
  $("pending-list").innerHTML = items.map((item) => `<li class="${item.state === "done" ? "done" : item.state === "active" ? "active" : ""}">${escapeHtml(item.label)}</li>`).join("");
}

function tickExample(labels, active) {
  drawItems(labels.map((label, i) => ({ label, state: i < active ? "done" : i === active ? "active" : "todo" })));
  if (active > labels.length) { go(current); return; }
  pollTimer = setTimeout(() => tickExample(labels, active + 1), 1100);
}

async function poll() {
  try {
    reel = (await api(`/api/reels/${reelId}`)).reel;
  } catch (error) {
    pollTimer = setTimeout(poll, 4000);
    return;
  }
  const status = reel.status || {};
  const items = status.items?.length ? status.items : STAGES[pendingStage].items.map((label, i) => ({ label, state: i === 0 ? "active" : "todo" }));
  drawItems(items);
  if (status.stage === pendingStage && status.state === "done") {
    answers = [];
    go(current);
    return;
  }
  if (status.stage === pendingStage && status.state === "failed") {
    $("pending-error").hidden = false;
    $("pending-error").textContent = `Studio got stuck: ${status.error || "it didn't say why"}. Open its chat to see what happened, or go back and try again.`;
    document.querySelector(".step-nav").hidden = false;
    $("next").hidden = true;
    return;
  }
  pollTimer = setTimeout(poll, 2500);
}

async function advance(stage, inputs, landsOn) {
  if (EXAMPLE) { showPending(stage, landsOn); return; }
  $("next").disabled = true;
  try {
    reel = (await api(`/api/reels/${reelId}/advance`, { method: "POST", body: JSON.stringify({ stage, inputs }) })).reel;
    showPending(stage, landsOn);
  } catch (error) {
    $("next").disabled = false;
    alert(error.message);
  }
}

// ---- Buttons ----
$("next").addEventListener("click", async () => {
  const key = STEPS[current].key;
  if (key === "app") {
    if (EXAMPLE) { done.add(current); showPending("research"); return; }
    if (reel) { go(stepIndex("interview")); return; }
    $("next").disabled = true;
    try {
      reel = (await api("/api/reels", { method: "POST", body: JSON.stringify({ app: selectedApp }) })).reel;
      reelId = reel.id;
      history.replaceState(null, "", `/?reel=${reelId}`);
      showPending("research");
    } catch (error) {
      $("next").disabled = false;
      alert(error.message);
    }
    return;
  }
  if (key === "interview") return advance("story", { answers: { answers } });
  if (key === "tone") {
    const tone = document.querySelector('input[name="tone"]:checked')?.value || "";
    const direction = reel.tones?.directions?.find((d) => d.recommended)?.key || "";
    return advance("script", { choice: { tone, direction } });
  }
  if (key === "script") return advance("footage", { script: { ...reel.script, lines: script } });
  if (key === "footage") { go(stepIndex("film")); return; }
  if (key === "film") return advance("edit", { choice: { take: reel.choice?.take || reel.takes[reel.takes.length - 1]?.name } });
});
$("back").addEventListener("click", () => go(Math.max(current - 1, 0)));
$("q-next").addEventListener("click", () => {
  const count = reel.interview?.questions?.length || 0;
  if (question < count - 1) { question += 1; renderQuestion(); } else { $("next").click(); }
});
$("q-prev").addEventListener("click", () => { if (question > 0) { question -= 1; renderQuestion(); } });
$("skip-wait").addEventListener("click", () => go(current));
$("animatic-play").addEventListener("click", playAnimatic);
$("other-directions").addEventListener("click", () => {
  const directions = reel.tones?.directions || [];
  $("script-ask").value = "Try a different direction: " + directions.filter((d) => !d.recommended).map((d) => d.name).join(" or ");
  $("script-ask").focus();
});
// A change asked for on a step comes back to that same step once Studio has made it.
$("script-ask-send").addEventListener("click", () => {
  const text = $("script-ask").value.trim();
  if (!text) return;
  $("script-ask").value = "";
  advance("revise-script", { script: { ...reel.script, lines: script }, change: { text } }, "script");
});
$("edit-ask-send").addEventListener("click", () => {
  const text = $("edit-ask").value.trim();
  if (!text) return;
  $("edit-ask").value = "";
  if (EXAMPLE && reel.reel) reel.reel.version = (reel.reel.version || 1) + 1;
  advance("revise-reel", { change: { text } }, "edit");
});
$("copy-phone-url").addEventListener("click", async () => {
  await navigator.clipboard.writeText($("phone-url").href);
  $("copy-phone-url").textContent = "Copied";
});

// Where a reel picks up again: a stage still running shows the waiting screen; a finished one lands on its step.
function resume() {
  const status = reel.status || {};
  const stage = STAGES[status.stage] ? status.stage : "research";
  if (status.state === "working" || status.state === "failed") { showPending(stage); return; }
  if (stage === "footage" && (reel.takes || []).length) { go(stepIndex("film")); return; }
  go(stepIndex(STAGES[stage].lands));
}

async function start() {
  $("start-own").addEventListener("click", () => { $("welcome").hidden = true; $("layout").hidden = false; go(0); });
  if (EXAMPLE) {
    document.body.classList.add("example");
    $("example-banner").hidden = false;
    $("example-link").hidden = true;
    $("skip-wait").textContent = "Skip ahead";
    go(0);
    return;
  }
  if (reelId) {
    try {
      reel = (await api(`/api/reels/${reelId}`)).reel;
      $("welcome").hidden = true;
      $("layout").hidden = false;
      resume();
      return;
    } catch (error) {
      history.replaceState(null, "", "/");
      reelId = "";
    }
  }
  $("layout").hidden = true;
  $("welcome").hidden = false;
}

start();
