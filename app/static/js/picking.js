// Cuadrícula de picking.
//
//  1. Pide la config (para leer el peso del código de barras) y el catálogo de lotes.
//  2. Abre el WebSocket y pide el candado del puesto.
//  3. Monta la grilla (Tabulator) al estilo hoja de cálculo.
//  4. Piqueo por casillas: clic en una casilla -> escribís el peso -> Enter ->
//     se ve al instante y se guarda en segundo plano (PUT). Si el servidor lo
//     rechaza (te pasaste), se revierte y avisa.

(function () {
  "use strict";

  var PUESTO_ID = window.PUESTO_ID;
  var aviso = document.getElementById("aviso");
  var loadingMask = document.getElementById("loading-mask");
  var CFG = { bc_longitud: 13, bc_prefijo: "29", bc_peso_inicio: 8,
              bc_peso_digitos: 5, bc_peso_divisor: 1000, tolerancia_pct: 2 };

  var tabla = null;
  var lineas = {};           // id -> datos de la línea (fuente de verdad en el cliente)
  var lineaActiva = null;    // id de la línea donde está trabajando el operario

  // ---------- utilidades ----------
  var kg = function (n) { return Number(n).toFixed(3); };
  var suma = function (a) { return a.reduce(function (x, y) { return x + y; }, 0); };

  function mostrarAviso(txt, err) {
    aviso.textContent = txt;
    aviso.className = "aviso" + (err ? " error" : "");
    aviso.hidden = false;
    clearTimeout(mostrarAviso._t);
    mostrarAviso._t = setTimeout(function () { aviso.hidden = true; }, 4500);
  }
  function limpiarAviso() { aviso.hidden = true; }

  var kpiTimer = null;
  function pedirKpis() {
    clearTimeout(kpiTimer);
    kpiTimer = setTimeout(cargarKpis, 250);
  }

  // ---------- carga inicial ----------
  Promise.all([
    fetch("/api/config").then(function (r) { return r.json(); }).catch(function () { return null; }),
    fetch("/api/lotes?all=1").then(function (r) { return r.json(); }).catch(function () { return []; })
  ]).then(function (res) {
    if (res[0]) CFG = res[0];
    window.LOTES = res[1] || [];
  });

  // ---------- WebSocket / candado ----------
  var proto = location.protocol === "https:" ? "wss:" : "ws:";
  var ws = new WebSocket(proto + "//" + location.host + "/ws/puestos");
  ws.onopen = function () { ws.send(JSON.stringify({ accion: "abrir", puesto_id: PUESTO_ID })); };
  ws.onmessage = function (ev) {
    var d = JSON.parse(ev.data);
    if (d.type === "abierto" && d.puesto_id === PUESTO_ID) montarTabla();
    else if (d.type === "rechazado") { alert("Este puesto ya está ocupado por otra persona."); location.href = "/puestos"; }
  };
  ws.onclose = function () { mostrarAviso("Se perdió la conexión con el servidor. Recargá la página.", true); };

  document.getElementById("btn-cerrar").addEventListener("click", function () {
    try { ws.send(JSON.stringify({ accion: "cerrar" })); } catch (e) {}
    location.href = "/puestos";
  });
  window.addEventListener("beforeunload", function () {
    try { ws.send(JSON.stringify({ accion: "cerrar" })); } catch (e) {}
  });

  // ---------- estado de una línea ----------
  function estadoLinea(d) {
    var tope = d.cantidad_pedida * (1 + (CFG.tolerancia_pct || 2) / 100);
    if (d.cantidad_despachada > tope + 1e-9) return "excedida";
    if (d.cantidad_despachada >= d.cantidad_pedida && d.cantidad_pedida > 0) return "completa";
    return "";
  }

  function recalcular(d) {
    d.cantidad_despachada = Math.round(suma(d.pesos) * 1000) / 1000;
    d.canastillas = d.pesos.length;
    d.diferencia = Math.round((d.cantidad_pedida - d.cantidad_despachada) * 1000) / 1000;
  }

  // ---------- pintar una tira de piqueo (rápido, un solo elemento) ----------
  function pintarTira(wrap, d) {
    wrap.innerHTML = "";
    d.pesos.forEach(function (p, i) {
      var b = document.createElement("span");
      b.className = "pk"; b.dataset.idx = i; b.textContent = kg(p);
      wrap.appendChild(b);
    });
    var next = document.createElement("span");
    next.className = "pk pk-next"; next.dataset.idx = d.pesos.length; next.textContent = "+";
    wrap.appendChild(next);

    var falta = d.cantidad_pedida - d.cantidad_despachada;
    var rem = document.createElement("span");
    if (falta > 0.001) { rem.className = "pk-rem"; rem.textContent = "faltan " + kg(falta); }
    else if (falta < -0.001) { rem.className = "pk-rem over"; rem.textContent = "+" + kg(-falta); }
    else { rem.className = "pk-rem done"; rem.textContent = "listo"; }
    wrap.appendChild(rem);
  }

  function tiraDe(lineId) {
    var row = tabla.getRow(lineId);
    return row ? row.getElement().querySelector(".piqueo") : null;
  }

  function refrescarResumen(lineId) {
    var row = tabla.getRow(lineId);
    if (!row) return;
    var d = lineas[lineId];
    row.getCell("cantidad_despachada").setValue(d.cantidad_despachada);
    row.getCell("canastillas").setValue(d.canastillas);
    row.getCell("diferencia").setValue(d.diferencia);
    var el = row.getElement();
    el.classList.remove("fila-completa", "fila-excedida");
    var est = estadoLinea(d);
    if (est) el.classList.add("fila-" + est);
  }

  // ---------- marcar línea activa ----------
  function activar(lineId) {
    if (lineaActiva === lineId) return;
    lineaActiva = lineId;
    document.querySelectorAll("#grid .tabulator-row.fila-activa")
      .forEach(function (r) { r.classList.remove("fila-activa"); });
    var row = tabla.getRow(lineId);
    if (row) row.getElement().classList.add("fila-activa");
  }

  // ---------- editar una casilla ----------
  function editarCasilla(lineId, idx) {
    var d = lineas[lineId];
    if (!d || !d.es_kg) return;
    idx = Math.min(idx, d.pesos.length);           // solo la siguiente vacía o una existente
    activar(lineId);

    var wrap = tiraDe(lineId);
    if (!wrap || wrap.querySelector(".pk-input")) return;
    var celda = wrap.querySelector('.pk[data-idx="' + idx + '"]');
    if (!celda) return;

    var inp = document.createElement("input");
    inp.className = "pk-input"; inp.inputMode = "decimal";
    inp.value = d.pesos[idx] != null ? d.pesos[idx] : "";
    celda.replaceWith(inp);
    inp.focus(); inp.select();
    inp.scrollIntoView({ inline: "nearest", block: "nearest" });

    var listo = false;
    function cerrar(accion) {          // accion: "next" | "stay" | "cancel" | "prev"
      if (listo) return;
      listo = true;
      if (accion === "cancel") { pintarTira(wrap, d); return; }

      var txt = inp.value.replace(",", ".").trim();
      var pesos = d.pesos.slice();
      if (txt === "") {
        if (idx < pesos.length) pesos.splice(idx, 1);
      } else {
        var v = parseFloat(txt);
        if (isNaN(v) || v <= 0) { pintarTira(wrap, d); return; }
        pesos[idx] = Math.round(v * 1000) / 1000;
      }
      guardarPesos(lineId, pesos, accion);
    }

    inp.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); cerrar("next"); }
      else if (e.key === "Escape") { e.preventDefault(); cerrar("cancel"); document.getElementById("bc").focus(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); cerrar("stay"); saltarFila(lineId, -1, idx); }
      else if (e.key === "ArrowDown") { e.preventDefault(); cerrar("stay"); saltarFila(lineId, +1, idx); }
      else if (e.key === "ArrowLeft" && inp.selectionStart === 0 && idx > 0) { e.preventDefault(); cerrar("prev"); }
      else if (e.key === "Backspace" && inp.value === "" && idx > 0) { e.preventDefault(); cerrar("prev"); }
    });
    inp.addEventListener("blur", function () { cerrar("stay"); });
  }

  function saltarFila(lineId, dir, idx) {
    var ids = tabla.getRows("active").map(function (r) { return r.getData().id; });
    var pos = ids.indexOf(lineId);
    for (var i = pos + dir; i >= 0 && i < ids.length; i += dir) {
      if (lineas[ids[i]] && lineas[ids[i]].es_kg) { editarCasilla(ids[i], idx); return; }
    }
  }

  // ---------- guardar (optimista + PUT en segundo plano) ----------
  function guardarPesos(lineId, pesos, accion) {
    var d = lineas[lineId];
    var antes = d.pesos.slice();

    // 1) actualizá la vista al instante
    d.pesos = pesos;
    recalcular(d);
    var wrap = tiraDe(lineId);
    if (wrap) pintarTira(wrap, d);
    refrescarResumen(lineId);
    pedirKpis();

    // 2) reabrí la casilla que toque
    if (accion === "next") setTimeout(function () { editarCasilla(lineId, d.pesos.length); }, 0);
    else if (accion === "prev") setTimeout(function () { editarCasilla(lineId, Math.max(0, pesos.length - 1)); }, 0);

    // 3) guardá en el servidor
    fetch("/api/lineas/" + lineId + "/pesos", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pesos: pesos })
    }).then(function (r) {
      return r.json().then(function (b) { return { ok: r.ok, b: b }; });
    }).then(function (res) {
      if (!res.ok) {
        d.pesos = antes; recalcular(d);
        var w = tiraDe(lineId); if (w) pintarTira(w, d);
        refrescarResumen(lineId); pedirKpis();
        mostrarAviso(res.b.detail || "No se pudo guardar.", true);
        return;
      }
      limpiarAviso();
      // reconciliá por si el servidor redondeó distinto (sin pisar una casilla abierta)
      var cambio = JSON.stringify(d.pesos) !== JSON.stringify(res.b.pesos);
      d.pesos = res.b.pesos; recalcular(d);
      d.lote = res.b.lote; d.fecha_vencimiento = res.b.fecha_vencimiento;
      d.vencimiento_estado = res.b.vencimiento_estado; d.editado_por = res.b.editado_por;
      var w2 = tiraDe(lineId);
      if (cambio && w2 && !w2.querySelector(".pk-input")) pintarTira(w2, d);
      refrescarResumen(lineId);
    }).catch(function () {
      d.pesos = antes; recalcular(d);
      var w = tiraDe(lineId); if (w) pintarTira(w, d);
      refrescarResumen(lineId);
      mostrarAviso("Error de red al guardar.", true);
    });
  }

  // ---------- Tabulator ----------
  function montarTabla() {
    if (tabla) return;
    tabla = new Tabulator("#grid", {
      index: "id",
      layout: "fitData",
      height: "100%",
      ajaxURL: "/api/puestos/" + PUESTO_ID + "/lineas",
      placeholder: "Este puesto no tiene líneas de picking para hoy.",
      columnDefaults: { headerHozAlign: "left", resizable: true },
      rowFormatter: function (row) {
        var d = row.getData();
        lineas[d.id] = lineas[d.id] || d;
        var el = row.getElement();
        el.classList.remove("fila-completa", "fila-excedida");
        var est = estadoLinea(lineas[d.id]);
        if (est) el.classList.add("fila-" + est);
        if (d.id === lineaActiva) el.classList.add("fila-activa");
      },
      columns: [
        { title: "Almacén", field: "almacen_codigo", frozen: true, width: 88, headerFilter: "input" },
        {
          title: "Material", frozen: true, width: 240, headerFilter: "input", field: "material_descripcion",
          formatter: function (cell) {
            var d = cell.getRow().getData();
            return '<div>' + d.material_descripcion + '</div><div class="cell-mat-code mono">' + d.material_codigo + '</div>';
          }
        },
        { title: "Un", field: "unidad", width: 46, hozAlign: "center",
          formatter: function (c) { return '<span class="cell-unit">' + c.getValue() + '</span>'; } },
        { title: "Pedido", field: "cantidad_pedida", width: 78, hozAlign: "right",
          formatter: function (c) { var d = c.getRow().getData(); return '<span class="num-mono">' + (d.es_kg ? kg(c.getValue()) : c.getValue()) + '</span>'; } },
        {
          title: "Desp.", field: "cantidad_despachada", width: 84, hozAlign: "right",
          editable: function (c) { return c.getRow().getData().es_kg === false; },
          editor: "number", editorParams: { min: 0, selectContents: true },
          formatter: function (c) {
            var d = c.getRow().getData();
            return '<b class="num-mono">' + (d.es_kg ? kg(c.getValue()) : c.getValue()) + '</b>';
          }
        },
        {
          title: "Lote", field: "lote", width: 110,
          editor: "list",
          editorParams: { valuesLookup: function () { return window.LOTES || []; }, autocomplete: true, freetext: false, listOnEmpty: true, clearable: true, placeholderEmpty: "Sin coincidencias" },
          formatter: function (c) { var v = c.getValue(); return '<span class="lote-txt ' + (v ? '' : 'vacio') + '">' + (v || '—') + '</span>'; }
        },
        {
          title: "Vence", field: "fecha_vencimiento", width: 118, hozAlign: "center",
          editor: "date", editorParams: { min: window.HOY_ISO },
          formatter: function (c) {
            var d = c.getRow().getData();
            return '<span class="venc-txt ' + d.vencimiento_estado + '">' + (c.getValue() || '—') + '</span>';
          }
        },
        { title: "#", field: "canastillas", width: 42, hozAlign: "right",
          formatter: function (c) { return '<span class="num-mono">' + c.getValue() + '</span>'; } },
        {
          title: "Dif", field: "diferencia", width: 78, hozAlign: "right",
          formatter: function (c) {
            var d = c.getRow().getData();
            var v = c.getValue();
            var cls = v < 0 ? "dif-neg" : v === 0 ? "dif-zero" : "";
            var txt = v < 0 ? "+" + (d.es_kg ? kg(-v) : -v) : (v === 0 ? "0" : (d.es_kg ? kg(v) : v));
            return '<span class="num-mono ' + cls + '">' + txt + '</span>';
          }
        },
        {
          title: "Piqueo (casillas)", field: "pesos", width: 380, resizable: true, headerSort: false,
          formatter: function (cell) {
            var d = cell.getRow().getData();
            lineas[d.id] = lineas[d.id] || d;
            if (!d.es_kg) { return '<span class="muted small">se cuenta por unidad</span>'; }
            var wrap = document.createElement("div");
            wrap.className = "piqueo";
            wrap.dataset.linea = d.id;
            pintarTira(wrap, lineas[d.id]);
            return wrap;
          }
        }
      ]
    });

    tabla.on("dataLoaded", function (data) {
      data.forEach(function (d) { lineas[d.id] = d; });
      if (loadingMask) loadingMask.classList.add("hidden");
    });
    tabla.on("tableBuilt", cargarKpis);
    tabla.on("renderComplete", function () {
      // reaplica la clase de línea activa después de re-renders por scroll
      if (lineaActiva) {
        var row = tabla.getRow(lineaActiva);
        if (row) row.getElement().classList.add("fila-activa");
      }
    });
    tabla.on("cellEdited", function (cell) {
      var campo = cell.getField();
      if (campo === "cantidad_despachada" || campo === "lote" || campo === "fecha_vencimiento") {
        guardarCampo(cell, campo);
      }
    });

    // clics: casilla de piqueo, o cualquier celda para marcar la línea activa
    document.getElementById("grid").addEventListener("click", function (e) {
      var pk = e.target.closest(".pk");
      if (pk) {
        var wrap = pk.closest(".piqueo");
        editarCasilla(+wrap.dataset.linea, +pk.dataset.idx);
        return;
      }
      var rowEl = e.target.closest(".tabulator-row");
      if (rowEl) {
        var r = tabla.getRows().find(function (x) { return x.getElement() === rowEl; });
        if (r) activar(r.getData().id);
      }
    });
  }

  function guardarCampo(cell, campo) {
    var row = cell.getRow();
    var anterior = cell.getOldValue();
    fetch("/api/lineas/" + row.getData().id, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ campo: campo, valor: cell.getValue() })
    }).then(function (r) {
      return r.json().then(function (b) { return { ok: r.ok, b: b }; });
    }).then(function (res) {
      if (!res.ok) {
        cell.setValue(anterior, true);
        mostrarAviso(res.b.detail || "No se pudo guardar.", true);
        return;
      }
      limpiarAviso();
      lineas[res.b.id] = res.b;
      row.update(res.b);
      pedirKpis();
    }).catch(function () {
      cell.setValue(anterior, true);
      mostrarAviso("Error de red al guardar.", true);
    });
  }

  // ---------- KPIs ----------
  function cargarKpis() {
    fetch("/api/puestos/" + PUESTO_ID + "/kpis").then(function (r) { return r.json(); }).then(function (k) {
      var cells = [
        ["Total pedido", k.total_pedido, ""],
        ["Total despachado", k.total_despachado, ""],
        ["% Cumplimiento", k.pct_cumplimiento + " %", k.cumple_objetivo ? "good" : "bad"],
        ["% Faltante", k.pct_faltante + " %", ""],
        ["Total unidades", k.total_unidades, ""],
        ["Total pendiente", k.total_pendiente, k.total_pendiente < 0 ? "bad" : ""]
      ];
      document.getElementById("kpibar").innerHTML = cells.map(function (c) {
        return '<div class="kpi ' + c[2] + '"><div class="kl">' + c[0] + '</div><div class="kv">' + c[1] + '</div></div>';
      }).join("");
    });
  }

  // ---------- barra: peso del código de barras ----------
  var bc = document.getElementById("bc"), bcOut = document.getElementById("bc-out");
  function pesoDeCodigo(digits) {
    var start = (CFG.bc_peso_inicio || 1) - 1;
    var w = digits.slice(start, start + (CFG.bc_peso_digitos || 5));
    if (w.length < (CFG.bc_peso_digitos || 5)) return null;
    return parseInt(w, 10) / (CFG.bc_peso_divisor || 1000);
  }
  bc.addEventListener("input", function () {
    var p = pesoDeCodigo(bc.value.replace(/\D/g, ""));
    bcOut.textContent = p != null ? kg(p) + " kg" : "—";
  });
  bc.addEventListener("keydown", function (e) {
    if (e.key !== "Enter") return;
    var d = bc.value.replace(/\D/g, "");
    if (CFG.bc_longitud && d.length !== CFG.bc_longitud) { mostrarAviso("El código debe tener " + CFG.bc_longitud + " dígitos.", true); return; }
    if (CFG.bc_prefijo && d.slice(0, CFG.bc_prefijo.length) !== CFG.bc_prefijo) { mostrarAviso("Prefijo no reconocido (se espera " + CFG.bc_prefijo + ").", true); return; }
    var p = pesoDeCodigo(d);
    if (p == null || p <= 0) { mostrarAviso("No pude leer el peso del código.", true); return; }
    if (!lineaActiva || !lineas[lineaActiva] || !lineas[lineaActiva].es_kg) {
      mostrarAviso("Elegí primero una casilla o fila de un material en KG.", true); return;
    }
    var pesos = lineas[lineaActiva].pesos.slice();
    pesos.push(Math.round(p * 1000) / 1000);
    guardarPesos(lineaActiva, pesos, "none");
    bc.value = ""; bcOut.textContent = "—";
    bc.focus();   // queda listo para el siguiente escaneo
  });

  // ---------- buscador + filtros ----------
  var buscar = document.getElementById("buscar");
  var filtroAlm = null, soloPend = false;
  function aplicarFiltros() {
    if (!tabla) return;
    var q = buscar.value.trim().toLowerCase();
    tabla.setFilter(function (data) {
      if (q) {
        var t = (data.almacen_codigo + " " + data.material_codigo + " " + data.material_descripcion + " " + (data.lote || "")).toLowerCase();
        if (t.indexOf(q) === -1) return false;
      }
      if (filtroAlm && data.almacen_codigo !== filtroAlm) return false;
      if (soloPend && data.cantidad_despachada >= data.cantidad_pedida) return false;
      return true;
    });
  }
  buscar.addEventListener("input", aplicarFiltros);
  document.querySelectorAll(".fchip").forEach(function (b) {
    b.addEventListener("click", function () {
      if (b.dataset.alm) {
        filtroAlm = filtroAlm === b.dataset.alm ? null : b.dataset.alm;
        document.querySelectorAll(".fchip[data-alm]").forEach(function (x) { x.classList.toggle("on", x.dataset.alm === filtroAlm); });
      } else if (b.dataset.pend) {
        soloPend = !soloPend;
        b.classList.toggle("on", soloPend);
      }
      aplicarFiltros();
    });
  });
})();
