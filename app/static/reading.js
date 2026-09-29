// The reading page: streams the interpretation, opens the card panels on
// the Celtic Cross, copies the link. Native EventSource, no libraries.

// ---- the interpretation, as it is written ----
// The server sends JSON-encoded text chunks; each render rebuilds the essay
// from the accumulated text, the same way main.py renders a stored one.
(function () {
  var essay = document.getElementById("essay");
  if (!essay || !essay.dataset.stream) return;

  var status = document.getElementById("reading-status");
  var closing = document.getElementById("closing");
  var text = "";
  var source = new EventSource(essay.dataset.stream);
  essay.setAttribute("aria-busy", "true");

  function esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function bold(s) {
    return esc(s).replace(/\*\*([\s\S]+?)\*\*/g, "<strong>$1</strong>");
  }
  function label(s) {
    return '<h2 class="card-label">' + esc(s.trim().replace(/\.$/, "")) + "</h2>";
  }
  function paragraph(p) {
    var lead = /^\*\*([\s\S]+?)\*\*\s*([\s\S]*)$/.exec(p);
    if (lead) return label(lead[1]) + (lead[2].trim() ? "<p>" + bold(lead[2].trim()) + "</p>" : "");
    // A label still arriving: show it as the heading it is about to be,
    // not as two literal asterisks.
    if (p.indexOf("**") === 0) return label(p.slice(2));
    return "<p>" + bold(p) + "</p>";
  }
  function render(note) {
    essay.innerHTML = text
      .split(/\n\n+/)
      .map(function (p) { return p.trim(); })
      .filter(Boolean)
      .map(paragraph)
      .join("") + (note || "");
  }
  function say(key) {
    if (status && status.dataset[key]) status.textContent = status.dataset[key];
  }

  source.onmessage = function (e) {
    text += JSON.parse(e.data);
    render();
  };
  source.addEventListener("done", function () {
    source.close();
    essay.removeAttribute("aria-busy");
    say("done");
    if (closing) closing.hidden = false;
  });
  source.onerror = function () {
    // A reading cut short looked finished. Say that it is not.
    source.close();
    essay.removeAttribute("aria-busy");
    say("lost");
    render('<p class="pending">' +
      (text ? "The connection dropped before the reading was finished. "
            : "The connection to the reader was lost. ") +
      '<a href="">Reload the page</a> to have it read again.</p>');
  };
})();

// ---- card panels on the Celtic Cross ----
// Each card is a button that opens its panel. One open at a time; a second
// press, the close control, Escape, or a press anywhere else shuts it.
(function () {
  var triggers = document.querySelectorAll(".card-btn");
  if (!triggers.length) return;

  var hint = document.querySelector(".hint");
  if (hint) hint.hidden = false;   // only promise what the script can deliver
  var open = null;

  function panel(btn) {
    return document.getElementById(btn.getAttribute("aria-controls"));
  }
  function close(returnFocus) {
    if (!open) return;
    panel(open).hidden = true;
    open.setAttribute("aria-expanded", "false");
    if (returnFocus) open.focus();
    open = null;
  }
  function show(btn) {
    close(false);
    panel(btn).hidden = false;
    btn.setAttribute("aria-expanded", "true");
    open = btn;
  }

  Array.prototype.forEach.call(triggers, function (btn) {
    btn.addEventListener("click", function () {
      if (open === btn) close(false); else show(btn);
    });
  });
  Array.prototype.forEach.call(document.querySelectorAll(".tip-close"), function (x) {
    x.addEventListener("click", function () { close(true); });
  });
  document.addEventListener("click", function (e) {
    if (open && !e.target.closest(".cc-card, .cc-center")) close(false);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") close(true);
  });
})();

// ---- copy the link ----
(function () {
  var btn = document.querySelector("[data-copy]");
  if (!btn || !navigator.clipboard) return;
  var idle = btn.textContent;
  btn.hidden = false;
  btn.addEventListener("click", function () {
    navigator.clipboard.writeText(location.href).then(function () {
      btn.textContent = btn.dataset.copied;
      setTimeout(function () { btn.textContent = idle; }, 2400);
    });
  });
})();
