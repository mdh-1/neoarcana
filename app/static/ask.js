// The question form. Kept in a file, not inline: the site's
// Content-Security-Policy allows scripts from its own origin only.
(function () {
  var form = document.querySelector("form.ask");
  if (!form) return;
  var field = form.querySelector("textarea");
  var button = form.querySelector("button[type=submit]");
  var idle = button.textContent;

  // A textarea takes Enter as a new line. The question is one line, and
  // Enter has always sent it, so keep that; Shift+Enter still breaks.
  field.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      form.requestSubmit(button);
    }
  });

  // Drawing takes a moment (the shuffle is a network call) and nothing on
  // the page used to change, so a second tap drew a second reading and
  // spent two of the hour's ten.
  form.addEventListener("submit", function () {
    button.disabled = true;
    button.textContent = button.dataset.busy;
  });

  // Coming back with the browser's Back button restores the page as it was
  // left, disabled button and all.
  window.addEventListener("pageshow", function () {
    button.disabled = false;
    button.textContent = idle;
  });
})();
