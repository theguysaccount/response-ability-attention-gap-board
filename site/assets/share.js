// Share buttons on cause pages: the native share sheet where the browser has one, otherwise copy the link.
const box = document.querySelector("[data-share]");
if (box) {
  const url = document.querySelector('link[rel="canonical"]').href;
  const status = document.createElement("span");
  status.className = "status";
  status.setAttribute("role", "status");
  box.appendChild(status);
  const native = box.querySelector("[data-share-native]");
  const count = (name) => { try { window.goatcounter && window.goatcounter.count({ path: name, title: name, event: true }); } catch (_) { /* optional */ } };
  if (navigator.share) {
    native.hidden = false;
    native.addEventListener("click", async () => {
      try { await navigator.share({ title: box.dataset.title, text: box.dataset.text, url }); count("share"); } catch (_) { /* dismissed */ }
    });
  }
  box.querySelector("[data-share-copy]").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(url); status.textContent = "Link copied."; count("share"); }
    catch (_) { status.textContent = url; }
  });
}
if (new URLSearchParams(location.search).has("selftest")) import("./selftest.js").then((m) => m.run("cause"));
