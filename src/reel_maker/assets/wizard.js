// Mock of the Reel maker walkthrough: every value here is hard-coded sample content (the Deck List reel). The same
// content is what example mode (?example=1) walks through once the real flow is built.
const EXAMPLE = new URLSearchParams(location.search).has("example");
const REEL_VIDEO = "/_media/deck-list-reel/deck-list-reel.mp4";
const POST_CAPTION = "Archidekt made me click through menus to tag every card, so I asked Studio to build me my own deck builder. 99 cards, zero menus. Made with Studio.";
const STEPS = [
  { key: "app", title: "Pick your app", next: "Start the interview",
    pending: { title: "Studio is reading up on Deck List", items: ["Finding the chat you built it in", "Pulling out your first prompt", "Making a first guess at each answer"] } },
  { key: "interview", title: "Answer a few questions", next: "Choose a tone",
    pending: { title: "Studio is finding your story", items: ["Reading your answers", "Picking the tones that fit Deck List"] } },
  { key: "tone", title: "Pick a tone", next: "Write my script",
    pending: { title: "Studio is writing your script", items: ["Finding the hook", "Trying three story directions", "Writing every line", "Planning what's on screen"] } },
  { key: "script", title: "See your script", next: "Lock the script and film the app",
    pending: { title: "Studio is filming your app", items: ["Setting up a private copy with made-up data", "Filming your prompts from the build chat", "Filming the app", "Making the end card", "Checking nothing private shows"] } },
  { key: "footage", title: "Check the footage", next: "Film my take" },
  { key: "film", title: "Film your take", next: "Edit my reel",
    pending: { title: "Studio is editing your reel", items: ["Cutting pauses, keeping every word", "Writing the captions", "Writing music for this reel", "Laying footage over your voice", "Checking every word survived"] } },
  { key: "edit", title: "Watch your reel", next: null },
];

const QUESTIONS = [
  { q: "What's the most interesting thing about Deck List?", help: "The part a stranger would say \"wait, it does that?\" about.",
    guess: "Drag-to-tag. You pick up a card, the screen splits into zones, and you drop it on one to tag it.",
    answer: "Drag-to-tag, and having all of Scryfall locally so everything is super snappy." },
  { q: "What was deckbuilding like before it?", help: "The annoyance, the mess, the thing you kept putting off.",
    guess: "Tools like Archidekt make you tag cards from a menu, one card and one tag at a time.",
    answer: "Archidekt, and multi-tagging one card was a pain." },
  { q: "What made you finally build it?", help: "The moment that tipped it, if there was one.",
    guess: "Building the 99 for your Ulalek deck.", answer: "" },
  { q: "What was the most fun or easiest part of building it?", help: "The specific moment: one sentence you typed, the first time it worked.",
    guess: "The first time autocomplete worked.", answer: "Getting all the Scryfall data and tags loaded locally." },
  { q: "Is this what you typed to start it?", help: "Studio found this in the chat where you built Deck List. Your real words beat a paraphrase.",
    quote: "i'm building a list of 99 for my ulalek deck, i kind of just need, to start with, a place to write down card names and have them autocomplete. Once i see that i'll know what else i want",
    guess: "Yes, use that one.", answer: "Yes, use that one." },
  { q: "What surprised you?", help: "Something it did that you didn't expect, or did better than you pictured.",
    guess: "Auto-tag sorting your lands and ramp correctly.", answer: "How fast the card images load." },
  { q: "What's different now?", help: "One concrete after-picture, not a list of features.",
    guess: "Your list sits at 99 cards, every one tagged.", answer: "Search, add and the deck are all on one screen." },
];

const SCRIPT = [
  { say: "Putting one card in three categories on Archidekt? That's a lot of clicking.", screen: "Your face, Studio icon in a corner", face: true, shot: "face" },
  { say: "So I asked Studio to build me my own.", screen: "The build chat, scrolling up", shot: "chat" },
  { say: "First: copy all of Scryfall. Every card, every tag.", screen: "Your first prompt, then a counter to 39,000 cards", shot: "prompt" },
  { say: "Then: a place to write down card names, with autocomplete. That's it.", screen: "Your second prompt, word for word", shot: "prompt" },
  { say: "Search is instant. Even the pictures pop right in.", screen: "Typing a name, the card appears with its picture", shot: "app" },
  { say: "And tagging? I just drag a card toward a category.", screen: "A card dragged onto \"ramp\", it gets its tag", shot: "app" },
  { say: "Search, add, tag. All on one screen.", screen: "The full list, scrolling", shot: "app" },
  { say: "Ninety-nine cards. Zero menus.", screen: "End card: Deck List, its icon, \"Made with Studio\"", shot: "end" },
];

const SHOT_LOOK = {
  face: { label: "You, talking to camera", bg: "#3a3a3a" },
  chat: { label: "The chat you built it in", bg: "#f4f1ea" },
  prompt: { label: "Your prompt, highlighted", bg: "#fffbe6" },
  app: { label: "Deck List, on made-up data", bg: "#f6efe2" },
  end: { label: "Deck List\nMade with Studio", bg: "#492222" },
};

let current = 0;
// The step whose result Studio is preparing, or null when the user is on a step.
let pendingFor = null;
let pendingTimer = null;
let question = 0;
const done = new Set();

const $ = (id) => document.getElementById(id);

function renderStepper() {
  $("stepper").innerHTML = STEPS.map((s, i) => {
    const state = i === current ? (pendingFor === null ? "current" : "current working") : done.has(i) ? "done" : "";
    return `<button class="stepper-item ${state}" data-index="${i}" ${!EXAMPLE && i > current && !done.has(i) ? "disabled" : ""}>
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
  clearTimeout(pendingTimer);
  pendingFor = null;
  current = index;
  document.querySelectorAll(".step").forEach((el) => { el.hidden = el.dataset.step !== STEPS[index].key; });
  const step = STEPS[index];
  document.querySelector(".step-nav").hidden = false;
  $("next").hidden = !step.next;
  $("next").textContent = step.next || "";
  $("back").style.visibility = index === 0 ? "hidden" : "visible";
  document.querySelectorAll(".step video").forEach((v) => (v.closest(".step").hidden ? v.pause() : v.play().catch(() => {})));
  if (step.key === "interview") renderQuestion();
  if (step.key === "film") loadQr();
  renderStepper();
  $("panel").scrollTop = 0;
}

function renderQuestion() {
  const item = QUESTIONS[question];
  $("q-count").textContent = `Question ${question + 1} of ${QUESTIONS.length}`;
  $("q-bar").style.width = `${((question + 1) / QUESTIONS.length) * 100}%`;
  $("question-host").innerHTML = `
    <h1>${item.q}</h1>
    <p class="lede">${item.help}</p>
    ${item.quote ? `<blockquote>${item.quote}</blockquote>` : ""}
    <div class="guess"><span>Studio's guess</span><p>${item.guess}</p><button class="ghost small" id="use-guess">That's right</button></div>
    <textarea id="answer" rows="4" placeholder="In your own words. Short is fine; specific details help most.">${item.answer}</textarea>`;
  $("use-guess").addEventListener("click", () => { $("answer").value = item.guess; });
  $("answer").addEventListener("input", (e) => { item.answer = e.target.value; });
  $("q-prev").disabled = question === 0;
  $("q-next").textContent = question === QUESTIONS.length - 1 ? "Done with questions" : "Next question";
}

function renderScript() {
  $("script-lines").innerHTML = SCRIPT.map((line, i) => `
    <li data-line="${i}">
      <div class="say" contenteditable="true" spellcheck="false">${line.say}</div>
      <div class="screen-note">On screen: ${line.screen}</div>
    </li>`).join("");
  $("script-lines").querySelectorAll(".say").forEach((el, i) => el.addEventListener("input", () => { SCRIPT[i].say = el.textContent; }));
}

// Roughly how long a line takes to say, at an easy speaking pace.
const secondsFor = (text) => Math.max(1.6, text.split(/\s+/).length / 2.7);
let animaticTimer = null;

function showBeat(i) {
  const line = SCRIPT[i];
  const look = SHOT_LOOK[line.shot];
  const shot = $("animatic-shot");
  shot.style.background = look.bg;
  shot.className = `shot shot-${line.shot}`;
  shot.textContent = look.label;
  $("animatic-face").hidden = line.shot === "face" || line.shot === "end";
  $("animatic-caption").textContent = line.say;
  $("script-lines").querySelectorAll("li").forEach((li, j) => li.classList.toggle("playing", j === i));
}

function playAnimatic() {
  clearTimeout(animaticTimer);
  const total = SCRIPT.reduce((sum, l) => sum + secondsFor(l.say), 0);
  const fmt = (s) => `0:${String(Math.round(s)).padStart(2, "0")}`;
  let i = 0;
  let elapsed = 0;
  $("animatic").classList.add("running");
  const step = () => {
    if (i >= SCRIPT.length) {
      $("animatic").classList.remove("running");
      $("script-lines").querySelectorAll("li").forEach((li) => li.classList.remove("playing"));
      return;
    }
    showBeat(i);
    $("animatic-time").textContent = `${fmt(elapsed)} / ${fmt(total)}`;
    const length = secondsFor(SCRIPT[i].say);
    elapsed += length;
    i += 1;
    animaticTimer = setTimeout(step, length * 1000);
  };
  step();
}

function loadQr() {
  const target = (document.body.dataset.publicAddress || location.origin + "/") + "phone" + (EXAMPLE ? "?example=1" : "");
  $("qr").src = "/qr.svg?data=" + encodeURIComponent(target);
  $("phone-url").href = target;
  $("phone-url").textContent = target;
  $("phone-link").href = EXAMPLE ? "/phone?example=1" : "/phone";
  document.querySelector(".on-phone").href = $("phone-link").href;
}

// Mock: the waiting screen ticks through what Studio is doing, then moves on to the next step.
function showPending(fromIndex, pending = STEPS[fromIndex].pending, target = fromIndex + 1) {
  pendingFor = target;
  current = target;
  document.querySelectorAll(".step").forEach((el) => { el.hidden = el.dataset.step !== "pending"; });
  document.querySelectorAll(".step video").forEach((v) => v.pause());
  document.querySelector(".step-nav").hidden = true;
  $("pending-title").textContent = pending.title;
  renderStepper();
  let active = 0;
  const tick = () => {
    $("pending-list").innerHTML = pending.items.map((item, i) =>
      `<li class="${i < active ? "done" : i === active ? "active" : ""}">${item}</li>`).join("");
    if (active > pending.items.length) { const target = pendingFor; go(target); if (pending.after) pending.after(); return; }
    active += 1;
    pendingTimer = setTimeout(tick, 1100);
  };
  tick();
  $("panel").scrollTop = 0;
}

$("next").addEventListener("click", () => {
  done.add(current);
  if (STEPS[current].pending) showPending(current);
  else go(Math.min(current + 1, STEPS.length - 1));
});
$("back").addEventListener("click", () => go(Math.max(current - 1, 0)));
$("q-next").addEventListener("click", () => {
  if (question < QUESTIONS.length - 1) { question += 1; renderQuestion(); } else { $("next").click(); }
});
$("q-prev").addEventListener("click", () => { if (question > 0) { question -= 1; renderQuestion(); } });
$("skip-wait").addEventListener("click", () => go(pendingFor));
let version = 1;
// A change asked for on a step comes back to that same step once Studio has made it.
$("script-ask-send").addEventListener("click", () => {
  if (!$("script-ask").value.trim()) return;
  $("script-ask").value = "";
  showPending(current, { title: "Studio is rewriting your script", items: ["Reading your note", "Rewriting the lines it touches", "Checking the story still holds"] }, current);
});
$("edit-ask-send").addEventListener("click", () => {
  if (!$("edit-ask").value.trim()) return;
  $("edit-ask").value = "";
  showPending(current, {
    title: "Studio is making your changes",
    items: ["Reading your note", "Re-cutting the reel", "Checking every word survived"],
    after: () => { version += 1; $("edit-version").textContent = `Version ${version}`; },
  }, current);
});
$("animatic-play").addEventListener("click", playAnimatic);
$("other-directions").addEventListener("click", () => alert("Mock: shows two other story directions (a small mystery, a matter-of-fact tour) to swap in."));
document.querySelectorAll(".app-tile").forEach((tile) => tile.addEventListener("click", () => {
  document.querySelectorAll(".app-tile").forEach((t) => t.classList.remove("selected"));
  tile.classList.add("selected");
}));
function showTakes() {
  $("simulate-take").hidden = true;
  $("desk-takes").innerHTML = `
    <div class="take-row got"><span class="dot"></span> Take 1 &middot; 0:34 &middot; from your phone</div>
    <div class="take-row got chosen"><span class="dot"></span> Take 2 &middot; 0:32 &middot; from your phone <em class="badge">Using this one</em></div>`;
}
$("simulate-take").addEventListener("click", showTakes);
$("copy-phone-url").addEventListener("click", async () => {
  await navigator.clipboard.writeText($("phone-url").href);
  $("copy-phone-url").textContent = "Copied";
});

renderScript();
showBeat(0);
renderShare($("desk-share"), { videoUrl: REEL_VIDEO, fileName: "deck-list-reel.mp4", caption: POST_CAPTION });
$("start-own").addEventListener("click", () => { $("welcome").hidden = true; $("layout").hidden = false; go(0); });
if (EXAMPLE) {
  // Example mode: the whole flow, already filled in, so people can see every step before making their own.
  document.body.classList.add("example");
  $("example-banner").hidden = false;
  $("example-link").hidden = true;
  showTakes();
  $("skip-wait").textContent = "Skip ahead";
  go(0);
} else {
  $("layout").hidden = true;
  $("welcome").hidden = false;
}
