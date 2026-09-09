// Selección de puesto: WebSocket que marca en vivo cuáles están ocupados.
(function () {
  var grid = document.getElementById("puestos-grid");
  if (!grid) return;

  var proto = location.protocol === "https:" ? "wss:" : "ws:";
  var ws = new WebSocket(proto + "//" + location.host + "/ws/puestos");

  ws.onmessage = function (ev) {
    var data = JSON.parse(ev.data);
    if (data.type === "estado") pintar(data.ocupados);
  };
  ws.onclose = function () { setTimeout(function () { location.reload(); }, 3000); };

  function pintar(ocupados) {
    grid.querySelectorAll(".puesto").forEach(function (card) {
      var id = card.dataset.puesto;
      var dueno = ocupados[id];
      var txt = card.querySelector(".pst-txt");
      var who = card.querySelector(".pw");
      card.classList.remove("ocupado", "ocupado-mio");
      card.removeEventListener("click", bloquear);
      if (!dueno) { txt.textContent = "Libre"; who.innerHTML = "&nbsp;"; return; }
      var mio = String(dueno) === String(window.USUARIO_ID);
      if (mio) {
        card.classList.add("ocupado-mio");
        txt.textContent = "Lo tenés abierto"; who.innerHTML = "&nbsp;";
      } else {
        card.classList.add("ocupado");
        txt.textContent = "Ocupado"; who.textContent = "otro operario";
        card.addEventListener("click", bloquear);
      }
    });
  }
  function bloquear(e) { e.preventDefault(); alert("Ese puesto está ocupado por otra persona."); }
})();
