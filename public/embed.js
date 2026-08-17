// Puts the Fristen of one Vorhaben on a page with one script tag:
//   <script src="https://wannometer.de/embed.js" data-vorhaben="umzug"></script>
// Everything it does, the iframe snippet on /einbetten/ does too. This only
// saves the height guessing.
(function () {
  var tag = document.currentScript;
  if (!tag) return;
  var origin = new URL(tag.src, location.href).origin;
  var slug = tag.dataset.vorhaben || "umzug";
  var url = new URL(origin + "/embed/" + slug + "/");
  // Same names the iframe url takes, passed through from the script tag.
  ["accent", "ink", "muted", "line", "paper", "font"].forEach(function (key) {
    if (tag.dataset[key]) url.searchParams.set(key, tag.dataset[key]);
  });

  var frame = document.createElement("iframe");
  frame.src = url.href;
  frame.title = "Fristen von Wann-O-Meter";
  frame.loading = "lazy";
  frame.style.cssText = "width:100%;border:0;height:600px";
  tag.parentNode.insertBefore(frame, tag);

  addEventListener("message", function (event) {
    if (event.origin !== origin) return;
    if (event.source !== frame.contentWindow) return;
    var data = event.data;
    if (data && data.type === "wannometer:height" && data.height > 0) {
      frame.style.height = data.height + 16 + "px";
    }
  });
})();
