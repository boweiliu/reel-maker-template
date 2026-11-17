// Save and share the finished reel. On a phone the share sheet is the way in (it lists TikTok, Instagram and the
// rest, with the video attached); on a computer the video is saved and the site's upload page opens.
const PLATFORMS = [
  { name: "TikTok", upload: "https://www.tiktok.com/upload" },
  { name: "Instagram", upload: "https://www.instagram.com/" },
  { name: "YouTube Shorts", upload: "https://www.youtube.com/upload" },
  { name: "X", upload: "https://x.com/compose/post" },
  { name: "LinkedIn", upload: "https://www.linkedin.com/feed/?shareActive=true" },
];

function renderShare(root, { videoUrl, fileName, caption }) {
  root.innerHTML = `
    <div class="share-main">
      <a class="primary" data-role="save" href="${videoUrl}" download="${fileName}">Save the video</a>
      <button class="primary dark" data-role="share" hidden>Share...</button>
    </div>
    <div class="share-label">Post it to</div>
    <div class="share-platforms">
      ${PLATFORMS.map((p, i) => `<button class="platform" data-platform="${i}">${p.name}</button>`).join("")}
    </div>
    <div class="share-label">Caption</div>
    <div class="share-caption">
      <textarea rows="3" data-role="caption">${caption}</textarea>
      <button class="ghost small" data-role="copy">Copy caption</button>
    </div>
    <p class="note share-status" data-role="status" hidden></p>`;

  const q = (role) => root.querySelector(`[data-role="${role}"]`);
  const status = (text) => { q("status").hidden = false; q("status").textContent = text; };
  const captionText = () => q("caption").value;
  const isPhone = matchMedia("(pointer: coarse)").matches;
  let file = null;

  async function videoFile() {
    if (!file) {
      const blob = await (await fetch(videoUrl)).blob();
      file = new File([blob], fileName, { type: "video/mp4" });
    }
    return file;
  }
  async function openShareSheet() {
    status("Getting the video ready...");
    const f = await videoFile();
    if (!navigator.canShare || !navigator.canShare({ files: [f] })) return false;
    try {
      await navigator.share({ files: [f], text: captionText() });
      status("Shared.");
    } catch (error) {
      status(error.name === "AbortError" ? "" : "Couldn't open sharing on this device. Save the video instead.");
    }
    return true;
  }

  // The share sheet button only appears where the device can share a video file.
  if (navigator.canShare && navigator.canShare({ files: [new File([""], "probe.mp4", { type: "video/mp4" })] })) {
    q("share").hidden = false;
  }
  q("share").addEventListener("click", openShareSheet);
  q("copy").addEventListener("click", async () => {
    await navigator.clipboard.writeText(captionText());
    status("Caption copied.");
  });
  root.querySelectorAll("[data-platform]").forEach((button) => button.addEventListener("click", async () => {
    const platform = PLATFORMS[Number(button.dataset.platform)];
    if (isPhone && (await openShareSheet())) return;
    // On a computer: save the video, copy the caption, and open the platform's upload page.
    q("save").click();
    try { await navigator.clipboard.writeText(captionText()); } catch (error) { /* copying is a nicety */ }
    window.open(platform.upload, "_blank", "noopener");
    status(`Video saved and caption copied. Drop the video into ${platform.name}'s upload page.`);
  }));
}
