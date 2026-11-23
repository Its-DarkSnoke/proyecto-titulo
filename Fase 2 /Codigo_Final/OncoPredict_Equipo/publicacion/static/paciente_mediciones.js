(() => {
  const page = document.querySelector('.ficha-paciente');
  if (!page) return;

  const resultsSection = page.querySelector('.tarjeta-resultados');
  if (!resultsSection) return;

  const breastEvaluations = [...resultsSection.querySelectorAll('.evaluacion[data-tipo-evaluacion="mama"]')];
  const measurements = new Map();

  breastEvaluations.forEach((evaluation) => {
    const date = evaluation.querySelector('time')?.textContent.trim() || '';
    const details = evaluation.querySelector('.mediciones-paciente');
    if (!details) return;

    details.querySelectorAll(':scope > div').forEach((field) => {
      const label = field.querySelector('dt')?.textContent.trim();
      const rawValue = field.querySelector('dd')?.textContent.trim().replace(',', '.');
      const value = Number(rawValue);
      if (!label || !Number.isFinite(value)) return;
      if (!measurements.has(label)) measurements.set(label, []);
      measurements.get(label).push({ date, value });
    });
  });

  const available = [...measurements.entries()]
    .map(([label, values]) => [label, values.reverse()])
    .filter(([, values]) => values.length > 1);
  if (!available.length || !breastEvaluations.length) return;

  const chart = document.createElement('section');
  chart.className = 'historial-mediciones';
  chart.setAttribute('aria-labelledby', 'titulo-historial-mediciones');

  const heading = document.createElement('h4');
  heading.id = 'titulo-historial-mediciones';
  heading.textContent = 'Cómo han cambiado tus mediciones';
  const note = document.createElement('p');
  note.textContent = 'Compara tus valores publicados por fecha. El gráfico muestra mediciones registradas; no interpreta su significado clínico.';
  const tabs = document.createElement('div');
  tabs.className = 'historial-metricas';
  tabs.setAttribute('role', 'group');
  tabs.setAttribute('aria-label', 'Selecciona una medición para comparar');
  const graph = document.createElement('div');
  graph.className = 'historial-grafico';
  graph.setAttribute('aria-live', 'polite');
  chart.append(heading, note, tabs, graph);

  const svgElement = (name, attributes = {}) => {
    const element = document.createElementNS('http://www.w3.org/2000/svg', name);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
    return element;
  };

  const draw = (label, values) => {
    const width = 760;
    const height = 220;
    const padding = { top: 28, right: 28, bottom: 42, left: 28 };
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;
    const min = Math.min(...values.map((item) => item.value));
    const max = Math.max(...values.map((item) => item.value));
    const range = max - min || Math.max(Math.abs(max) * .12, 1);
    const points = values.map((item, index) => ({
      ...item,
      x: padding.left + (values.length === 1 ? plotWidth / 2 : (index / (values.length - 1)) * plotWidth),
      y: padding.top + plotHeight - ((item.value - min) / range) * plotHeight,
    }));

    const svg = svgElement('svg', { viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': `Historial de ${label} en ${values.length} evaluaciones` });
    for (let row = 0; row < 3; row += 1) {
      const y = padding.top + (plotHeight / 2) * row;
      svg.append(svgElement('line', { x1: padding.left, y1: y, x2: width - padding.right, y2: y, class: 'rejilla' }));
    }
    const line = svgElement('polyline', { points: points.map(({ x, y }) => `${x},${y}`).join(' '), class: 'linea' });
    svg.append(line);

    points.forEach((point) => {
      svg.append(svgElement('circle', { cx: point.x, cy: point.y, r: 6, class: 'punto' }));
      const valueText = svgElement('text', { x: point.x, y: Math.max(17, point.y - 13), 'text-anchor': 'middle', class: 'valor-punto' });
      valueText.textContent = String(point.value);
      svg.append(valueText);
      const dateText = svgElement('text', { x: point.x, y: height - 15, 'text-anchor': 'middle' });
      dateText.textContent = point.date.split(' ')[0] || `Evaluación ${points.indexOf(point) + 1}`;
      svg.append(dateText);
    });

    graph.replaceChildren(svg);
  };

  available.forEach(([label, values], index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = label;
    button.setAttribute('aria-pressed', index === 0 ? 'true' : 'false');
    button.addEventListener('click', () => {
      tabs.querySelectorAll('button').forEach((tab) => tab.setAttribute('aria-pressed', String(tab === button)));
      draw(label, values);
    });
    tabs.append(button);
  });

  resultsSection.insertBefore(chart, breastEvaluations[0]);
  draw(...available[0]);
})();
