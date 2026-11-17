// Mock of the phone page: the locked script, and one big button that opens the phone's camera.
const LINES = [
  "Putting one card in three categories on Archidekt? That's a lot of clicking.",
  "So I asked Studio to build me my own.",
  "First: copy all of Scryfall. Every card, every tag.",
  "Then: a place to write down card names, with autocomplete. That's it.",
  "Search is instant. Even the pictures pop right in.",
  "And tagging? I just drag a card toward a category.",
  "Search, add, tag. All on one screen.",
  "Ninety-nine cards. Zero menus.",
];

const EXAMPLE = new URLSearchParams(location.search).has("example");
const POST_CAPTION = "Archidekt made me click through menus to tag every card, so I asked Studio to build me my own deck builder. 99 cards, zero menus. Made with Studio.";
const takes = [];
let chosen = -1;

document.getElementById("prompter").innerHTML = LINES.map((line, i) => `<p><span>${i + 1}</span>${line}</p>`).join("");

function renderTakes() {
  const section = document.getElementById("phone-takes");
  section.hidden = takes.length === 0;
  document.getElementById("take-list").innerHTML = takes.map((take, i) => `
    <div class="phone-take ${i === chosen ? "chosen" : ""}">
      <video src="${take.url}" controls playsinline preload="metadata"></video>
      <div class="phone-take-row">
        <b>Take ${i + 1}</b>
        <span class="sent">Sent to Studio</span>
        ${i === chosen ? '<em class="badge">Using this one</em>' : `<button class="ghost small" data-use="${i}">Use this take</button>`}
      </div>
    </div>`).reverse().join("");
  document.querySelectorAll("[data-use]").forEach((b) => b.addEventListener("click", () => { chosen = Number(b.dataset.use); renderTakes(); }));
  document.getElementById("record-text").textContent = takes.length ? "Record another take" : "Record your take";
}

document.getElementById("record-input").addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (!file) return;
  takes.push({ url: URL.createObjectURL(file), name: file.name });
  chosen = takes.length - 1;
  event.target.value = "";
  renderTakes();
  window.scrollTo({ top: 0, behavior: "smooth" });
});

function showReady() {
  document.getElementById("phone-ready").hidden = false;
  renderShare(document.getElementById("phone-share"), {
    videoUrl: "/_media/deck-list-reel/deck-list-reel.mp4", fileName: "deck-list-reel.mp4", caption: POST_CAPTION,
  });
}

if (EXAMPLE) {
  // Example mode: the edit is done, so the phone shows the finished reel with its save and share buttons first.
  document.getElementById("example-banner").hidden = false;
  showReady();
} else {
  // Mock: once a take is in, a button stands in for Studio finishing the edit.
  const pretend = document.createElement("button");
  pretend.className = "ghost small pretend";
  pretend.textContent = "Pretend the edit finished (mock only)";
  pretend.addEventListener("click", () => { pretend.remove(); showReady(); window.scrollTo({ top: 0 }); });
  document.getElementById("phone-takes").appendChild(pretend);
}
