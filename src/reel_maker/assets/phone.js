// The phone page: the reel's script in large type, one big button that opens the phone's camera, every take sent to
// the app as it is recorded, and the finished reel with save and share buttons. ?reel=<id> is a real reel;
// ?example=1 shows the Deck List example.
const params = new URLSearchParams(location.search);
const EXAMPLE = params.has("example");
const reelId = params.get("reel") || "";
const EXAMPLE_LINES = [
  "Putting one card in three categories on Archidekt? That's a lot of clicking.",
  "So I asked Studio to build me my own.",
  "First: copy all of Scryfall. Every card, every tag.",
  "Then: a place to write down card names, with autocomplete. That's it.",
  "Search is instant. Even the pictures pop right in.",
  "And tagging? I just drag a card toward a category.",
  "Search, add, tag. All on one screen.",
  "Ninety-nine cards. Zero menus.",
];
const EXAMPLE_CAPTION = "Archidekt made me click through menus to tag every card, so I asked Studio to build me my own deck builder. 99 cards, zero menus. Made with Studio.";

const $ = (id) => document.getElementById(id);
const escapeHtml = (text) => String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fileUrl = (name) => `/api/reels/${encodeURIComponent(reelId)}/files/${name}`;
let reel = null;
let shownReelVersion = null;
let uploading = false;

function renderScript(lines) {
  $("prompter").innerHTML = lines.map((line, i) => `<p><span>${i + 1}</span>${escapeHtml(line)}</p>`).join("");
}

function renderTakes() {
  const takes = reel?.takes || [];
  const chosen = reel?.choice?.take || takes[takes.length - 1]?.name;
  $("phone-takes").hidden = takes.length === 0;
  $("take-list").innerHTML = takes.slice().reverse().map((take) => `
    <div class="phone-take ${take.name === chosen ? "chosen" : ""}">
      <video src="${fileUrl(take.name)}" controls playsinline preload="metadata"></video>
      <div class="phone-take-row">
        <b>Take ${take.number}</b>
        <span class="sent">Sent to Studio</span>
        ${take.name === chosen ? '<em class="badge">Using this one</em>' : `<button class="ghost small" data-use="${escapeHtml(take.name)}">Use this take</button>`}
      </div>
    </div>`).join("");
  $("take-list").querySelectorAll("[data-use]").forEach((button) => button.addEventListener("click", async () => {
    const response = await fetch(`/api/reels/${encodeURIComponent(reelId)}/choose-take`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ take: button.dataset.use }),
    });
    if (response.ok) { reel = (await response.json()).reel; renderTakes(); }
  }));
  $("record-text").textContent = takes.length ? "Record another take" : "Record your take";
}

function showReady(videoUrl, fileName, caption) {
  $("phone-ready").hidden = false;
  $("ready-video").src = videoUrl;
  renderShare($("phone-share"), { videoUrl, fileName, caption });
}

function showMessage(text) {
  $("phone-message").hidden = !text;
  $("phone-message").textContent = text || "";
}

// Send a take straight to the reel's folder, with a progress bar: phone videos run to hundreds of megabytes.
function upload(file) {
  uploading = true;
  $("upload-progress").hidden = false;
  $("upload-text").textContent = "Sending your take to Studio...";
  $("upload-bar").style.width = "0%";
  const request = new XMLHttpRequest();
  request.open("POST", `/api/reels/${encodeURIComponent(reelId)}/takes`);
  request.setRequestHeader("Content-Type", file.type && file.type.startsWith("video/") ? file.type : "video/mp4");
  request.upload.onprogress = (event) => {
    if (event.lengthComputable) $("upload-bar").style.width = `${Math.round((event.loaded / event.total) * 100)}%`;
  };
  request.onload = async () => {
    uploading = false;
    if (request.status >= 300) {
      $("upload-text").textContent = "Couldn't send that take. Check your connection and record it again.";
      return;
    }
    $("upload-progress").hidden = true;
    await refresh();
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  request.onerror = () => {
    uploading = false;
    $("upload-text").textContent = "Couldn't send that take. Check your connection and record it again.";
  };
  request.send(file);
}

$("record-input").addEventListener("change", (event) => {
  const file = event.target.files[0];
  event.target.value = "";
  if (!file) return;
  if (EXAMPLE) { showMessage("This is the example run, so takes aren't sent anywhere. Start your own reel to film one."); return; }
  upload(file);
});

async function refresh() {
  const response = await fetch(`/api/reels/${encodeURIComponent(reelId)}`);
  if (!response.ok) { showMessage("This reel couldn't be found. Scan the code on your computer again."); return; }
  reel = (await response.json()).reel;
  $("phone-title").textContent = `${reel.interview?.app || reel.request?.app?.display_name || "Your"} reel`;
  const lines = (reel.script?.lines || []).map((line) => line.say);
  renderScript(lines);
  showMessage(lines.length ? "" : "Studio hasn't written your script yet. Finish the steps on your computer first.");
  if (!uploading) renderTakes();
  const version = reel.reel?.version;
  // Only a finished cut: while Studio is editing, the file may be half written.
  const editing = ["edit", "revise-reel"].includes(reel.status?.stage) && reel.status?.state !== "done";
  if (reel.has_reel_video && reel.reel && !editing && version !== shownReelVersion) {
    shownReelVersion = version;
    const slug = (reel.request?.app?.name || "my-app").replace(/[^a-z0-9-]/gi, "");
    showReady(`${fileUrl("reel.mp4")}?v=${version || 1}`, `${slug}-reel.mp4`, reel.reel?.caption || "");
  }
}

if (EXAMPLE) {
  // Example mode: the edit is done, so the phone shows the finished reel with its save and share buttons first.
  $("example-banner").hidden = false;
  $("phone-title").textContent = "Deck List reel";
  renderScript(EXAMPLE_LINES);
  showReady("/_media/deck-list-reel/deck-list-reel.mp4", "deck-list-reel.mp4", EXAMPLE_CAPTION);
} else if (!reelId) {
  showMessage("Open this page from the QR code on your computer's Film your take step.");
  $("record-label").hidden = true;
} else {
  refresh();
  // The reel shows up here when Studio finishes the edit, without reloading.
  setInterval(() => { if (!uploading) refresh(); }, 5000);
}
