// Panel de supervisor: pinta el resumen y lo refresca cada 15 s.
(function () {
  var tb = document.querySelector("#tabla-puestos tbody");
  var alertas = document.getElementById("alertas");

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function pintar(r) {
    tb.innerHTML = r.puestos.map(function (p) {
      var k = p.kpis;
      var cls = k.total_pedido <= 0 ? "i" : k.cumple_objetivo ? "g" : "w";
      var txt = k.total_pedido <= 0 ? "sin abrir" : k.pct_cumplimiento + " %";
      var alerta = (!k.cumple_objetivo && k.total_pedido > 0) ? " fila-alerta" : "";
      return "<tr class='fila-link" + alerta + "' onclick=\"location.href='/supervisor/puesto/" + p.id + "'\">" +
        "<td class='mono'>" + String(p.numero).padStart(2, "0") + "</td>" +
        "<td>" + (p.ocupado_por ? esc(p.ocupado_por) : "<span class='muted'>libre</span>") + "</td>" +
        "<td><div class='barcell'><div class='bt'><i style='width:" + Math.min(k.pct_cumplimiento, 100) + "%'></i></div>" +
          "<span class='pill " + cls + "'>" + txt + "</span></div></td>" +
        "<td class='r mono'>" + k.total_pedido + "</td>" +
        "<td class='r mono'>" + k.total_despachado + "</td>" +
        "<td class='r mono'>" + k.total_pendiente + "</td></tr>";
    }).join("");

    if (!r.alertas.length) {
      alertas.innerHTML = "<div class='empty-state'>Sin vencimientos próximos.</div>";
    } else {
      alertas.innerHTML = r.alertas.map(function (a) {
        return "<div class='arow " + a.estado + "'><span class='sv'></span>" +
          "<div class='m'><div>" + esc(a.material) + "</div>" +
          "<div class='s'>Puesto " + String(a.puesto).padStart(2, "0") + " · lote " + esc(a.lote || "—") + "</div></div>" +
          "<span class='tg'>" + (a.estado === "vencido" ? "vencido " : "vence ") + a.vence + "</span></div>";
      }).join("");
    }
  }

  function refrescar() {
    fetch("/api/supervisor/resumen").then(function (x) { return x.json(); }).then(pintar).catch(function () {});
  }

  if (window.RESUMEN_INICIAL) pintar(window.RESUMEN_INICIAL);
  setInterval(refrescar, 15000);
})();
