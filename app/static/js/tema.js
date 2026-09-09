// Tema claro / oscuro / automático.
// El valor guardado ("light" | "dark" | ausente = automático) ya se aplicó en el
// <head> para no parpadear. Aquí solo conectamos el selector.
(function () {
  var sel = document.getElementById("theme-sel");
  if (!sel) return;

  var guardado = null;
  try { guardado = localStorage.getItem("tema"); } catch (e) {}
  sel.value = guardado === "light" || guardado === "dark" ? guardado : "auto";

  sel.addEventListener("change", function () {
    var v = sel.value;
    try {
      if (v === "auto") localStorage.removeItem("tema");
      else localStorage.setItem("tema", v);
    } catch (e) {}
    if (v === "auto") document.documentElement.setAttribute("data-theme", "");
    else document.documentElement.setAttribute("data-theme", v);
  });
})();
