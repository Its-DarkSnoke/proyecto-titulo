"use strict";

const get = (id) => document.getElementById(id);
const dataset = JSON.parse(get("analysis-data").textContent);
const count = new Intl.NumberFormat("es-CL");
const decimal = new Intl.NumberFormat("es-CL", { maximumFractionDigits: 2 });
const percent = new Intl.NumberFormat("es-CL", {
  style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1
});
const share = (numerator, denominator) => denominator ? percent.format(numerator / denominator) : "—";

function element(tag, className, text) {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function empty(root, details) {
  root.replaceChildren(element("p", "empty", details));
}

function choices(id, onSelect) {
  const options = [...get(id).querySelectorAll("button")];
  options.forEach((option) => option.addEventListener("click", () => onSelect(option.dataset.value)));
  return (value) => {
    options.forEach((option) => option.setAttribute("aria-pressed", String(option.dataset.value === value)));
  };
}

function indicators(...values) {
  ["total", "kpi-two", "kpi-three", "kpi-four"].forEach((id, index) => {
    get(id).textContent = values[index];
  });
}

function scope(message, active) {
  get("scope").textContent = message;
  get("scope").classList.toggle("is-active", active);
  get("reset").disabled = !active;
}

function bar({ label, value, fraction, color, detail, selected, onClick }) {
  const row = element(onClick ? "button" : "div", "bar-row");
  const track = element("span", "bar-track");
  const fill = element("span", "bar-fill");
  track.setAttribute("aria-hidden", "true");
  fill.style.setProperty("--bar-width", `${Math.max(0, Math.min(1, fraction)) * 100}%`);
  if (color) fill.style.setProperty("--bar-color", color);
  track.append(fill);
  row.append(element("span", "bar-name", label), track, element("span", "bar-value", value));
  if (detail) row.title = detail;
  if (onClick) {
    row.type = "button";
    row.setAttribute("aria-pressed", String(selected));
    row.setAttribute("aria-label", detail ? `${label}, ${value}, ${detail}` : `${label}, ${value}`);
    row.addEventListener("click", onClick);
  }
  return row;
}

function lungDashboard() {
  const data = dataset.map(([country, gender, smoking, age, diagnosis, stage, size]) => ({
    country, gender, smoking, age, positive: diagnosis === "Sí", stage, size
  }));
  const labels = {
    country: "País", age: "Edad", gender: "Género", smoking: "Tabaquismo"
  };
  const dimensions = Object.keys(labels);
  const display = (key, value) => {
    if (key === "smoking") return value === "Sí" ? "Fumador" : "No fumador";
    return key === "age" ? value.replace("-", "–") : value;
  };
  const values = Object.fromEntries(dimensions.map((key) => [
    key, [...new Set(data.map((row) => row[key]))].sort((a, b) => a.localeCompare(b, "es-CL"))
  ]));
  const filters = Object.fromEntries(dimensions.map((key) => [key, get(key)]));
  const stages = ["Etapa 1", "Etapa 2", "Etapa 3", "Etapa 4"];
  const stageColors = ["#52a89e", "#267f88", "#456891", "#624e84"];
  let dimension = "age";
  const selectDimension = choices("dimension", (value) => {
    dimension = value;
    render();
  });

  for (const key of dimensions) {
    for (const value of values[key]) filters[key].add(new Option(display(key, value), value));
    filters[key].addEventListener("change", render);
  }
  get("reset").addEventListener("click", () => {
    for (const input of Object.values(filters)) input.value = "";
    render();
    filters.country.focus();
  });

  function renderGroups(visible, selected, focusGroup) {
    const root = get("group-bars");
    const groups = new Map();
    for (const row of visible) {
      const key = row[dimension];
      const group = groups.get(key) || { total: 0, positive: 0 };
      group.total += row.size;
      if (row.positive) group.positive += row.size;
      groups.set(key, group);
    }
    const rate = (group) => group.positive / group.total;
    let order = values[dimension].filter((key) => groups.has(key));
    const countryRanking = dimension === "country" && order.length > 8;
    if (dimension === "country") {
      order = order.sort((a, b) => rate(groups.get(b)) - rate(groups.get(a)));
      if (countryRanking) order = order.slice(0, 8);
      if (selected && groups.has(selected) && !order.includes(selected)) order.push(selected);
    }
    const scale = Math.max(.05, ...order.map((key) => rate(groups.get(key))));
    get("group-note").textContent = [
      countryRanking ? "Se muestran los 8 países con mayor proporción y el país seleccionado, si corresponde." : "",
      selected ? `La comparación mantiene todos los grupos de ${labels[dimension].toLowerCase()} disponibles bajo los otros filtros.` : ""
    ].filter(Boolean).join(" ");
    if (!order.length) {
      empty(root, "No hay registros para esta combinación de filtros.");
      return;
    }
    root.replaceChildren();
    for (const key of order) {
      const group = groups.get(key);
      const node = bar({
        label: display(dimension, key),
        value: share(group.positive, group.total),
        fraction: rate(group) / scale,
        detail: `${count.format(group.positive)} positivos de ${count.format(group.total)} registros`,
        selected: selected === key,
        onClick: () => {
          filters[dimension].value = selected === key ? "" : key;
          render(key);
        }
      });
      root.append(node);
      if (focusGroup === key) node.focus();
    }
    if (typeof focusGroup === "string" && !order.includes(focusGroup)) filters[dimension].focus();
  }

  function renderStages(groups, positive) {
    const root = get("stage-bars");
    const note = get("stage-note");
    if (!positive) {
      empty(root, "No hay diagnósticos positivos en la selección.");
      note.textContent = "";
      return;
    }
    root.replaceChildren(...stages.map((stage, index) => {
      const amount = groups.get(stage) || 0;
      return bar({ label: stage, value: share(amount, positive), fraction: amount / positive,
        color: stageColors[index], detail: `${count.format(amount)} casos` });
    }));
    note.textContent = `${count.format(positive)} diagnósticos positivos en la selección.`;
  }

  function render(focusGroup) {
    selectDimension(dimension);
    const active = dimensions.filter((key) => filters[key].value);
    for (const key of dimensions) filters[key].classList.toggle("is-active", active.includes(key));
    const summary = active.map((key) => `${labels[key]} · ${display(key, filters[key].value)}`);
    scope(summary.join("  /  ") || "Mostrando todos los registros.", Boolean(active.length));
    const matches = (row, except) => active.every((key) => key === except || row[key] === filters[key].value);
    let total = 0;
    let positive = 0;
    const countries = new Set();
    const stageCount = new Map();
    for (const row of data.filter((row) => matches(row))) {
      total += row.size;
      countries.add(row.country);
      if (row.positive) {
        positive += row.size;
        stageCount.set(row.stage, (stageCount.get(row.stage) || 0) + row.size);
      }
    }
    indicators(count.format(total), count.format(positive), share(positive, total), count.format(countries.size));
    renderGroups(data.filter((row) => matches(row, dimension)), filters[dimension].value, focusGroup);
    renderStages(stageCount, positive);
  }

  render();
}

function svg(tag, attributes, label) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
  if (label !== undefined) node.textContent = label;
  return node;
}

function breastDashboard() {
  const data = dataset.map(([diagnosis, radius, texture, perimeter, area]) => ({
    diagnosis, radius, texture, perimeter, area
  }));
  const groups = ["Benigno", "Maligno"];
  const metrics = { radius: "Radio medio", texture: "Textura media", perimeter: "Perímetro medio", area: "Área media" };
  const styles = { Benigno: "benign", Maligno: "malignant" };
  const bounds = {
    radius: { min: 5, max: 30, step: 5 },
    texture: { min: 5, max: 40, step: 7 },
    perimeter: { min: 40, max: 200, step: 40 },
    area: { min: 0, max: 2600, step: 650 }
  };
  let diagnosis = "";
  let dimension = "texture";
  let plotWidth = 0;
  let visibleRows = [];
  const selectDiagnosis = choices("diagnosis", (value) => {
    diagnosis = value;
    render();
  });
  const selectDimension = choices("dimension", (value) => {
    dimension = value;
    render();
  });
  get("reset").addEventListener("click", () => {
    diagnosis = "";
    render();
    get("diagnosis").querySelector("[aria-pressed='true']").focus();
  });

  function plot(rows) {
    const root = get("scatter");
    const detail = get("point-detail");
    plotWidth = Math.max(250, root.parentElement.clientWidth);
    root.setAttribute("viewBox", `0 0 ${plotWidth} 330`);
    detail.hidden = true;
    root.replaceChildren(
      svg("title", { id: "scatter-title" }, `${metrics.radius} y ${metrics[dimension].toLowerCase()}`),
      svg("desc", { id: "scatter-desc" },
        `${count.format(rows.length)} muestras. Los puntos verdes son benignos y los puntos rosa son malignos.`)
    );
    const left = 59, right = plotWidth - 19, top = 17, bottom = 272;
    const x = (value) => left + (value - bounds.radius.min) / (bounds.radius.max - bounds.radius.min) * (right - left);
    const range = bounds[dimension];
    const y = (value) => bottom - (value - range.min) / (range.max - range.min) * (bottom - top);
    for (let value = bounds.radius.min; value <= bounds.radius.max; value += bounds.radius.step) {
      root.append(
        svg("line", { x1: x(value), x2: x(value), y1: top, y2: bottom, class: "plot-grid" }),
        svg("text", { x: x(value), y: bottom + 20, "text-anchor": "middle", class: "plot-tick" }, count.format(value))
      );
    }
    for (let value = range.min; value <= range.max; value += range.step) {
      root.append(
        svg("line", { x1: left, x2: right, y1: y(value), y2: y(value), class: "plot-grid" }),
        svg("text", { x: left - 8, y: y(value) + 4, "text-anchor": "end", class: "plot-tick" }, count.format(value))
      );
    }
    root.append(
      svg("path", { d: `M ${left} ${top} V ${bottom} H ${right}`, class: "plot-axis", fill: "none" }),
      svg("text", { x: (left + right) / 2, y: 319, "text-anchor": "middle", class: "plot-label" }, metrics.radius),
      svg("text", { transform: "translate(15 145) rotate(-90)", "text-anchor": "middle", class: "plot-label" }, metrics[dimension])
    );
    root.append(...rows.map((row) => {
      const point = svg("circle", {
        cx: x(row.radius), cy: y(row[dimension]), r: 4.2, class: `plot-point ${styles[row.diagnosis]}`
      });
      point.addEventListener("pointerenter", () => {
        detail.textContent = `${row.diagnosis} · radio ${decimal.format(row.radius)} · ${metrics[dimension].toLowerCase()} ${decimal.format(row[dimension])}`;
        detail.hidden = false;
      });
      point.addEventListener("pointerleave", () => { detail.hidden = true; });
      return point;
    }));
  }

  function averages(rows) {
    const root = get("morphology");
    root.replaceChildren();
    const selected = Object.fromEntries(groups.map((group) => [group, rows.filter((row) => row.diagnosis === group)]));
    for (const [key, label] of Object.entries(metrics)) {
      const metric = element("div", "metric");
      metric.append(element("h3", "", label));
      for (const group of groups) {
        const subset = selected[group];
        if (!subset.length) continue;
        const mean = subset.reduce((sum, row) => sum + row[key], 0) / subset.length;
        metric.append(bar({ label: group, value: decimal.format(mean), fraction: mean / bounds[key].max,
          color: `var(--${styles[group]})`, detail: `Promedio de ${count.format(subset.length)} muestras` }));
      }
      root.append(metric);
    }
  }

  function render() {
    selectDiagnosis(diagnosis);
    selectDimension(dimension);
    const rows = diagnosis ? data.filter((row) => row.diagnosis === diagnosis) : data;
    const malignant = rows.filter((row) => row.diagnosis === "Maligno").length;
    scope(diagnosis ? `Diagnóstico · ${diagnosis}` : "Mostrando todas las muestras.", Boolean(diagnosis));
    indicators(count.format(rows.length), count.format(rows.length - malignant), count.format(malignant), share(malignant, rows.length));
    visibleRows = rows;
    plot(visibleRows);
    averages(rows);
  }

  render();
  new ResizeObserver(() => {
    if (Math.max(250, get("scatter").parentElement.clientWidth) !== plotWidth) plot(visibleRows);
  }).observe(get("scatter").parentElement);
}

if (document.body.dataset.specialty === "mama") breastDashboard();
else lungDashboard();
