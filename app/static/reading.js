// Streams the interpretation into the essay. Native EventSource — no libraries.
// The server sends JSON-encoded text chunks; we re-render bold + paragraphs
// from the accumulated text (the prompt permits only that much markdown).
(function () {
  var essay = document.getElementById("essay");
  if (!essay || !essay.dataset.stream) return;

  var text = "";
  var source = new EventSource(essay.dataset.stream);

  function esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function render() {
    essay.innerHTML = text
      .split(/\n\n+/)
      .filter(function (p) { return p.trim(); })
      .map(function (p) {
        return "<p>" + esc(p.trim()).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>") + "</p>";
      })
      .join("");
  }

  source.onmessage = function (e) {
    text += JSON.parse(e.data);
    render();
  };
  source.addEventListener("done", function () { source.close(); });
  source.onerror = function () {
    // Connection dropped mid-read: keep whatever arrived, offer a reload.
    source.close();
    if (!text) {
      essay.innerHTML =
        '<p class="pending">The connection to the reader was lost — ' +
        '<a href="">reload the page</a> to try again.</p>';
    }
  };
})();

// A card's tooltip opens on focus (click or tap) and closes when focus
// leaves. Escape is the other thing people try, so honour it.
document.addEventListener("keydown", function (e) {
  if (e.key === "Escape" && document.activeElement) document.activeElement.blur();
});
