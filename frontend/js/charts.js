/* =============================================================================
   Módulo de Gráficos (Plotly.js) — Theme-Aware
   =============================================================================
   Funciones puras para renderizar cada gráfico del dashboard.
   Lee colores desde CSS variables para adaptarse al tema activo.
   ============================================================================= */


/**
 * Lee los colores del tema actual desde las CSS variables.
 */
function getThemeColors() {
    const style = getComputedStyle(document.documentElement);
    return {
        plotBg:  style.getPropertyValue('--color-plot-bg').trim(),
        grid:    style.getPropertyValue('--color-plot-grid').trim(),
        zero:    style.getPropertyValue('--color-plot-zero').trim(),
        font:    style.getPropertyValue('--color-plot-font').trim(),
        line:    style.getPropertyValue('--color-plot-line').trim(),
        accent:  style.getPropertyValue('--color-accent').trim(),
        // Theme-aware semantic colors (used in traces)
        alcance: style.getPropertyValue('--color-alcance').trim(),
        objetos: style.getPropertyValue('--color-sem-green').trim(),
    };
}


/**
 * Configuración base compartida por gráficos 2D.
 */
function getPlotlyLayoutBase() {
    const c = getThemeColors();
    return {
        paper_bgcolor: 'transparent',
        plot_bgcolor:  'transparent',
        font: { color: c.font, family: 'JetBrains Mono, monospace', size: 9 },
        showlegend: false
    };
}

const PLOTLY_CONFIG = { responsive: true, displayModeBar: false };

// Máximo de un array numérico ignorando null/undefined (sin spread: los arrays
// de trayectoria pueden ser grandes). Para fijar rangos Y estables en gráficos
// con leyenda interactiva: al ocultar una traza Plotly re-autoescala al máximo
// de las visibles y las alturas dejan de ser comparables.
function _maxNum(arr) {
    return (arr || []).reduce((m, v) => (v != null && v > m ? v : m), 0);
}

// Rango [0, max·1.1] para eje Y fijo (1 si todo es 0 para no colapsar el eje)
function _rangoYFijo(maxY) {
    return [0, maxY > 0 ? maxY * 1.1 : 1];
}

// Fixed chart colors (do not change with theme)
const CHART_COLORS = {
    alcance:    '#4facfe',
    transporte: '#ff9e00',
    cursor:     '#ff0055',
    score:      '#a78bfa',
    objetos:    '#00ff88',
};


// =============================================================================
// GRÁFICO 3D: Trayectoria cinemática
// =============================================================================

/**
 * Inicializa el gráfico 3D vacío con ejes fijos.
 */
function inicializarGrafico3D(containerId, datos, fantasma = null) {
    const pad = 0.05;
    const c   = getThemeColors();

    // Si hay trayectoria fantasma, los ejes deben encuadrar ambas sesiones
    const xs = fantasma?.x?.length ? datos.x.concat(fantasma.x) : datos.x;
    const ys = fantasma?.y?.length ? datos.y.concat(fantasma.y) : datos.y;
    const zs = fantasma?.z?.length ? datos.z.concat(fantasma.z) : datos.z;

    const layout = {
        paper_bgcolor: 'transparent',
        plot_bgcolor:  'transparent',
        margin: { l: 0, r: 0, b: 0, t: 0 },
        font:   { color: c.font, family: 'JetBrains Mono, monospace', size: 10 },
        scene: {
            xaxis: { title: 'X', gridcolor: c.grid, zerolinecolor: c.zero, range: [Math.min(...xs) - pad, Math.max(...xs) + pad] },
            yaxis: { title: 'Y', gridcolor: c.grid, zerolinecolor: c.zero, range: [Math.min(...ys) - pad, Math.max(...ys) + pad] },
            zaxis: { title: 'Z', gridcolor: c.grid, zerolinecolor: c.zero, range: [Math.min(...zs) - pad, Math.max(...zs) + pad] },
            camera: { eye: { x: 1.5, y: 1.5, z: 1.5 } },
            bgcolor: 'transparent'
        },
        showlegend: false
    };

    Plotly.newPlot(containerId, [], layout, { responsive: true });
    return layout;
}


/**
 * Actualiza el gráfico 3D con los puntos hasta el frame actual.
 * Preserva el ángulo de cámara y añade marcadores de posición de objetos.
 */
function actualizarGrafico3D(containerId, datos, rangoInicio, currentIndex, layoutFijo, agarreSeleccionado, fantasma = null) {
    const c = getThemeColors();

    const x_h = datos.x.slice(rangoInicio, currentIndex + 1);
    const y_h = datos.y.slice(rangoInicio, currentIndex + 1);
    const z_h = datos.z.slice(rangoInicio, currentIndex + 1);
    const g_h = datos.grasps.slice(rangoInicio, currentIndex + 1);

    const x_alcance    = [], y_alcance    = [], z_alcance    = [];
    const x_transporte = [], y_transporte = [], z_transporte = [];

    g_h.forEach((agarre, i) => {
        if (agarre) {
            x_transporte.push(x_h[i]); y_transporte.push(y_h[i]); z_transporte.push(z_h[i]);
        } else {
            x_alcance.push(x_h[i]);    y_alcance.push(y_h[i]);    z_alcance.push(z_h[i]);
        }
    });

    const traces = [
        {
            x: x_h, y: y_h, z: z_h,
            mode: 'lines',
            line: { color: c.line, width: 1.5 },
            type: 'scatter3d',
            hoverinfo: 'none'
        },
        {
            x: x_alcance, y: y_alcance, z: z_alcance,
            mode: 'markers',
            marker: { size: 3, color: c.alcance, opacity: 0.8 },
            type: 'scatter3d',
            name: 'Alcance'
        },
        {
            x: x_transporte, y: y_transporte, z: z_transporte,
            mode: 'markers',
            marker: { size: 5, color: CHART_COLORS.transporte, symbol: 'diamond', opacity: 0.9 },
            type: 'scatter3d',
            name: 'Transporte'
        },
        {
            x: [datos.x[currentIndex]],
            y: [datos.y[currentIndex]],
            z: [datos.z[currentIndex]],
            mode: 'markers',
            marker: { size: 10, color: CHART_COLORS.cursor, opacity: 0.9 },
            type: 'scatter3d',
            name: 'Cursor'
        }
    ];

    // Marcadores de posición de agarre (verde, cruz)
    // Filtrar: solo mostrar objetos cuyo agarre cae dentro del rango visible
    if (datos.posiciones_objetos && datos.posiciones_objetos.length > 0) {
        let objs = [];
        let labels = [];
        const segs = datos.grasp_segments || [];
        if (agarreSeleccionado != null) {
            const idx = agarreSeleccionado - 1;
            if (idx >= 0 && idx < datos.posiciones_objetos.length) {
                objs = [datos.posiciones_objetos[idx]];
                labels = [`Agarre #${agarreSeleccionado}`];
            }
        } else {
            for (let i = 0; i < datos.posiciones_objetos.length; i++) {
                const seg = segs[i];
                if (seg && seg.frame_inicio_reach >= rangoInicio && seg.frame_fin <= currentIndex) {
                    objs.push(datos.posiciones_objetos[i]);
                    labels.push(`Agarre #${i + 1}`);
                } else if (!seg) {
                    objs.push(datos.posiciones_objetos[i]);
                    labels.push(`Agarre #${i + 1}`);
                }
            }
        }
        if (objs.length > 0) {
            traces.push({
                x: objs.map(p => p.x),
                y: objs.map(p => p.y),
                z: objs.map(p => p.z),
                mode: 'markers',
                marker: { size: 9, color: c.objetos, symbol: 'cross', opacity: 1.0 },
                type: 'scatter3d',
                name: 'Pos. objeto',
                text: labels,
                hovertemplate: '%{text}<extra>Pos. objeto</extra>'
            });
        }
    }

    // Trayectoria fantasma: otra sesión de la misma mano, superpuesta y
    // semitransparente. Su cursor avanza en tiempo PROPORCIONAL (ambas
    // trayectorias normalizadas 0→1), no en tiempo absoluto.
    if (fantasma?.x?.length) {
        // Color sólido + punteado: scatter3d NO soporta alpha en line.color
        // (el rgba se funde a blanco en WebGL); la opacidad va en marker.opacity
        traces.push({
            x: fantasma.x, y: fantasma.y, z: fantasma.z,
            mode: 'lines',
            line: { color: '#a78bfa', width: 3, dash: 'dot' },
            type: 'scatter3d',
            name: 'Fantasma',
            hoverinfo: 'none'
        });
        const total = Math.max(1, datos.x.length - 1);
        const gi = Math.min(fantasma.x.length - 1,
                            Math.round(currentIndex / total * (fantasma.x.length - 1)));
        traces.push({
            x: [fantasma.x[gi]], y: [fantasma.y[gi]], z: [fantasma.z[gi]],
            mode: 'markers',
            marker: { size: 9, color: '#a78bfa', symbol: 'circle-open', opacity: 0.9, line: { color: '#a78bfa', width: 3 } },
            type: 'scatter3d',
            name: 'Cursor fantasma',
            hoverinfo: 'none'
        });
    }

    const el = document.getElementById(containerId);
    Plotly.react(containerId, traces, el.layout || layoutFijo);
}


// =============================================================================
// GRÁFICO 2D: Perfil de velocidad
// =============================================================================

function renderizarVelocidad(containerId, timestamps, velocidades, grasps) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const c = getThemeColors();

    const trace = {
        x: timestamps,
        y: velocidades,
        type: 'scatter',
        mode: 'lines',
        line: { color: c.alcance, width: 1.5 },
        fill: 'tozeroy',
        fillcolor: 'rgba(79, 172, 254, 0.1)',
        hovertemplate: 'T: %{x:.1f}s<br>V: %{y:.3f} m/s<extra></extra>'
    };

    const layout = {
        ...getPlotlyLayoutBase(),
        margin: { l: 40, r: 10, b: 30, t: 10 },
        xaxis:  { gridcolor: c.grid, zerolinecolor: c.zero },
        yaxis:  { title: 'm/s', gridcolor: c.grid, zerolinecolor: c.zero },
        shapes: _calcularZonasTransporte(timestamps, grasps)
    };

    Plotly.newPlot(containerId, [trace], layout, PLOTLY_CONFIG);
}


// =============================================================================
// GRÁFICO 2D: Scores por frame
// =============================================================================

function renderizarScores(containerId, scores, anomalias) {
    const el = document.getElementById(containerId);
    if (!el || !scores || !scores.length) return;
    const c = getThemeColors();

    const trace = {
        x: scores.map((_, i) => i),
        y: scores,
        type: 'scatter',
        mode: 'lines+markers',
        line:   { color: CHART_COLORS.score, width: 2 },
        marker: { size: 3, color: CHART_COLORS.score },
        fill: 'tozeroy',
        fillcolor: 'rgba(167, 139, 250, 0.1)',
        hovertemplate: 'Frame %{x}<br>Score: %{y}<extra></extra>'
    };

    const shapes = [];
    const annotations = [];
    for (const a of (anomalias || [])) {
        shapes.push({
            type: 'rect', xref: 'x', yref: 'paper',
            x0: a.frame_inicio, x1: a.frame_fin, y0: 0, y1: 1,
            fillcolor: 'rgba(255,80,80,0.12)',
            line: { color: 'rgba(255,80,80,0.5)', width: 1 },
        });
        annotations.push({
            x: (a.frame_inicio + a.frame_fin) / 2,
            y: 1, yref: 'paper', yanchor: 'top',
            text: `A${a.num}`,
            showarrow: false,
            font: { color: '#ff5050', size: 10, family: 'monospace' },
            bgcolor: 'rgba(0,0,0,0.25)', borderpad: 2,
        });
    }

    const layout = {
        ...getPlotlyLayoutBase(),
        margin: { l: 40, r: 10, b: 30, t: 10 },
        xaxis:  { title: 'Frame', gridcolor: c.grid, zerolinecolor: c.zero },
        yaxis:  { title: 'Score', gridcolor: c.grid, zerolinecolor: c.zero },
        shapes, annotations,
    };

    Plotly.newPlot(containerId, [trace], layout, PLOTLY_CONFIG);
}


// =============================================================================
// GRÁFICO 2D: Fruits — comparación de manos (barras agrupadas)
// =============================================================================

const HAND_COLORS = { RIGHT: '#4facfe', LEFT: '#ff9e00', BOTH: '#00ff88', NONE: '#94a3b8' };
const HAND_LABELS = { RIGHT: 'Derecha', LEFT: 'Izquierda', BOTH: 'Ambas', NONE: 'Mano única' };
// Orden canónico de manos. NONE = registro sin lateralidad declarada (juego a una mano).
const HAND_KEYS = ['RIGHT', 'LEFT', 'BOTH', 'NONE'];

function renderizarFruitsComparacion(containerId, datos) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const c = getThemeColors();
    const hands = datos.hands || {};
    const keys  = HAND_KEYS.filter(h => hands[h]);
    if (!keys.length) {
        // limpiar: los contenedores se comparten entre juegos Fruits y sin esto
        // quedaría visible el gráfico del juego anterior
        el.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;opacity:0.4;font-size:13px;font-family:monospace">Sin datos por mano para esta partida</div>';
        return;
    }

    const labels = keys.map(h => HAND_LABELS[h]);

    // offsetgroup: sin él, Plotly NO agrupa barras de ejes Y distintos (y/y2)
    // y las dibuja superpuestas ocupando todo el ancho
    const traceFPM = {
        name: 'Frutas/min',
        x: labels,
        y: keys.map(h => hands[h].metricas.frutas_por_minuto),
        type: 'bar',
        marker: { color: CHART_COLORS.alcance, opacity: 0.9 },
        yaxis: 'y',
        offsetgroup: 'fpm',
        hovertemplate: '%{x}<br><b>%{y}</b> frutas/min<extra></extra>',
    };

    const traceTMedio = {
        name: 'T. medio (s)',
        x: labels,
        y: keys.map(h => hands[h].metricas.tiempo_medio_s),
        type: 'bar',
        marker: { color: '#a78bfa', opacity: 0.85 },
        yaxis: 'y2',
        offsetgroup: 'tmedio',
        hovertemplate: '%{x}<br><b>%{y}</b> s/fruta<extra></extra>',
    };

    const layout = {
        ...getPlotlyLayoutBase(),
        barmode: 'group',
        showlegend: true,
        legend: { orientation: 'h', y: -0.25, font: { size: 10 } },
        margin: { l: 45, r: 50, b: 50, t: 10 },
        xaxis:  { gridcolor: c.grid },
        yaxis:  { title: 'Frutas/min', gridcolor: c.grid, zerolinecolor: c.zero, range: _rangoYFijo(_maxNum(traceFPM.y)) },
        yaxis2: { title: 'T. medio (s)', overlaying: 'y', side: 'right', gridcolor: 'transparent', zerolinecolor: 'transparent', range: _rangoYFijo(_maxNum(traceTMedio.y)) },
    };

    Plotly.newPlot(containerId, [traceFPM, traceTMedio], layout, PLOTLY_CONFIG);
}


// =============================================================================
// GRÁFICO 2D: Fruits — tiempos entre frutas por mano (barras agrupadas)
// =============================================================================

function _regresionLineal(ys) {
    const n = ys.length;
    const xs = ys.map((_, i) => i + 1);
    const sumX  = xs.reduce((a, b) => a + b, 0);
    const sumY  = ys.reduce((a, b) => a + b, 0);
    const sumXY = xs.reduce((a, _, i) => a + xs[i] * ys[i], 0);
    const sumXX = xs.reduce((a, _, i) => a + xs[i] * xs[i], 0);
    const denom = n * sumXX - sumX * sumX;
    const m = denom !== 0 ? (n * sumXY - sumX * sumY) / denom : 0;
    const b = (sumY - m * sumX) / n;
    return { m, b, xs };
}

function renderizarFruitsTimes(containerId, datos) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const c     = getThemeColors();
    const hands = datos.hands || {};
    const keys  = HAND_KEYS.filter(h => hands[h]?.times_between?.length);
    if (!keys.length) {
        el.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;opacity:0.4;font-size:13px;font-family:monospace">Sin tiempos registrados para esta partida</div>';
        return;
    }

    const maxTimes = Math.max(...keys.map(h => hands[h].times_between.length));
    if (maxTimes < 2) {
        el.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;opacity:0.4;font-size:13px;font-family:monospace">Datos insuficientes para mostrar tendencia (≥2 frutas por mano)</div>';
        return;
    }
    el.innerHTML = '';

    const traces = [];
    for (const h of keys) {
        const times = hands[h].times_between;
        const xs = times.map((_, i) => i + 1);

        traces.push({
            name: HAND_LABELS[h],
            x: xs,
            y: times,
            type: 'scatter',
            mode: 'lines+markers',
            line:   { color: HAND_COLORS[h], width: 2 },
            marker: { size: 7, color: HAND_COLORS[h] },
            legendgroup: h,
            hovertemplate: `${HAND_LABELS[h]} · Fruta %{x}<br><b>%{y:.3f} s</b><extra></extra>`,
        });

        if (times.length > 1) {
            const { m, b } = _regresionLineal(times);
            traces.push({
                name: `Tendencia ${HAND_LABELS[h]}`,
                x: [xs[0], xs[xs.length - 1]],
                y: [m * xs[0] + b, m * xs[xs.length - 1] + b],
                type: 'scatter',
                mode: 'lines',
                line: { color: HAND_COLORS[h], width: 2, dash: 'dash' },
                legendgroup: h,
                showlegend: false,
                hoverinfo: 'skip',
            });
        }
    }

    const maxT = Math.max(...keys.map(h => _maxNum(hands[h].times_between)));
    const layout = {
        ...getPlotlyLayoutBase(),
        showlegend: true,
        legend: { orientation: 'h', y: -0.25, font: { size: 10 } },
        margin: { l: 45, r: 10, b: 50, t: 10 },
        xaxis: { title: 'Fruta nº', gridcolor: c.grid, zerolinecolor: c.zero, dtick: 1 },
        yaxis: { title: 'Segundos', gridcolor: c.grid, zerolinecolor: c.zero, range: _rangoYFijo(maxT) },
    };

    Plotly.newPlot(containerId, traces, layout, PLOTLY_CONFIG);
}


// =============================================================================
// GRÁFICO 2D: Fruits — asimetría bilateral (Derecha vs Izquierda)
// =============================================================================

function renderizarFruitsAsimetria(containerId, datos) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const hands = datos.hands || {};
    if (!hands.RIGHT || !hands.LEFT) {
        el.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;opacity:0.4;font-size:13px;font-family:monospace;text-align:center;padding:0 16px">Se necesitan datos de ambas manos (Derecha e Izquierda) para calcular la asimetría</div>';
        return;
    }
    el.innerHTML = '';

    const c = getThemeColors();

    // + siempre = derecha con ventaja, − = izquierda con ventaja
    // Para métricas donde mayor=mejor (frutas/min): R - L
    // Para métricas donde menor=mejor (tiempos):    L - R  (invertido)
    const config = [
        { m: 'frutas_por_minuto', label: 'Frutas/min',       inv: false },
        { m: 'tiempo_medio_s',    label: 'T. Medio (s)',     inv: true  },
        { m: 'std_dev_s',         label: 'Desv. Típica (s)', inv: true  },
    ];

    const etiquetas = config.map(cfg => cfg.label);
    const valores = config.map(({ m, inv }) => {
        const r = hands.RIGHT.metricas[m] || 0;
        const l = hands.LEFT.metricas[m]  || 0;
        const media = (r + l) / 2;
        if (media === 0) return 0;
        const diff = inv ? l - r : r - l;
        return parseFloat((diff / media * 100).toFixed(1));
    });

    const colores = valores.map(v =>
        Math.abs(v) < 10 ? '#00ff88' :
        v > 0            ? '#4facfe' :
                           '#ff9e00'
    );

    const severidad = v => Math.abs(v) < 10 ? 'Simétrico' : Math.abs(v) < 20 ? 'Leve' : Math.abs(v) < 40 ? 'Moderada' : 'Severa';
    const lado      = v => v > 0 ? '→ Derecha mejor' : v < 0 ? '← Izquierda mejor' : 'Simétrico';

    const trace = {
        x: etiquetas,
        y: valores,
        type: 'bar',
        marker: { color: colores, opacity: 0.85 },
        customdata: valores.map(v => [severidad(v), lado(v)]),
        hovertemplate: '%{x}<br>Asimetría: <b>%{y}%</b><br>%{customdata[0]} · %{customdata[1]}<extra></extra>',
    };

    const layout = {
        ...getPlotlyLayoutBase(),
        showlegend: false,
        margin: { l: 50, r: 30, b: 60, t: 10 },
        xaxis: { gridcolor: c.grid },
        yaxis: { title: '+ Derecha mejor  /  − Izquierda mejor', gridcolor: c.grid, zerolinecolor: c.zero },
        shapes: [
            { type: 'line', x0: -0.5, x1: 2.5, y0:   0, y1:   0, line: { color: c.zero,      width: 1.5 } },
            { type: 'line', x0: -0.5, x1: 2.5, y0:  10, y1:  10, line: { color: '#00ff8855', width: 1, dash: 'dot' } },
            { type: 'line', x0: -0.5, x1: 2.5, y0: -10, y1: -10, line: { color: '#00ff8855', width: 1, dash: 'dot' } },
            { type: 'line', x0: -0.5, x1: 2.5, y0:  40, y1:  40, line: { color: '#ff666655', width: 1, dash: 'dot' } },
            { type: 'line', x0: -0.5, x1: 2.5, y0: -40, y1: -40, line: { color: '#ff666655', width: 1, dash: 'dot' } },
        ],
        annotations: [
            { x: 2.45, y:  10, xanchor: 'right', yanchor: 'bottom', text: 'leve',   showarrow: false, font: { size: 9, color: '#00ff88' } },
            { x: 2.45, y:  40, xanchor: 'right', yanchor: 'bottom', text: 'severa', showarrow: false, font: { size: 9, color: '#ff6666' } },
            { x: 2.45, y: -10, xanchor: 'right', yanchor: 'top',    text: 'leve',   showarrow: false, font: { size: 9, color: '#00ff88' } },
            { x: 2.45, y: -40, xanchor: 'right', yanchor: 'top',    text: 'severa', showarrow: false, font: { size: 9, color: '#ff6666' } },
        ],
    };

    Plotly.newPlot(containerId, [trace], layout, PLOTLY_CONFIG);
}


// =============================================================================
// GRÁFICO 2D: Fruits — evolución temporal (líneas por mano)
// =============================================================================

function renderizarFruitsEvolucion(containerId, sessions, metrica) {
    const el = document.getElementById(containerId);
    if (!el || !sessions?.length) return;
    const c = getThemeColors();

    const metricaLabel = {
        frutas_por_minuto: 'Frutas/min',
        total_fruits:      'Total frutas',
        total_time:        'Tiempo total (s)',
    };

    const dates = sessions.map(s => s.date);

    const traces = HAND_KEYS.map(h => ({
        name: HAND_LABELS[h],
        x: dates,
        y: sessions.map(s => s[h]?.[metrica] ?? null),
        type: 'scatter',
        mode: 'lines+markers',
        connectgaps: false,
        line:   { color: HAND_COLORS[h], width: 2 },
        marker: { size: 7, color: HAND_COLORS[h] },
        hovertemplate: `${HAND_LABELS[h]} · %{x}<br><b>%{y}</b><extra></extra>`,
    })).filter(t => t.y.some(v => v != null));   // sin datos de esa mano → fuera de la leyenda

    const maxY = Math.max(...traces.map(t => _maxNum(t.y)), 0);
    const layout = {
        ...getPlotlyLayoutBase(),
        showlegend: true,
        legend: { orientation: 'h', y: -0.25, font: { size: 11 } },
        margin: { l: 50, r: 15, b: 70, t: 10 },
        xaxis: { gridcolor: c.grid, zerolinecolor: c.zero, tickangle: -30 },
        yaxis: { title: metricaLabel[metrica] || metrica, gridcolor: c.grid, zerolinecolor: c.zero, range: _rangoYFijo(maxY) },
    };

    Plotly.newPlot(containerId, traces, layout, PLOTLY_CONFIG);
}


// =============================================================================
// GRÁFICO 2D: Evolución temporal BBT (barras agrupadas L vs R)
// =============================================================================

function renderizarEvolucion(containerId, sessions, metrica) {
    const el = document.getElementById(containerId);
    if (!el || !sessions || !sessions.length) return;
    const c = getThemeColors();

    const metricaLabels = {
        completed:   'Completados',
        no_valid:    'No válidos',
        out_of_zone: 'Fuera de zona'
    };

    // Cuando dos sesiones caen el mismo día, añadir la hora para distinguir
    const dateCounts = {};
    sessions.forEach(s => { dateCounts[s.date] = (dateCounts[s.date] || 0) + 1; });
    const xLabels = sessions.map(s => {
        if (dateCounts[s.date] > 1) {
            const timePart = s.datetime.split(' ')[1].replace(/-/g, ':');
            return `${s.date}<br>${timePart}`;
        }
        return s.date;
    });

    const label = metricaLabels[metrica] || metrica;

    const traceLeft = {
        name: 'Izquierda',
        x: xLabels,
        y: sessions.map(s => s.left[metrica]),
        type: 'bar',
        marker: { color: c.alcance, opacity: 0.85 },
        hovertemplate: `Izq · %{x}<br>${label}: <b>%{y}</b><extra></extra>`
    };

    const traceRight = {
        name: 'Derecha',
        x: xLabels,
        y: sessions.map(s => s.right[metrica]),
        type: 'bar',
        marker: { color: c.objetos, opacity: 0.85 },
        hovertemplate: `Der · %{x}<br>${label}: <b>%{y}</b><extra></extra>`
    };

    const maxY = Math.max(_maxNum(traceLeft.y), _maxNum(traceRight.y));
    const layout = {
        ...getPlotlyLayoutBase(),
        showlegend: true,
        legend: { orientation: 'h', y: -0.25, font: { size: 11 } },
        barmode: 'group',
        margin: { l: 45, r: 15, b: 70, t: 15 },
        xaxis: { gridcolor: c.grid, zerolinecolor: c.zero, tickangle: -30 },
        yaxis: { title: label, gridcolor: c.grid, zerolinecolor: c.zero, range: _rangoYFijo(maxY) }
    };

    Plotly.newPlot(containerId, [traceLeft, traceRight], layout, PLOTLY_CONFIG);
}


/**
 * Re-renderiza todos los gráficos visibles. Se llama al cambiar de tema.
 */
function reRenderizarGraficos(dd, rangoInicio, currentIndex, _layoutFijo, anomalias, agarreSeleccionado, fantasma = null) {
    if (!dd) return;
    const nuevoLayout = inicializarGrafico3D('plot3d', dd, fantasma);
    actualizarGrafico3D('plot3d', dd, rangoInicio, currentIndex, nuevoLayout, agarreSeleccionado, fantasma);
    renderizarVelocidad('plotVelocidad', dd.timestamps, dd.velocidades, dd.grasps);
    renderizarScores('plotScores', dd.scores_por_frame, anomalias || []);
    return nuevoLayout;
}


// =============================================================================
// GRÁFICO 2D: Mini-barras Derecha vs Izquierda (comparación de manos BBT)
// =============================================================================

function _renderizarMiniGrafico(elementId, label, valDerc, valIzq) {
    const el = document.getElementById(elementId);
    if (!el) return;
    const c = getThemeColors();

    Plotly.react(el, [{
        type: 'bar',
        x: ['Derecha', 'Izquierda'],
        y: [valDerc, valIzq],
        marker: { color: ['rgba(56,189,100,0.85)', 'rgba(56,189,212,0.85)'] },
        text: [String(valDerc), String(valIzq)],
        textposition: 'outside',
        cliponaxis: false,   // sin esto la etiqueta del valor se corta contra el borde superior
    }], {
        ...getPlotlyLayoutBase(),
        font: { color: c.font, size: 12 },
        margin: { t: 30, r: 20, b: 40, l: 50 },
        title: { text: label, font: { size: 12, color: c.font } },
        yaxis: { gridcolor: c.grid, zerolinecolor: c.zero, rangemode: 'tozero' },
        xaxis: { tickfont: { size: 12 } },
    }, PLOTLY_CONFIG);
}


// =============================================================================
// GRÁFICO 2D: Fruits Race — mapa espacial de aciertos/fallos
// =============================================================================

/**
 * Scatter XY (frontal: X lateral, Y altura) de las posiciones de fruta en Race.
 * Verde = atrapada, rojo = fallada. Una pareja de trazas por mano.
 */
function renderizarRaceScatter(containerId, datos) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const c     = getThemeColors();
    const hands = datos.hands || {};
    const keys  = HAND_KEYS.filter(h => hands[h]?.action_states?.length);
    if (!keys.length) {
        el.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;opacity:0.4;font-size:13px;font-family:monospace">Sin posiciones registradas para esta partida</div>';
        return;
    }
    el.innerHTML = '';

    // Color = mano (misma paleta que el resto de la app: azul Derecha, naranja
    // Izquierda) · símbolo = resultado (● atrapada, ✕ fallada). Con símbolos por
    // mano y color por resultado las manos no se distinguían a simple vista.
    const traces = [];
    for (const h of keys) {
        const states  = hands[h].action_states;
        const correct = states.filter(s => s.is_correct);
        const failed  = states.filter(s => !s.is_correct);
        const base = {
            type: 'scatter',
            mode: 'markers',
            legendgroup: h,
        };
        if (correct.length) {
            traces.push({
                ...base,
                name: `${HAND_LABELS[h]} · atrapada ●`,
                x: correct.map(s => s.fruit_pos[0]),
                y: correct.map(s => s.fruit_pos[1]),
                marker: { size: 9, color: HAND_COLORS[h], symbol: 'circle', opacity: 0.85 },
                hovertemplate: `${HAND_LABELS[h]} · Atrapada<br>X: %{x:.2f} · Y: %{y:.2f}<extra></extra>`,
            });
        }
        if (failed.length) {
            traces.push({
                ...base,
                name: `${HAND_LABELS[h]} · fallada ✕`,
                x: failed.map(s => s.fruit_pos[0]),
                y: failed.map(s => s.fruit_pos[1]),
                // dismetría: por cuántos cm falló la mano en este evento
                customdata: failed.map(s => (Math.hypot(
                    s.hand_pos[0] - s.fruit_pos[0],
                    s.hand_pos[1] - s.fruit_pos[1],
                    s.hand_pos[2] - s.fruit_pos[2]) * 100).toFixed(1)),
                marker: { size: 11, color: HAND_COLORS[h], symbol: 'x', opacity: 0.9 },
                hovertemplate: `${HAND_LABELS[h]} · Fallada · error %{customdata} cm<br>X: %{x:.2f} · Y: %{y:.2f}<extra></extra>`,
            });
        }
    }

    const layout = {
        ...getPlotlyLayoutBase(),
        showlegend: true,
        legend: { orientation: 'h', y: -0.2, font: { size: 10 } },
        margin: { l: 50, r: 20, b: 60, t: 10 },
        xaxis: { title: 'X (lateral)', gridcolor: c.grid, zerolinecolor: c.zero },
        yaxis: { title: 'Y (altura)', gridcolor: c.grid, zerolinecolor: c.zero, scaleanchor: 'x' },
    };

    Plotly.newPlot(containerId, traces, layout, PLOTLY_CONFIG);
}


// =============================================================================
// GRÁFICO 2D: Superposición de perfiles de velocidad (dos datasets BBT)
// =============================================================================

function renderizarVelocidadComparacion(containerId, dd1, label1, dd2, label2) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const c = getThemeColors();

    // Normalizar timestamps a [0,1] para comparar duraciones distintas
    const norm = ts => {
        if (!ts || !ts.length) return [];
        const mn = Math.min(...ts), mx = Math.max(...ts);
        return mx > mn ? ts.map(t => (t - mn) / (mx - mn)) : ts.map(() => 0);
    };

    // Rango Y fijo al máximo de AMBAS manos (+10%): al ocultar una traza la otra
    // no debe "subir" por el re-autoescalado
    const maxVel = Math.max(_maxNum(dd1.velocidades), _maxNum(dd2.velocidades));

    Plotly.newPlot(containerId, [
        {
            type: 'scatter', mode: 'lines',
            x: norm(dd1.timestamps), y: dd1.velocidades,
            line: { color: '#38c464', width: 2 }, name: label1,
            hovertemplate: `${label1} %{y:.3f} m/s<extra></extra>`,
        },
        {
            type: 'scatter', mode: 'lines',
            x: norm(dd2.timestamps), y: dd2.velocidades,
            line: { color: '#38bcd4', width: 2, dash: 'dot' }, name: label2,
            hovertemplate: `${label2} %{y:.3f} m/s<extra></extra>`,
        },
    ], {
        ...getPlotlyLayoutBase(),
        showlegend: true,
        legend: { orientation: 'h', y: -0.25, font: { size: 10 } },
        margin: { l: 45, r: 10, b: 40, t: 10 },
        xaxis: { title: 'Tiempo norm.', gridcolor: c.grid, zerolinecolor: c.zero },
        yaxis: { title: 'm/s', gridcolor: c.grid, zerolinecolor: c.zero, range: _rangoYFijo(maxVel) },
    }, PLOTLY_CONFIG);
}


// =============================================================================
// UTILIDAD PRIVADA
// =============================================================================

function _calcularZonasTransporte(timestamps, grasps) {
    const shapes = [];
    let enTransporte = false;
    let inicio = 0;

    for (let i = 0; i < grasps.length; i++) {
        if (grasps[i] && !enTransporte) {
            enTransporte = true;
            inicio = timestamps[i];
        } else if (!grasps[i] && enTransporte) {
            enTransporte = false;
            shapes.push({
                type: 'rect', xref: 'x', yref: 'paper',
                x0: inicio, x1: timestamps[i],
                y0: 0, y1: 1,
                fillcolor: 'rgba(255, 158, 0, 0.08)',
                line: { width: 0 }
            });
        }
    }

    if (enTransporte) {
        shapes.push({
            type: 'rect', xref: 'x', yref: 'paper',
            x0: inicio, x1: timestamps[timestamps.length - 1],
            y0: 0, y1: 1,
            fillcolor: 'rgba(255, 158, 0, 0.08)',
            line: { width: 0 }
        });
    }

    return shapes;
}


// =============================================================================
// HEATMAP DE DENSIDAD DE TRAYECTORIA
// =============================================================================

// Ejes de un plano de proyección 2D. Ejes de los datos: X lateral · Y altura · Z profundidad.
const PLANOS_HEATMAP = {
    planta:  { ejeX: 'x', ejeY: 'z', titX: 'X (lateral)',     titY: 'Z (profundidad)', label: 'Planta (XZ)'  },
    frontal: { ejeX: 'x', ejeY: 'y', titX: 'X (lateral)',     titY: 'Y (altura)',      label: 'Frontal (XY)' },
    perfil:  { ejeX: 'z', ejeY: 'y', titX: 'Z (profundidad)', titY: 'Y (altura)',      label: 'Perfil (ZY)'  },
};

/**
 * Heatmap 2D de densidad de la trayectoria en el plano indicado (planta/frontal/perfil).
 * Cubre TODA la trayectoria (no un rango) para poder comparar cada agarre contra la nube
 * completa de movimiento. Superpone las posiciones de agarre; si hay un agarre seleccionado
 * lo resalta → detección visual de dispersión/anomalías espaciales.
 */
function renderizarHeatmap(containerId, datos, plano = 'planta', agarreSeleccionado = null) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const c = getThemeColors();
    const cfg = PLANOS_HEATMAP[plano] || PLANOS_HEATMAP.planta;
    const hx = datos[cfg.ejeX];
    const hy = datos[cfg.ejeY];

    // Densidad de la trayectoria completa
    const traceDensidad = {
        x: hx,
        y: hy,
        type: 'histogram2dcontour',
        colorscale: [[0,'rgba(79,172,254,0)'], [0.3,'rgba(79,172,254,0.3)'], [1,'rgba(79,172,254,0.95)']],
        showscale: false,
        contours: { showlines: false },
        ncontours: 14,
        name: 'Densidad',
        showlegend: false,
        hoverinfo: 'skip',
    };
    const traces = [traceDensidad];

    // Solo si hay un agarre seleccionado: dibujar SU trayectoria proyectada al plano
    // (reach en azul + transporte en naranja, como el 3D) sobre el heatmap.
    // Sin selección → solo el heatmap de densidad (limpio).
    const objs = datos.posiciones_objetos || [];
    const segs = datos.grasp_segments || [];
    const seg  = agarreSeleccionado != null ? segs.find(s => s.num === agarreSeleccionado) : null;
    if (seg) {
        const tramo = (i0, i1) => ({
            x: datos[cfg.ejeX].slice(i0, i1 + 1),
            y: datos[cfg.ejeY].slice(i0, i1 + 1),
        });
        // reach: inicio → punto de agarre · transporte: agarre → fin
        traces.push({
            ...tramo(seg.frame_inicio_reach, seg.frame_inicio_agarre),
            mode: 'lines', type: 'scatter',
            // verde en vez del azul del 3D: el heatmap de densidad ya es azul (alcance
            // azul sobre densidad azul no se distinguía)
            line: { color: '#22c55e', width: 2.5 },
            name: `Agarre #${agarreSeleccionado}`,
            hovertemplate: `Alcance<extra></extra>`,
        });
        traces.push({
            ...tramo(seg.frame_inicio_agarre, seg.frame_fin),
            mode: 'lines', type: 'scatter',
            line: { color: CHART_COLORS.transporte, width: 3 },
            name: 'transporte', showlegend: false,
            hovertemplate: `Transporte<extra></extra>`,
        });
    }
    // Marcador del punto de agarre (inicio de transporte)
    const selIdx = agarreSeleccionado != null ? agarreSeleccionado - 1 : -1;
    if (selIdx >= 0 && selIdx < objs.length) {
        const p = objs[selIdx];
        traces.push({
            x: [p[cfg.ejeX]], y: [p[cfg.ejeY]],
            mode: 'markers',
            type: 'scatter',
            marker: { size: 13, color: CHART_COLORS.cursor, symbol: 'cross', opacity: 1, line: { color: '#ffffff', width: 1.5 } },
            name: 'punto de agarre', showlegend: false,
            hovertemplate: `Agarre #${agarreSeleccionado}<extra></extra>`,
        });
    }

    const layout = {
        ...getPlotlyLayoutBase(),
        showlegend: true,
        legend: { x: 0, y: 1, font: { size: 9, color: c.font }, bgcolor: 'transparent' },
        xaxis: {
            title: { text: cfg.titX, font: { size: 9 } },
            gridcolor: c.grid, zeroline: false,
            tickfont: { size: 8, color: c.font },
        },
        yaxis: {
            title: { text: cfg.titY, font: { size: 9 } },
            gridcolor: c.grid, zeroline: false,
            tickfont: { size: 8, color: c.font },
            scaleanchor: 'x',
        },
        margin: { t: 10, r: 20, b: 45, l: 50 },
    };

    Plotly.react(containerId, traces, layout, PLOTLY_CONFIG);
}


// =============================================================================
// RADAR CHART DE MÉTRICAS BIOMECÁNICAS
// =============================================================================

/**
 * Renderiza un gráfico de araña con las métricas normalizadas del paciente.
 * Referencia (100%) = valor clínico de referencia razonable.
 */
function renderizarRadar(containerId, metricas) {
    const c = getThemeColors();

    // Valores de referencia para normalización (100% = "buen" rendimiento clínico).
    // Para tiempos (invertir:true): menos tiempo = mejor score.
    const items = [
        { key: 'distancia_m',          label: 'Trayectoria',  ref: 2.0,  invertir: false },
        { key: 'velocidad_media_ms',    label: 'Vel. Media',   ref: 0.5,  invertir: false },
        { key: 'velocidad_pico_ms',     label: 'Vel. Pico',    ref: 1.2,  invertir: false },
        { key: 'ratio_eficiencia_pct',  label: 'Eficiencia',   ref: 60,   invertir: false },
        { key: 'num_transiciones',      label: 'Transiciones', ref: 30,   invertir: false },
        { key: 'tiempo_transporte_s',   label: 'T. Transp.',   ref: 15,   invertir: true  },
        { key: 'tiempo_alcance_s',      label: 'T. Alcance',   ref: 15,   invertir: true  },
    ];

    const scores = items.map(({ key, ref, invertir }) => {
        const val = metricas[key] ?? 0;
        let pct = Math.min((val / ref) * 100, 150);
        if (invertir) pct = Math.max(0, 100 - pct + 50); // penaliza tiempo excesivo
        return Math.min(Math.round(pct), 100);
    });

    const labels   = items.map(i => i.label);
    const rValues  = [...scores, scores[0]];
    const rLabels  = [...labels, labels[0]];

    const trace = {
        type: 'scatterpolar',
        r:     rValues,
        theta: rLabels,
        fill:  'toself',
        fillcolor: 'rgba(79,172,254,0.15)',
        line:  { color: CHART_COLORS.alcance, width: 2 },
        name:  'Perfil actual',
        hovertemplate: '<b>%{theta}</b><br>%{r}%<extra></extra>',
    };

    // Línea de referencia (100%)
    const traceRef = {
        type: 'scatterpolar',
        r:     new Array(rLabels.length).fill(100),
        theta: rLabels,
        mode:  'lines',
        line:  { color: 'rgba(255,158,0,0.35)', width: 1.5, dash: 'dot' },
        name:  'Referencia',
        hoverinfo: 'none',
    };

    const layout = {
        ...getPlotlyLayoutBase(),
        showlegend: false,
        polar: {
            bgcolor: 'transparent',
            radialaxis: {
                visible:  true,
                range:    [0, 100],
                gridcolor: c.grid,
                tickfont: { size: 8, color: c.font },
                ticksuffix: '%',
                tickvals: [25, 50, 75, 100],
            },
            angularaxis: {
                gridcolor: c.grid,
                tickfont:  { size: 9, color: c.font },
            },
        },
        margin: { t: 20, r: 30, b: 20, l: 30 },
    };

    Plotly.react(containerId, [trace, traceRef], layout, PLOTLY_CONFIG);
}
