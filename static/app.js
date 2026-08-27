/* Settings persist in cookies the same way ncssmtime.com does, so the
   campus you pick sticks between pages and visits. */

function setCookie(name, value) {
  const oneYear = 60 * 60 * 24 * 365;
  document.cookie = `${name}=${value}; path=/; max-age=${oneYear}; SameSite=Lax`;
}

/* ---- Campus switch ----
   Swapping campus used to reload the page, which flashed. Instead: flip the
   body class so the two background layers crossfade immediately, then fetch
   the same URL (the server reads the new cookie) and swap just <main> in.
   Nothing blocks on the network except the item list. */

let swapSeq = 0;
let inflight = null;

async function switchCampus(toMorganton) {
  // The visual half is instant and never skipped, even mid-flight -- flipping
  // a switch that then does nothing is worse than a slow swap.
  setCookie("campus", toMorganton ? "morganton" : "durham");
  document.body.classList.toggle("morganton", toMorganton);
  syncCampusToggles(toMorganton);

  const main = document.querySelector("main");
  if (!main) return;

  // Latest toggle wins: abandon any request still running for an older one.
  const seq = ++swapSeq;
  if (inflight) inflight.abort();
  const controller = new AbortController();
  inflight = controller;

  main.classList.add("swapping");
  try {
    const resp = await fetch(window.location.href, {
      headers: { "X-Requested-With": "fetch" },
      signal: controller.signal,
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const html = await resp.text();
    if (seq !== swapSeq) return; // superseded while we were parsing

    const fresh = new DOMParser()
      .parseFromString(html, "text/html")
      .querySelector("main");
    if (fresh) main.innerHTML = fresh.innerHTML;
    syncCampusToggles(toMorganton);
  } catch (err) {
    if (err.name === "AbortError") return; // superseded, not a failure
    // Never leave the page showing one campus's items under another's name.
    window.location.reload();
    return;
  } finally {
    if (seq === swapSeq) {
      main.classList.remove("swapping");
      inflight = null;
    }
  }
}

function syncCampusToggles(checked) {
  document.querySelectorAll(".campus-toggle").forEach((t) => {
    t.checked = checked;
  });
}

/* Delegated, so switches that arrive with swapped-in markup still work. */
document.addEventListener("change", (e) => {
  if (e.target.matches(".campus-toggle")) {
    switchCampus(e.target.checked);
  }
});

/* ---- Submit states ----
   Also delegated: the results page has its own search form, and that markup
   is replaced whenever the campus changes. */

document.addEventListener("submit", (e) => {
  const form = e.target;

  if (form.id === "post-form") {
    const btn = form.querySelector("#post-btn");
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span>Reading the photo…';
    }
  }

  if (form.classList.contains("search-form")) {
    const btn = form.querySelector('button[type="submit"]');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span>Searching';
    }
  }
});

/* ---- Post form: drag-and-drop and local preview ---- */

function bindDropZone() {
  const drop = document.getElementById("drop");
  const fileInput = document.getElementById("photo");
  if (!drop || !fileInput || drop.dataset.bound) return;
  drop.dataset.bound = "1";

  const preview = document.getElementById("preview");
  const dropText = document.getElementById("drop-text");
  const dropSub = document.getElementById("drop-sub");

  function showFile(file) {
    if (!file || !file.type.startsWith("image/")) return;
    preview.src = URL.createObjectURL(file);
    preview.hidden = false;
    dropText.textContent = file.name;
    dropSub.textContent = "Click to pick a different photo";
  }

  fileInput.addEventListener("change", () => showFile(fileInput.files[0]));

  ["dragenter", "dragover"].forEach((evt) =>
    drop.addEventListener(evt, (e) => {
      e.preventDefault();
      drop.classList.add("over");
    })
  );

  ["dragleave", "drop"].forEach((evt) =>
    drop.addEventListener(evt, (e) => {
      e.preventDefault();
      drop.classList.remove("over");
    })
  );

  drop.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files[0];
    if (file) {
      // DataTransfer is the only way to programmatically set input.files.
      const dt = new DataTransfer();
      dt.items.add(file);
      fileInput.files = dt.files;
      showFile(file);
    }
  });
}

bindDropZone();
