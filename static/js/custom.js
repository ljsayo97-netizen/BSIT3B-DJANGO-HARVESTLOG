/* Shared UI helpers for HarvestLog. */
document.addEventListener("DOMContentLoaded", function () {
  // Allow dashboard shortcuts to deep-link directly into create dialogs:
  // ?new=farm, ?new=crop, ?new=harvest, ?new=schedule, ?new=activity, or ?new=1.
  var params = new URLSearchParams(window.location.search);
  var requested = params.get("new");
  if (!requested) {
    return;
  }

  var selector = '[data-mode="create"][data-bs-toggle="modal"]';
  if (requested !== "1" && /^[a-z0-9_-]+$/i.test(requested)) {
    selector =
      '[data-mode="create"][data-bs-toggle="modal"][data-bs-target="#' +
      requested +
      'Modal"]';
  }

  var trigger = document.querySelector(selector);
  if (!trigger) {
    return;
  }

  // Clean the URL so refreshing or closing the dialog does not reopen it.
  params.delete("new");
  var query = params.toString();
  var cleanUrl = window.location.pathname + (query ? "?" + query : "");
  window.history.replaceState({}, document.title, cleanUrl + window.location.hash);

  trigger.click();
});
