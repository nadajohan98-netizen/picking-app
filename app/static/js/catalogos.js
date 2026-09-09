// Tablas de catálogo del admin (materiales, almacenes, puestos, usuarios).
// - "Editar" en una fila muestra el formulario de esa fila.
// - El buscador filtra las filas por texto.
(function () {
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-edit-row]");
    if (btn) {
      var tr = btn.closest("tr");
      tr.classList.toggle("editando");
      var inp = tr.querySelector(".row-edit input, .row-edit select");
      if (inp && tr.classList.contains("editando")) inp.focus();
      return;
    }
    if (e.target.closest("[data-cancel-row]")) {
      e.target.closest("tr").classList.remove("editando");
    }
  });

  var buscador = document.getElementById("cat-buscar");
  if (buscador) {
    buscador.addEventListener("input", function () {
      var q = buscador.value.trim().toLowerCase();
      document.querySelectorAll("tbody tr[data-buscar]").forEach(function (tr) {
        tr.hidden = q && tr.dataset.buscar.toLowerCase().indexOf(q) === -1;
      });
    });
  }
})();
