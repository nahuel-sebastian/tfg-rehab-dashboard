/* =============================================================================
   Aplicación Vue 3 — Dashboard HMI Rehabilitación Robótica
   =============================================================================
   SPA con navegación por estados: pacientes → sesiones → juegos → dashboard.

   Fuentes de datos en paralelo:
     - CSV  → pacientes BBT leídos del filesystem (siempre disponible)
     - SQL  → pacientes Fruits Reach en MySQL (opcional, fallo silencioso)

   El estado de navegación lo controla `vista` (string). Los datos del dashboard
   activo viven en `dd` y se limpian al retroceder en la navegación.
   ============================================================================= */

const { createApp, nextTick } = Vue;

createApp({

    data() {
        return {
            // Tema. La elección se recuerda entre visitas (RF-27); en modo
            // privado o con almacenamiento bloqueado se cae al tema claro.
            temaOscuro: (() => {
                try { return localStorage.getItem('tema') === 'dark'; }
                catch (e) { return false; }
            })(),

            // Navegación
            vista: 'pacientes',
            pacientes: [],
            pacienteSeleccionado: null,
            sesiones: [],
            sesionSeleccionada: null,
            juegos: [],
            juegoSeleccionado: null,

            // Dashboard
            dd: null,
            mensajeError: '',
            cargando: false,   // overlay de carga durante fetch
            webglDisponible: true,   // la trayectoria 3D requiere WebGL; se comprueba al montar

            // Evolución temporal (BBT CSV)
            evolucion: null,
            evolucionMetrica: 'completed',

            // Evolución temporal (Fruits SQL)
            evolucionFruits: null,
            evolucionFruitsMetrica: 'frutas_por_minuto',

            // Reproducción (BBT)
            currentIndex: 0,
            maxIndexGlobal: 0,
            isPlaying: false,
            intervalId: null,
            layoutFijo: null,   // layout 3D Plotly preservado entre renders

            // Segmentación (BBT)
            rangoInicio: 0,
            rangoFin: 0,
            inputInicio: 0,
            inputFin: 0,

            // Comparación de sesiones Fruits
            modoComparacion: false,
            ddComparar: null,

            // Filtro de fechas (vista sesiones)
            filtroFechaDesde: '',
            filtroFechaHasta: '',

            // Comparación de manos BBT
            ddComparacionManos: null,
            graficosVisibles: {},

            // Análisis avanzado BBT
            agarreSeleccionado:    null,
            umbralAnomaliaFrames:  80,
            anomaliasBBT:          [],
            ddVelocidadComparar:   null,
            velCompLabels:         ['', ''],      // [mano actual, otra mano]
            velCompVisible:        [true, true],  // visibilidad de cada traza
            velCompModalAbierto:   false,         // el modal se oculta sin perder los datos (los usa el PDF)

            // Resumen clínico (copiar al portapapeles)
            resumenCopiado: false,

            // Trayectoria fantasma (otra sesión superpuesta en el 3D)
            ddFantasma:         null,
            fantasmaLabel:      '',
            fantasmaCandidatos: [],
            fantasmaSel:        '',
            fantasmaBuscado:    false,
            cargandoFantasma:   false,

            // Filtro de pacientes
            filtroPaciente: '',

            // Velocidad de reproducción
            velocidadReproduccion: 1,

            // Exportación PDF
            pdfModalAbierto: false,
            pdfSecciones:    [],
            pdfNotas:        '',
            pdfGenerando:    false,
            mostrarHeatmap:  false,
            planoHeatmap:    'planta',   // plano de proyección del heatmap: planta | frontal | perfil

            // Sección activa del dashboard (libro)
            seccionActivaBBT:    'info',
            seccionActivaFruits: 'info',
        };
    },

    computed: {
        estadoMano() {
            if (!this.dd || this.currentIndex === 0) {
                return { texto: 'Esperando...', clase: 'text-t-dimmed border-t-border' };
            }
            const tieneObjeto = this.dd.grasps[this.currentIndex];
            return tieneObjeto
                ? { texto: 'Transporte (Con Objeto)', clase: 'text-transporte border-transporte phase-transporte' }
                : { texto: 'Alcance (Mano Vacía)',    clase: 'text-alcance border-alcance phase-alcance' };
        },

        colorEficiencia() {
            const r = this.dd?.metricas?.ratio_eficiencia_pct ?? 0;
            if (r >= 40) return 'text-t-green';
            if (r >= 20) return 'text-t-yellow';
            return 'text-t-red';
        },

        bgEficiencia() {
            const r = this.dd?.metricas?.ratio_eficiencia_pct ?? 0;
            if (r >= 40) return 'bg-green-500';
            if (r >= 20) return 'bg-yellow-500';
            return 'bg-red-500';
        },

        pacientesFiltrados() {
            if (!this.filtroPaciente.trim()) return this.pacientes;
            const q = this.filtroPaciente.toLowerCase().trim();
            return this.pacientes.filter(p => {
                const nombre = p.source === 'csv'
                    ? p.name
                    : `${p.UserName || ''} ${p.UserSurname1 || ''} ${p.UserSurname2 || ''} ${p.UserID}`;
                return nombre.toLowerCase().includes(q);
            });
        },

        sesionesFiltradas() {
            if (!this.filtroFechaDesde && !this.filtroFechaHasta) return this.sesiones;
            return this.sesiones.filter(s => {
                if (!s.Date) return true;
                const fecha = this._parseFecha(s.Date);
                if (isNaN(fecha)) return true;
                if (this.filtroFechaDesde && fecha < new Date(this.filtroFechaDesde)) return false;
                if (this.filtroFechaHasta) {
                    const hasta = new Date(this.filtroFechaHasta);
                    hasta.setHours(23, 59, 59, 999);
                    if (fecha > hasta) return false;
                }
                return true;
            });
        },

        // Agrupa los juegos de la sesión: empareja BBT Derecha+Izquierda en una sola entrada,
        // el resto (Fruits, BBT solo de una mano) quedan como entradas individuales.
        juegosPareados() {
            const bbt   = this.juegos.filter(j => j.game_type === 'bbt');
            const otros = this.juegos.filter(j => j.game_type !== 'bbt');
            const result = [];
            const usados = new Set();

            // hand_label funciona tanto para juegos SQL (hand_type) como CSV (hand)
            const esDerc = j => j.hand_label === 'Derecha';
            const esIzq  = j => j.hand_label === 'Izquierda';

            for (const d of bbt.filter(esDerc)) {
                const i = bbt.find(j => esIzq(j) && !usados.has(j.register_id));
                if (i) {
                    result.push({ tipo: 'par', derecha: d, izquierda: i,
                        game_name: d.game_name, is_vr: d.is_vr, session_date: d.session_date });
                    usados.add(d.register_id);
                    usados.add(i.register_id);
                }
            }
            for (const g of bbt) {
                if (!usados.has(g.register_id)) result.push({ tipo: 'individual', juego: g });
            }
            for (const g of otros) {
                result.push({ tipo: 'individual', juego: g });
            }
            return result;
        },

        // Claves de mano presentes en el dashboard Fruits activo, en orden canónico.
        // Incluye 'NONE' (registro sin lateralidad declarada) para no dejar el panel vacío.
        clavesManos() {
            const hands = this.dd?.hands || {};
            return ['RIGHT', 'LEFT', 'BOTH', 'NONE'].filter(h => hands[h]);
        },

        // Alerta de asimetría bilateral en Fruits (misma fórmula que el gráfico:
        // diferencia / media en frutas/min). null si no aplica o < 20% (umbral clínico).
        alertaAsimetria() {
            const r = this.dd?.hands?.RIGHT?.metricas?.frutas_por_minuto;
            const l = this.dd?.hands?.LEFT?.metricas?.frutas_por_minuto;
            if (r == null || l == null) return null;
            const media = (r + l) / 2;
            if (media === 0) return null;
            const pct = Math.abs(r - l) / media * 100;
            if (pct < 20) return null;
            return {
                pct:       Math.round(pct),
                manoDebil: r < l ? 'Derecha' : 'Izquierda',
                severidad: pct >= 40 ? 'severa' : 'moderada',
            };
        },
    },

    methods: {

        // Comprueba una sola vez si el navegador soporta WebGL (necesario para el 3D)
        _detectarWebGL() {
            try {
                const canvas = document.createElement('canvas');
                return !!(window.WebGLRenderingContext &&
                    (canvas.getContext('webgl') || canvas.getContext('experimental-webgl')));
            } catch (e) {
                return false;
            }
        },

        // =============================================================
        // ETIQUETAS DE MANO (normaliza CSV 2/1 y SQL 'right'/'left'/'both')
        // =============================================================

        // Texto legible de la mano evaluada en BBT a partir de dd.hand.
        // CSV → numérico (2/1); SQL → string lowercase ('right'/'left'/'both'); mock → 2.
        manoTextoBBT(hand) {
            if (hand === 2 || hand === 'R' || hand === 'RIGHT' || hand === 'right') return 'Derecha';
            if (hand === 1 || hand === 'L' || hand === 'LEFT'  || hand === 'left')  return 'Izquierda';
            if (hand === 'BOTH' || hand === 'both') return 'Ambas';
            return '—';
        },

        // Nombre legible del modo de juego Fruits.
        modoTitulo(mode) {
            return { reach: 'Alcance', grab: 'Agarre', sequence: 'Secuencia', flip: 'Volteo', race: 'Race' }[mode] || mode || '—';
        },

        // Título de la tarjeta por mano en dashboards Fruits.
        manoTitulo(handKey) {
            return { RIGHT: '→ Derecha', LEFT: '← Izquierda', BOTH: '↔ Ambas', NONE: 'Mano única' }[handKey] || handKey;
        },

        // Clase de color del título por mano.
        manoClaseTexto(handKey) {
            return { RIGHT: 'text-t-blue', LEFT: 'text-transporte', BOTH: 'text-t-green', NONE: 'text-t-muted' }[handKey] || 'text-t-muted';
        },

        // =============================================================
        // TEMA
        // =============================================================

        // Escribe el tema en el DOM y lo persiste. Se llama desde el toggle y
        // al montar, de modo que la elección sobrevive a la recarga.
        _aplicarTema() {
            document.documentElement.setAttribute(
                'data-theme',
                this.temaOscuro ? 'dark' : 'light'
            );
            try { localStorage.setItem('tema', this.temaOscuro ? 'dark' : 'light'); }
            catch (e) { /* almacenamiento no disponible: el tema dura la sesión */ }
        },

        toggleTema() {
            this.temaOscuro = !this.temaOscuro;
            this._aplicarTema();
            if (this.dd && (this.vista === 'dashboard' || this.vista === 'comparar')) {
                nextTick(() => {
                    if (this.dd.game_type === 'bbt') {
                        if (this.webglDisponible) {
                            this.layoutFijo = reRenderizarGraficos(
                                this.dd, this.rangoInicio, this.currentIndex, this.layoutFijo, this.anomaliasBBT, this.agarreSeleccionado, this.ddFantasma
                            );
                        } else {
                            // sin 3D: re-renderizar solo los 2D que toca el tema
                            renderizarVelocidad('plotVelocidad', this.dd.timestamps, this.dd.velocidades, this.dd.grasps);
                            renderizarScores('plotScores', this.dd.scores_por_frame, this.anomaliasBBT);
                        }
                        if (this.dd.metricas) renderizarRadar('plotRadar', this.dd.metricas);
                        if (this.mostrarHeatmap) renderizarHeatmap('plotHeatmap', this.dd, this.planoHeatmap, this.agarreSeleccionado);
                        // solo si el modal está visible: renderizar en un contenedor oculto
                        // deja el plot con tamaño por defecto al reabrirlo
                        if (this.ddVelocidadComparar && this.velCompModalAbierto) this._renderVelocidadComparacion();
                    } else if (this.dd.game_type?.startsWith('fruits')) {
                        renderizarFruitsComparacion('plotFruitsComparacion', this.dd);
                        renderizarFruitsTimes('plotFruitsTimes', this.dd);
                        renderizarFruitsAsimetria('plotFruitsAsimetria', this.dd);
                        if (this.dd.game_type === 'fruits_race') renderizarRaceScatter('plotRaceScatter', this.dd);
                    }
                });
            } else if (this.vista === 'comparar_manos' && this.ddComparacionManos) {
                // Re-renderizar solo los mini-gráficos que estén visibles
                nextTick(() => {
                    const todas = [
                        { key: 'distancia_m',         label: 'Trayectoria',   unit: 'm'   },
                        { key: 'velocidad_media_ms',   label: 'Vel. Media',    unit: 'm/s' },
                        { key: 'velocidad_pico_ms',    label: 'Vel. Pico',     unit: 'm/s' },
                        { key: 'tiempo_alcance_s',     label: 'T. Alcance',    unit: 's'   },
                        { key: 'tiempo_transporte_s',  label: 'T. Transporte', unit: 's'   },
                        { key: 'num_transiciones',     label: 'Transiciones',  unit: ''    },
                        { key: 'ratio_eficiencia_pct', label: 'Eficiencia',    unit: '%'   },
                        { key: 'completed',            label: 'Completados',   unit: ''    },
                        { key: 'no_valid',             label: 'No Válidos',    unit: ''    },
                        { key: 'out_of_zone',          label: 'Fuera Zona',    unit: ''    },
                    ];
                    for (const m of todas) {
                        if (this.graficosVisibles[m.key]) {
                            const valD = this.ddComparacionManos?.derecha?.metricas?.[m.key]
                                      ?? this.ddComparacionManos?.derecha?.penalizaciones?.[m.key] ?? 0;
                            const valI = this.ddComparacionManos?.izquierda?.metricas?.[m.key]
                                      ?? this.ddComparacionManos?.izquierda?.penalizaciones?.[m.key] ?? 0;
                            _renderizarMiniGrafico(`plot_cmp_${m.key}`, `${m.label}${m.unit ? ' (' + m.unit + ')' : ''}`, valD, valI);
                        }
                    }
                });
            } else if (this.vista === 'evolucion' && this.evolucion) {
                nextTick(() => {
                    renderizarEvolucion('plotEvolucion', this.evolucion.sessions, this.evolucionMetrica);
                });
            } else if (this.vista === 'evolucion_fruits' && this.evolucionFruits) {
                nextTick(() => {
                    renderizarFruitsEvolucion('plotFruitsEvolucion', this.evolucionFruits.sessions, this.evolucionFruitsMetrica);
                    this._conectarClickEvolucion();
                });
            }
        },


        // =============================================================
        // NAVEGACIÓN
        // =============================================================

        irA(destino) {
            this.pausar();
            if (destino === 'pacientes') {
                this.vista = 'pacientes';
                this.pacienteSeleccionado = null;
                this.sesiones = [];
                this.sesionSeleccionada = null;
                this.juegos = [];
                this.juegoSeleccionado = null;
                this.dd = null;
                this.evolucion = null;
                this.evolucionFruits = null;
                this.modoComparacion = false;
                this.ddComparar = null;
            } else if (destino === 'sesiones') {
                this.vista = 'sesiones';
                this.sesionSeleccionada = null;
                this.juegos = [];
                this.juegoSeleccionado = null;
                this.dd = null;
                this.evolucion = null;
            } else if (destino === 'juegos') {
                this.vista = 'juegos';
                this.juegoSeleccionado      = null;
                this.dd                     = null;
                this.ddComparacionManos     = null;
                this.agarreSeleccionado     = null;
                this.ddVelocidadComparar    = null;
                this.velCompModalAbierto    = false;
                this.mostrarHeatmap         = false;
                this.anomaliasBBT           = [];
                this.seccionActivaBBT       = 'info';
                this.seccionActivaFruits    = 'info';
                this._resetFantasma();
            } else if (destino === 'evolucion') {
                this.vista = 'evolucion';
            }
        },

        // Parsea fechas de la API de forma portable: Safari no acepta
        // 'YYYY-MM-DD HH:MM:SS' (el ISO exige 'T' como separador)
        _parseFecha(str) {
            if (!str) return new Date(NaN);
            let d = new Date(str);
            if (isNaN(d)) d = new Date(String(str).replace(' ', 'T'));
            return d;
        },

        // Formatea un string datetime a "DD/MM/YYYY HH:MM"
        formatearFecha(dateStr) {
            if (!dateStr) return '—';
            const d = this._parseFecha(dateStr);
            if (isNaN(d)) return dateStr;
            const pad = n => String(n).padStart(2, '0');
            return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
        },

        // Etiqueta del paciente seleccionado para el breadcrumb
        nombrePaciente(p) {
            if (!p) return '';
            return p.source === 'csv' ? p.name : `${p.UserName || ''} ${p.UserSurname1 || ''}`.trim() || `Paciente #${p.UserID}`;
        },

        // Etiqueta de la sesión para el breadcrumb
        labelSesion(s) {
            if (!s) return '';
            return s.isCSV ? s.Date : `Sesión #${s.SessionID}`;
        },


        // =============================================================
        // CARGA DE DATOS
        // =============================================================

        async cargarPacientes() {
            this.mensajeError = '';
            this.cargando = true;

            const [csvResult, sqlResult] = await Promise.allSettled([
                fetch(`${API_BASE}/api/csv/patients`).then(r => r.json()),
                fetch(`${API_BASE}/api/patients`).then(r => r.json()),
            ]);

            const lista = [];

            if (csvResult.status === 'fulfilled') {
                for (const p of (csvResult.value.patients || [])) {
                    lista.push({
                        source: 'csv', _key: `csv_${p.name}`, name: p.name,
                        has_desktop: p.has_desktop, has_vr: p.has_vr,
                        total_sesiones: p.total_sessions,
                    });
                }
            } else {
                this.mensajeError = `Error cargando pacientes CSV: ${csvResult.reason?.message}`;
            }

            if (sqlResult.status === 'fulfilled') {
                for (const p of (sqlResult.value.patients || [])) {
                    lista.push({ ...p, source: 'sql', _key: `sql_${p.UserID}` });
                }
            }
            // SQL es opcional — fallo silencioso

            this.pacientes = lista;
            this.cargando = false;
        },

        async seleccionarPaciente(paciente) {
            this.mensajeError = '';
            this.pacienteSeleccionado = paciente;
            this.cargando = true;

            if (paciente.source === 'csv') {
                try {
                    const res  = await fetch(`${API_BASE}/api/csv/patients/${encodeURIComponent(paciente.name)}/sessions`);
                    const data = await res.json();
                    this.sesiones = (data.sessions || []).map((s, i) => ({
                        SessionID: `csv-${i}`,
                        Date:      s.date,
                        isCSV:     true,
                        is_vr:     s.is_vr,
                        label:     s.label,
                        games:     s.games,
                    }));
                    this.vista = 'sesiones';
                } catch (e) {
                    this.mensajeError = `Error cargando sesiones: ${e.message}`;
                } finally {
                    this.cargando = false;
                }
            } else {
                try {
                    const res  = await fetch(`${API_BASE}/api/patients/${paciente.UserID}/sessions`);
                    const data = await res.json();
                    if (data.error) throw new Error(data.error);
                    this.sesiones = data.sessions;
                    this.vista = 'sesiones';
                } catch (e) {
                    this.mensajeError = `Error cargando sesiones: ${e.message}`;
                } finally {
                    this.cargando = false;
                }
            }
        },

        async seleccionarSesion(sesion) {
            this.mensajeError = '';
            this.sesionSeleccionada = sesion;

            if (sesion.isCSV) {
                this.juegos = sesion.games;
                this.vista  = 'juegos';
            } else {
                this.cargando = true;
                try {
                    const res  = await fetch(`${API_BASE}/api/sessions/${sesion.SessionID}/games`);
                    const data = await res.json();
                    if (data.error) throw new Error(data.error);
                    this.juegos = data.games;
                    this.vista  = 'juegos';
                } catch (e) {
                    this.mensajeError = `Error cargando juegos: ${e.message}`;
                } finally {
                    this.cargando = false;
                }
            }
        },

        async seleccionarJuego(juego) {
            this.mensajeError = '';
            // En modo comparación solo tiene sentido el MISMO modo Fruits (comparar
            // Race contra Alcance daría porcentajes sin sentido clínico)
            if (this.modoComparacion && juego.game_type !== this.ddComparar?.game_type) {
                this.mensajeError = `Modo comparación activo: selecciona otro juego del mismo modo (${this.modoTitulo(this.ddComparar?.game_mode)}) o cancela la comparación.`;
                return;
            }
            this.juegoSeleccionado = juego;

            let url = '';
            if (juego.game_type === 'bbt') {
                url = this._urlBBT(juego);
            } else if (juego.game_type === 'fruits') {
                url = `${API_BASE}/api/fruits/${juego.register_id}`;
            } else if (juego.game_type === 'fruits_sequence') {
                url = `${API_BASE}/api/fruits-sequence/${juego.register_id}`;
            } else if (juego.game_type === 'fruits_grab') {
                url = `${API_BASE}/api/fruits-grab/${juego.register_id}`;
            } else if (juego.game_type === 'fruits_flip') {
                url = `${API_BASE}/api/fruits-flip/${juego.register_id}`;
            } else if (juego.game_type === 'fruits_race') {
                url = `${API_BASE}/api/fruits-race/${juego.register_id}`;
            }

            if (!url) {
                this.mensajeError = `Dashboard no implementado para: ${juego.game_type}`;
                return;
            }

            this.cargando = true;
            try {
                const res  = await fetch(url);
                const data = await res.json();
                if (data.error) throw new Error(data.error);

                // Modo comparación: segunda sesión cargada → ir a comparar
                if (this.modoComparacion && data.game_type?.startsWith('fruits')) {
                    this.dd = data;
                    this.modoComparacion = false;
                    this.vista = 'comparar';
                    return;
                }

                this.dd   = data;
                this.vista = 'dashboard';
                this.seccionActivaBBT    = 'info';
                this.seccionActivaFruits = 'info';

                if (data.game_type === 'bbt') {
                    this.maxIndexGlobal         = data.x.length - 1;
                    this.rangoInicio            = 0;
                    this.rangoFin               = this.maxIndexGlobal;
                    this.inputInicio            = 0;
                    this.inputFin               = this.maxIndexGlobal;
                    // Trayectoria completa visible al entrar (un solo punto parece un fallo);
                    // Inicio / Reproducir rebobinan al principio del rango
                    this.currentIndex           = this.maxIndexGlobal;
                    this.agarreSeleccionado     = null;
                    this.ddVelocidadComparar    = null;
                    this.velCompModalAbierto    = false;
                    this.mostrarHeatmap         = false;
                    this._resetFantasma();
                    this.anomaliasBBT = this._calcularAnomalias(
                        data.scores_por_frame || [], data.timestamps || [], this.umbralAnomaliaFrames
                    );
                    // Pre-inicializar gráficos en background para PDF (v-show los mantiene en DOM)
                    nextTick(() => {
                        if (this.webglDisponible) {
                            this.layoutFijo = inicializarGrafico3D('plot3d', data);
                            this.actualizarGrafica3D();
                        }
                        renderizarVelocidad('plotVelocidad', data.timestamps, data.velocidades, data.grasps);
                        renderizarScores('plotScores', data.scores_por_frame, this.anomaliasBBT);
                        if (data.metricas) renderizarRadar('plotRadar', data.metricas);
                    });
                } else if (data.game_type?.startsWith('fruits')) {
                    nextTick(() => {
                        renderizarFruitsComparacion('plotFruitsComparacion', data);
                        renderizarFruitsTimes('plotFruitsTimes', data);
                        renderizarFruitsAsimetria('plotFruitsAsimetria', data);
                        if (data.game_type === 'fruits_race') renderizarRaceScatter('plotRaceScatter', data);
                    });
                }
            } catch (e) {
                this.mensajeError = `Error cargando dashboard: ${e.message}`;
            } finally {
                this.cargando = false;
            }
        },


        // =============================================================
        // NAVEGACIÓN DE SECCIONES (Dashboard sidebar)
        // =============================================================

        cambiarSeccionBBT(sec) {
            this.seccionActivaBBT = sec;
            nextTick(() => {
                if (!this.dd) return;
                if (sec === 'reproduccion') {
                    if (this.webglDisponible) {
                        this.layoutFijo = inicializarGrafico3D('plot3d', this.dd, this.ddFantasma);
                        this.actualizarGrafica3D();
                    }
                    if (this.mostrarHeatmap) renderizarHeatmap('plotHeatmap', this.dd, this.planoHeatmap, this.agarreSeleccionado);
                } else if (sec === 'velocidad') {
                    renderizarVelocidad('plotVelocidad', this.dd.timestamps, this.dd.velocidades, this.dd.grasps);
                } else if (sec === 'biomecanica' && this.dd.metricas) {
                    renderizarRadar('plotRadar', this.dd.metricas);
                } else if (sec === 'puntuacion') {
                    renderizarScores('plotScores', this.dd.scores_por_frame, this.anomaliasBBT);
                }
            });
        },

        cambiarSeccionFruits(sec) {
            this.seccionActivaFruits = sec;
            nextTick(() => {
                if (!this.dd) return;
                if (sec === 'comparacion') {
                    renderizarFruitsComparacion('plotFruitsComparacion', this.dd);
                } else if (sec === 'fatiga') {
                    renderizarFruitsTimes('plotFruitsTimes', this.dd);
                } else if (sec === 'asimetria') {
                    renderizarFruitsAsimetria('plotFruitsAsimetria', this.dd);
                } else if (sec === 'race') {
                    renderizarRaceScatter('plotRaceScatter', this.dd);
                }
            });
        },


        // =============================================================
        // COMPARACIÓN DE SESIONES
        // =============================================================

        iniciarComparacion() {
            this.ddComparar = this.dd;
            this.modoComparacion = true;
            this.pausar();
            this.vista = 'sesiones';
            this.sesionSeleccionada = null;
            this.juegos = [];
            this.juegoSeleccionado = null;
            this.dd = null;
        },

        cancelarComparacion() {
            this.modoComparacion = false;
            this.ddComparar = null;
            this.irA('sesiones');
        },

        _urlBBT(juego) {
            if (juego.csv_params) {
                const p = juego.csv_params;
                return `${API_BASE}/api/csv/bbt?patient=${encodeURIComponent(p.patient)}&modalidad=${p.modalidad}&hand=${p.hand}&datetime_str=${encodeURIComponent(p.datetime_str)}`;
            }
            return `${API_BASE}/api/bbt/${juego.register_id}`;
        },

        // ── Cálculo client-side de anomalías (score estancado > umbral frames) ──
        _calcularAnomalias(scores, timestamps, umbral) {
            const result = [];
            const n = scores.length;
            let i = 0, num = 0;
            while (i < n) {
                let j = i + 1;
                while (j < n && scores[j] === scores[i]) j++;
                const dur = j - i;
                if (dur >= umbral) {
                    num++;
                    result.push({
                        num,
                        frame_inicio:   i,
                        frame_fin:      j - 1,
                        score:          scores[i],
                        duracion_frames: dur,
                        tiempo_inicio_s: timestamps[i]     != null ? Math.round(timestamps[i]     * 100) / 100 : null,
                        tiempo_fin_s:    timestamps[j - 1] != null ? Math.round(timestamps[j - 1] * 100) / 100 : null,
                    });
                }
                i = j;
            }
            return result;
        },

        // ── Filtrar trayectoria 3D a un agarre concreto ──
        seleccionarAgarre(num) {
            if (num === null) {
                this.agarreSeleccionado = null;
                this.rangoInicio  = 0;
                this.rangoFin     = this.maxIndexGlobal;
                this.inputInicio  = 0;
                this.inputFin     = this.maxIndexGlobal;
                this.currentIndex = this.rangoFin;
            } else {
                const seg = this.dd?.grasp_segments?.find(s => s.num === num);
                if (!seg) return;
                this.agarreSeleccionado = num;
                this.rangoInicio  = seg.frame_inicio_reach;
                this.rangoFin     = seg.frame_fin;
                this.inputInicio  = seg.frame_inicio_reach;
                this.inputFin     = seg.frame_fin;
                this.currentIndex = seg.frame_fin;
            }
            this.actualizarGrafica3D();
            // El heatmap resalta el agarre seleccionado → re-renderizar si está visible
            if (this.mostrarHeatmap) {
                renderizarHeatmap('plotHeatmap', this.dd, this.planoHeatmap, this.agarreSeleccionado);
            }
        },

        // ── Ver frames de una anomalía en la trayectoria 3D ──
        verFramesAnomalia(anomalia) {
            this.agarreSeleccionado = null;
            this.rangoInicio  = anomalia.frame_inicio;
            this.rangoFin     = anomalia.frame_fin;
            this.inputInicio  = anomalia.frame_inicio;
            this.inputFin     = anomalia.frame_fin;
            this.currentIndex = anomalia.frame_fin;
            // Navegar a la sección 3D y renderizar con el rango de la anomalía
            this.seccionActivaBBT = 'reproduccion';
            nextTick(() => {
                if (this.webglDisponible) {
                    this.layoutFijo = inicializarGrafico3D('plot3d', this.dd, this.ddFantasma);
                    this.actualizarGrafica3D();
                }
                document.getElementById('plot3d')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
            });
        },

        // ── Recomputar anomalías al cambiar el umbral ──
        cambiarUmbralAnomalia() {
            if (!this.dd?.scores_por_frame?.length) return;
            this.anomaliasBBT = this._calcularAnomalias(
                this.dd.scores_por_frame, this.dd.timestamps, this.umbralAnomaliaFrames
            );
            renderizarScores('plotScores', this.dd.scores_por_frame, this.anomaliasBBT);
        },

        // ── Cargar velocidad de la otra mano y superponer ──
        async cargarVelocidadOtraMano() {
            if (!this.sesionSeleccionada || !this.dd) return;
            this.mensajeError = '';
            // Etiqueta real de la mano actual (cubre 'both'/'none', no solo D/I)
            const manoActual = this.juegoSeleccionado?.hand_label
                            || this.manoTextoBBT(this.juegoSeleccionado?.hand ?? this.dd?.hand);
            const buscarLabel = manoActual === 'Derecha' ? 'Izquierda' : 'Derecha';
            try {
                // this.juegos ya tiene los juegos de la sesión activa (SQL y CSV)
                const otroJuego = this.juegos?.find(
                    g => g.game_type === 'bbt' && g.hand_label === buscarLabel
                );
                if (!otroJuego) { this.mensajeError = 'No hay datos de la otra mano en esta sesión.'; return; }
                const res  = await fetch(this._urlBBT(otroJuego));
                const data = await res.json();
                if (data.error) throw new Error(data.error);
                this.ddVelocidadComparar    = data;
                this.velCompLabels          = [manoActual, buscarLabel];
                this.velCompVisible         = [true, true];
                this.velCompModalAbierto    = true;
                nextTick(() => this._renderVelocidadComparacion());
            } catch (e) {
                this.mensajeError = `Error cargando comparación de velocidad: ${e.message}`;
            }
        },

        // Renderiza la comparación de velocidad respetando la visibilidad de cada mano
        _renderVelocidadComparacion() {
            if (!this.ddVelocidadComparar || !this.dd) return;
            renderizarVelocidadComparacion(
                'plotVelocidadComparacion',
                this.dd, this.velCompLabels[0],
                this.ddVelocidadComparar, this.velCompLabels[1]
            );
            const el = document.getElementById('plotVelocidadComparacion');
            if (!el) return;
            this.velCompVisible.forEach((visible, idx) => {
                if (!visible) Plotly.restyle(el, { visible: 'legendonly' }, [idx]);
            });
        },

        // Oculta/muestra una de las dos trazas para ver la otra sin superposición
        toggleVelocidadMano(idx) {
            this.velCompVisible[idx] = !this.velCompVisible[idx];
            const el = document.getElementById('plotVelocidadComparacion');
            if (el) Plotly.restyle(el, { visible: this.velCompVisible[idx] ? true : 'legendonly' }, [idx]);
        },

        toggleGraficoComparacion(key, label, unit) {
            this.graficosVisibles = { ...this.graficosVisibles, [key]: !this.graficosVisibles[key] };
            if (this.graficosVisibles[key]) {
                const valD = this.ddComparacionManos?.derecha?.metricas?.[key]
                          ?? this.ddComparacionManos?.derecha?.penalizaciones?.[key] ?? 0;
                const valI = this.ddComparacionManos?.izquierda?.metricas?.[key]
                          ?? this.ddComparacionManos?.izquierda?.penalizaciones?.[key] ?? 0;
                nextTick(() => _renderizarMiniGrafico(`plot_cmp_${key}`, `${label} (${unit || 'u.'})`, valD, valI));
            }
        },

        async compararManosBBT(juegoDerc, juegoIzq) {
            if (!juegoDerc || !juegoIzq) return;
            this.mensajeError = '';
            try {
                const [resD, resI] = await Promise.all([
                    fetch(this._urlBBT(juegoDerc)).then(r => r.json()),
                    fetch(this._urlBBT(juegoIzq)).then(r => r.json()),
                ]);
                if (resD.error) throw new Error(resD.error);
                if (resI.error) throw new Error(resI.error);
                this.ddComparacionManos = { derecha: resD, izquierda: resI };
                this.graficosVisibles = {};
                this.vista = 'comparar_manos';
            } catch (e) {
                this.mensajeError = `Error cargando comparación de manos: ${e.message}`;
            }
        },

        // Calcula el delta entre sesión A (ddComparar) y sesión B (dd)
        // mayorEsMejor: true para frutas/min, false para tiempos
        // Devuelve { pct, mejora } o null si no hay datos
        deltaFruits(hand, metrica, mayorEsMejor) {
            const a = this.ddComparar?.hands?.[hand]?.metricas?.[metrica];
            const b = this.dd?.hands?.[hand]?.metricas?.[metrica];
            if (a == null || b == null || a === 0) return null;
            const pct = parseFloat(((b - a) / a * 100).toFixed(1));
            const mejora = mayorEsMejor ? b > a : b < a;
            return { pct, mejora };
        },


        // =============================================================
        // SEVERIDAD
        // =============================================================

        severidadClase(valor, umbralMedio, umbralAlto) {
            if (valor >= umbralAlto)  return 'severity-high';
            if (valor >= umbralMedio) return 'severity-medium';
            return 'severity-low';
        },

        severidadBarra(valor, umbralMedio, umbralAlto) {
            if (valor >= umbralAlto)  return 'bg-red-500';
            if (valor >= umbralMedio) return 'bg-yellow-500';
            return 'bg-green-500';
        },


        // =============================================================
        // SEGMENTACIÓN (BBT)
        // =============================================================

        validarRango() {
            if (this.inputFin > this.maxIndexGlobal)     this.inputFin    = this.maxIndexGlobal;
            if (this.inputFin < 1)                       this.inputFin    = 1;
            if (this.inputInicio < 0)                    this.inputInicio = 0;
            if (this.inputInicio >= this.inputFin)       this.inputInicio = this.inputFin - 1;
        },

        aplicarRango() {
            this.pausar();
            this.validarRango();
            this.rangoInicio  = this.inputInicio;
            this.rangoFin     = this.inputFin;
            this.currentIndex = this.rangoInicio;
            this.actualizarGrafica3D();
        },


        // =============================================================
        // REPRODUCCIÓN (BBT)
        // =============================================================

        siguientePunto() {
            if (this.currentIndex < this.rangoFin) {
                this.currentIndex++;
                this.actualizarGrafica3D();
            } else {
                this.pausar();
            }
        },

        reiniciar() {
            this.pausar();
            this.currentIndex = this.rangoInicio;
            this.actualizarGrafica3D();
        },

        togglePlay() {
            if (this.isPlaying) { this.pausar(); return; }
            if (this.currentIndex >= this.rangoFin) this.currentIndex = this.rangoInicio;
            this._iniciarInterval();
        },

        cambiarVelocidad(v) {
            this.velocidadReproduccion = v;
            if (this.isPlaying) {
                clearInterval(this.intervalId);
                this._iniciarInterval();
            }
        },

        _iniciarInterval() {
            this.isPlaying  = true;
            const ms = Math.round(50 / this.velocidadReproduccion);
            this.intervalId = setInterval(() => this.siguientePunto(), ms);
        },

        pausar() {
            this.isPlaying = false;
            clearInterval(this.intervalId);
        },


        // =============================================================
        // EVOLUCIÓN TEMPORAL
        // =============================================================

        async verEvolucion() {
            if (!this.pacienteSeleccionado) return;
            this.mensajeError = '';
            // CSV → histórico de ficheros; SQL → game_bbt_score por sesión
            const url = this.pacienteSeleccionado.source === 'csv'
                ? `${API_BASE}/api/csv/patients/${encodeURIComponent(this.pacienteSeleccionado.name)}/evolution`
                : `${API_BASE}/api/patients/${this.pacienteSeleccionado.UserID}/bbt-evolution`;
            try {
                const res  = await fetch(url);
                const data = await res.json();
                if (data.error) throw new Error(data.error);
                this.evolucion = data;
                this.evolucionMetrica = 'completed';
                this.vista = 'evolucion';
                nextTick(() => {
                    renderizarEvolucion('plotEvolucion', data.sessions, this.evolucionMetrica);
                });
            } catch (e) {
                this.mensajeError = `Error cargando evolución: ${e.message}`;
            }
        },

        cambiarMetricaEvolucion(metrica) {
            this.evolucionMetrica = metrica;
            if (this.evolucion) {
                renderizarEvolucion('plotEvolucion', this.evolucion.sessions, metrica);
            }
        },


        // =============================================================
        // EVOLUCIÓN FRUITS (SQL)
        // =============================================================

        async verEvolucionFruits() {
            if (!this.pacienteSeleccionado || this.pacienteSeleccionado.source !== 'sql') return;
            this.mensajeError = '';
            const uid = this.pacienteSeleccionado.UserID;
            try {
                const res  = await fetch(`${API_BASE}/api/patients/${uid}/fruits-evolution`);
                const data = await res.json();
                if (data.error) throw new Error(data.error);
                this.evolucionFruits        = data;
                this.evolucionFruitsMetrica = 'frutas_por_minuto';
                this.vista = 'evolucion_fruits';
                nextTick(() => {
                    renderizarFruitsEvolucion('plotFruitsEvolucion', data.sessions, this.evolucionFruitsMetrica);
                    this._conectarClickEvolucion();
                });
            } catch (e) {
                this.mensajeError = `Error cargando evolución: ${e.message}`;
            }
        },

        cambiarMetricaFruitsEvolucion(metrica) {
            this.evolucionFruitsMetrica = metrica;
            if (this.evolucionFruits) {
                renderizarFruitsEvolucion('plotFruitsEvolucion', this.evolucionFruits.sessions, metrica);
                nextTick(() => this._conectarClickEvolucion());
            }
        },

        // Conecta el evento click del gráfico de evolución para navegar a la sesión
        _conectarClickEvolucion() {
            const el = document.getElementById('plotFruitsEvolucion');
            if (!el) return;
            // Evita apilar handlers al recambiar de métrica (Plotly no los reemplaza)
            el.removeAllListeners?.('plotly_click');
            el.on('plotly_click', (evt) => {
                if (!evt?.points?.length) return;
                const idx = evt.points[0].pointIndex;
                const sesionData = this.evolucionFruits?.sessions?.[idx];
                if (sesionData?.session_id) {
                    this.seleccionarSesion({ SessionID: sesionData.session_id, isCSV: false });
                }
            });
        },


        // =============================================================
        // RESUMEN CLÍNICO (texto estructurado para la historia clínica)
        // =============================================================

        generarResumenClinico() {
            const dd = this.dd;
            if (!dd) return '';
            const lineas = [];
            const entorno = dd.is_vr ? 'VR' : 'Desktop';

            if (dd.game_type === 'bbt') {
                lineas.push(`Prueba BBT (${dd.task_name || 'VABBT'}, ${entorno}) — ${dd.patient || '—'} — ${dd.date || '—'} — Mano ${this.manoTextoBBT(dd.hand)}.`);
                const p = dd.penalizaciones;
                if (p) lineas.push(`Resultado: ${p.completed} cubos completados, ${p.no_valid} no válidos, ${p.out_of_zone} fuera de zona.`);
                const m = dd.metricas;
                if (m) lineas.push(`Métricas: distancia ${m.distancia_m} m; vel. media ${m.velocidad_media_ms} m/s (pico ${m.velocidad_pico_ms}); t. alcance ${m.tiempo_alcance_s} s; t. transporte ${m.tiempo_transporte_s} s; eficiencia ${m.ratio_eficiencia_pct}%.`);
                if (dd.grasp_segments?.length) lineas.push(`Agarres detectados: ${dd.grasp_segments.length} ciclos alcance→transporte.`);
                const f = dd.indice_fatiga;
                if (f) lineas.push(`Fatiga: cambio de velocidad ${f.cambio_pct > 0 ? '+' : ''}${f.cambio_pct}% entre primeros y últimos agarres (${f.fatiga_detectada ? 'FATIGA DETECTADA' : 'sin fatiga significativa'}).`);
                if (this.anomaliasBBT?.length) lineas.push(`Anomalías: ${this.anomaliasBBT.length} bloqueo(s) de puntuación ≥ ${this.umbralAnomaliaFrames} frames.`);
            } else if (dd.game_type?.startsWith('fruits')) {
                lineas.push(`Prueba Fruits — modo ${this.modoTitulo(dd.game_mode)} (${entorno}) — ${dd.patient || '—'} — ${dd.date || '—'}.`);
                for (const k of this.clavesManos) {
                    const h = dd.hands[k];
                    const m = h?.metricas || {};
                    let linea = `${this.manoTitulo(k).replace(/^[→←↔ ]+/, '')}: ${m.total_frutas ?? h.total_fruits} frutas en ${m.tiempo_total_s ?? h.total_time} s (${m.frutas_por_minuto} frutas/min, t. medio ${m.tiempo_medio_s} s)`;
                    if (m.precision_pct != null) linea += `; precisión ${m.precision_pct}% (${m.frutas_falladas} falladas)`;
                    if (m.error_fallo_medio_cm != null) linea += `; error medio en fallos ${m.error_fallo_medio_cm} cm (máx ${m.error_fallo_max_cm} cm)`;
                    lineas.push(linea + '.');
                }
                const a = this.alertaAsimetria;
                if (a) lineas.push(`Asimetría bilateral ${a.severidad} del ${a.pct}% en frutas/min; mano con menor rendimiento: ${a.manoDebil}.`);
            }
            return lineas.join('\n');
        },

        async copiarResumenClinico() {
            const texto = this.generarResumenClinico();
            if (!texto) return;
            try {
                if (navigator.clipboard?.writeText) {
                    await navigator.clipboard.writeText(texto);
                } else {
                    // fallback para file:// y navegadores sin Clipboard API
                    const ta = document.createElement('textarea');
                    ta.value = texto;
                    document.body.appendChild(ta);
                    ta.select();
                    document.execCommand('copy');
                    ta.remove();
                }
                this.resumenCopiado = true;
                setTimeout(() => { this.resumenCopiado = false; }, 2000);
            } catch (e) {
                this.mensajeError = `No se pudo copiar el resumen: ${e.message}`;
            }
        },


        // =============================================================
        // VISTAS DE CÁMARA 3D PREDEFINIDAS
        // =============================================================

        vistaCamara(preset) {
            const el = document.getElementById('plot3d');
            if (!el || !this.webglDisponible) return;
            // Ejes de los datos: X lateral · Y altura · Z profundidad
            const camaras = {
                superior: { eye: { x: 0,   y: 2.2, z: 0.05 }, up: { x: 0, y: 0, z: -1 } },
                frontal:  { eye: { x: 0,   y: 0.2, z: 2.2  }, up: { x: 0, y: 1, z: 0  } },
                lateral:  { eye: { x: 2.2, y: 0.2, z: 0    }, up: { x: 0, y: 1, z: 0  } },
                libre:    { eye: { x: 1.5, y: 1.5, z: 1.5  } },
            };
            const cam = camaras[preset];
            if (cam) Plotly.relayout(el, { 'scene.camera': cam });
        },


        // =============================================================
        // TRAYECTORIA FANTASMA (otra sesión superpuesta en el 3D)
        // =============================================================

        async cargarCandidatosFantasma() {
            this.cargandoFantasma = true;
            this.mensajeError = '';
            const manoLabel = this.juegoSeleccionado?.hand_label || this.manoTextoBBT(this.dd?.hand);
            try {
                const listas = await Promise.all((this.sesiones || []).map(async s => {
                    if (s.SessionID === this.sesionSeleccionada?.SessionID) return [];
                    let games = s.isCSV ? (s.games || []) : null;
                    if (!games) {
                        const data = await fetch(`${API_BASE}/api/sessions/${s.SessionID}/games`).then(r => r.json());
                        games = data.games || [];
                    }
                    const g = games.find(j => j.game_type === 'bbt' && j.hand_label === manoLabel);
                    return g ? [{ label: this.formatearFecha(g.session_date || s.Date), juego: g }] : [];
                }));
                this.fantasmaCandidatos = listas.flat();
            } catch (e) {
                this.mensajeError = `Error buscando otras sesiones: ${e.message}`;
            } finally {
                this.cargandoFantasma = false;
                this.fantasmaBuscado = true;
            }
        },

        async seleccionarFantasma() {
            const cand = this.fantasmaCandidatos[this.fantasmaSel];
            if (!cand) return;
            this.mensajeError = '';
            try {
                const res  = await fetch(this._urlBBT(cand.juego));
                const data = await res.json();
                if (data.error) throw new Error(data.error);
                this.ddFantasma    = data;
                this.fantasmaLabel = cand.label;
                // reencuadrar los ejes para que quepan ambas trayectorias
                this.layoutFijo = inicializarGrafico3D('plot3d', this.dd, this.ddFantasma);
                this.actualizarGrafica3D();
            } catch (e) {
                this.mensajeError = `Error cargando la sesión fantasma: ${e.message}`;
            }
        },

        quitarFantasma() {
            this.ddFantasma    = null;
            this.fantasmaLabel = '';
            this.fantasmaSel   = '';
            this.layoutFijo = inicializarGrafico3D('plot3d', this.dd);
            this.actualizarGrafica3D();
        },

        _resetFantasma() {
            this.ddFantasma         = null;
            this.fantasmaLabel      = '';
            this.fantasmaCandidatos = [];
            this.fantasmaSel        = '';
            this.fantasmaBuscado    = false;
        },


        // =============================================================
        // PANTALLA COMPLETA
        // =============================================================

        pantallaCompleta3D() {
            const el = document.getElementById('plot3d');
            if (!el) return;
            const req = el.requestFullscreen || el.webkitRequestFullscreen || el.mozRequestFullScreen;
            if (req) req.call(el);
        },


        // =============================================================
        // HEATMAP
        // =============================================================

        toggleHeatmap() {
            this.mostrarHeatmap = !this.mostrarHeatmap;
            if (this.mostrarHeatmap && this.dd) {
                nextTick(() => renderizarHeatmap('plotHeatmap', this.dd, this.planoHeatmap, this.agarreSeleccionado));
            }
        },

        // Cambia el plano de proyección del heatmap (planta/frontal/perfil) y re-renderiza
        cambiarPlanoHeatmap(plano) {
            this.planoHeatmap = plano;
            if (this.mostrarHeatmap && this.dd) {
                renderizarHeatmap('plotHeatmap', this.dd, this.planoHeatmap, this.agarreSeleccionado);
            }
        },


        // =============================================================
        // GRÁFICO 3D (wrapper)
        // =============================================================

        actualizarGrafica3D() {
            if (!this.webglDisponible) return;
            actualizarGrafico3D('plot3d', this.dd, this.rangoInicio, this.currentIndex, this.layoutFijo, this.agarreSeleccionado, this.ddFantasma);
        },


        // =============================================================
        // EXPORTACIÓN PDF
        // =============================================================

        abrirModalPDF() {
            const secciones = [];

            if (this.vista === 'dashboard' && this.dd?.game_type === 'bbt') {
                secciones.push(
                    { id: 'ficha',          label: 'Ficha del paciente', checked: true,  disponible: true },
                    { id: 'metricas',       label: 'Métricas biomecánicas', checked: true,  disponible: !!this.dd?.metricas },
                    { id: 'trayectoria',    label: 'Trayectoria 3D', checked: this.webglDisponible, disponible: this.webglDisponible },
                    { id: 'penalizaciones', label: 'Penalizaciones BBT', checked: true,  disponible: !!this.dd?.penalizaciones },
                    { id: 'velocidad',      label: 'Perfil de velocidad', checked: false, disponible: true },
                    { id: 'scores',         label: 'Puntuación por frames', checked: false, disponible: true },
                    { id: 'anomalias',      label: 'Anomalías detectadas', checked: false, disponible: (this.anomaliasBBT?.length ?? 0) > 0 },
                    { id: 'vel_comparar',   label: 'Velocidad comparada', checked: false, disponible: !!this.ddVelocidadComparar },
                    { id: 'notas',          label: 'Notas clínicas', checked: false, disponible: true },
                );
            } else if (this.vista === 'comparar_manos') {
                secciones.push(
                    { id: 'ficha',             label: 'Ficha del paciente', checked: true,  disponible: true },
                    { id: 'comparacion_manos', label: 'Comparación D / I', checked: true,  disponible: true },
                    { id: 'notas',             label: 'Notas clínicas', checked: false, disponible: true },
                );
            } else if (this.vista === 'evolucion') {
                secciones.push(
                    { id: 'ficha',     label: 'Ficha del paciente', checked: true, disponible: true },
                    { id: 'evolucion', label: 'Evolución temporal', checked: true, disponible: !!this.evolucion },
                    { id: 'notas',     label: 'Notas clínicas', checked: false, disponible: true },
                );
            } else if (this.vista === 'dashboard' && this.dd?.game_type?.startsWith('fruits')) {
                secciones.push(
                    { id: 'ficha',           label: 'Ficha del paciente', checked: true, disponible: true },
                    { id: 'fruits_metrics',  label: 'Métricas Fruits', checked: true, disponible: !!this.dd?.hands },
                    { id: 'fruits_graficos', label: 'Gráficos Fruits', checked: true, disponible: true },
                    { id: 'notas',           label: 'Notas clínicas', checked: false, disponible: true },
                );
            }

            this.pdfSecciones    = secciones;
            this.pdfModalAbierto = true;
        },

        moverSeccionPDF(idx, dir) {
            const arr    = [...this.pdfSecciones];
            const newIdx = idx + dir;
            if (newIdx < 0 || newIdx >= arr.length) return;
            [arr[idx], arr[newIdx]] = [arr[newIdx], arr[idx]];
            this.pdfSecciones = arr;
        },

        async generarPDF() {
            if (this.pdfGenerando) return;
            const activas = this.pdfSecciones.filter(s => s.checked && s.disponible);
            if (!activas.length) return;

            this.pdfGenerando = true;
            try {
                const { jsPDF } = window.jspdf;
                const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
                const pW  = doc.internal.pageSize.getWidth();
                const pH  = doc.internal.pageSize.getHeight();
                const mg  = 15;
                const cW  = pW - mg * 2;

                // Paleta
                const ACCENT = [255, 158, 0];
                const DARK   = [30,  30,  30];
                const GRAY   = [100, 100, 100];

                // ── Helpers ──────────────────────────────────────────────
                let y = mg;

                const needPage = (needed) => {
                    if (y + needed > pH - mg - 12) { doc.addPage(); y = mg; }
                };

                const sectionTitle = (title) => {
                    needPage(12);
                    doc.setFillColor(...ACCENT);
                    doc.roundedRect(mg, y, cW, 9, 1.5, 1.5, 'F');
                    doc.setFontSize(10);
                    doc.setFont(undefined, 'bold');
                    doc.setTextColor(...DARK);
                    doc.text(title, mg + 4, y + 6.2);
                    y += 13;
                };

                const addPlotImage = async (elementId, imgW, imgH) => {
                    const el = document.getElementById(elementId);
                    if (!el) return;
                    try {
                        const imgData = await Plotly.toImage(el, { format: 'png', width: imgW, height: imgH, scale: 2 });
                        const mmH     = cW * imgH / imgW;
                        needPage(mmH + 5);
                        doc.addImage(imgData, 'PNG', mg, y, cW, mmH);
                        y += mmH + 6;
                    } catch (err) {
                        console.warn(`No se pudo capturar gráfico "${elementId}":`, err);
                    }
                };

                // ── PORTADA ───────────────────────────────────────────────
                doc.setFillColor(...ACCENT);
                doc.rect(0, 0, pW, 42, 'F');
                doc.setFontSize(24);
                doc.setFont(undefined, 'bold');
                doc.setTextColor(...DARK);
                doc.text('INFORME CLÍNICO', pW / 2, 22, { align: 'center' });
                doc.setFontSize(10);
                doc.setFont(undefined, 'normal');
                doc.text('Sistema de Rehabilitación Robótica', pW / 2, 32, { align: 'center' });

                y = 55;
                const pac          = this.pacienteSeleccionado;
                const dd           = this.dd;
                const pacNombre    = dd?.patient
                                  || (pac?.source === 'csv' ? pac.name : (pac ? `Paciente #${pac.UserID}` : 'N/D'));
                const manoLabel    = dd?.game_type === 'bbt'
                                  ? this.manoTextoBBT(dd.hand)
                                  : (dd?.hands
                                      ? this.clavesManos.map(k => this.manoTitulo(k).replace(/^[→←↔ ]+/, '')).join(' + ')
                                      : '—');

                doc.autoTable({
                    startY: y,
                    margin: { left: mg, right: mg },
                    head: [['Campo', 'Valor']],
                    body: [
                        ['Paciente',        pacNombre],
                        ['Fecha sesión',    dd?.date || this.formatearFecha(this.sesionSeleccionada?.Date) || '—'],
                        ['Entorno',         dd?.is_vr ? 'Realidad Virtual (Meta Quest)' : 'Desktop'],
                        ['Tipo de prueba',  dd?.task_name || dd?.game_type?.toUpperCase() || '—'],
                        ['Mano evaluada',   manoLabel],
                        ['Fecha informe',   new Date().toLocaleDateString('es-ES', { year: 'numeric', month: 'long', day: 'numeric' })],
                    ],
                    styles:           { fontSize: 10, cellPadding: 4 },
                    headStyles:       { fillColor: ACCENT, textColor: DARK, fontStyle: 'bold' },
                    alternateRowStyles: { fillColor: [248, 248, 248] },
                    columnStyles:     { 0: { fontStyle: 'bold', cellWidth: 50 } },
                });
                y = doc.lastAutoTable.finalY + 10;

                // ── SECCIONES ─────────────────────────────────────────────
                for (const sec of activas) {
                    if (sec.id === 'ficha') continue; // ya está en portada

                    doc.addPage();
                    y = mg;

                    // --- Métricas BBT ---
                    if (sec.id === 'metricas' && dd?.metricas) {
                        sectionTitle('Métricas Biomecánicas');
                        const m = dd.metricas;
                        doc.autoTable({
                            startY: y, margin: { left: mg, right: mg },
                            head: [['Métrica', 'Valor', 'Unidad']],
                            body: [
                                ['Trayectoria total',  m.distancia_m,          'm'  ],
                                ['Velocidad media',    m.velocidad_media_ms,    'm/s'],
                                ['Velocidad pico',     m.velocidad_pico_ms,     'm/s'],
                                ['T. Alcance',         m.tiempo_alcance_s,      's'  ],
                                ['T. Transporte',      m.tiempo_transporte_s,   's'  ],
                                ['Transiciones',       m.num_transiciones,      ''   ],
                                ['Ratio eficiencia',   m.ratio_eficiencia_pct,  '%'  ],
                            ],
                            styles:           { fontSize: 10, cellPadding: 4 },
                            headStyles:       { fillColor: ACCENT, textColor: DARK, fontStyle: 'bold' },
                            alternateRowStyles: { fillColor: [248, 248, 248] },
                            columnStyles:     { 1: { halign: 'left', fontStyle: 'bold' }, 2: { halign: 'left', textColor: GRAY, cellWidth: 15 } },
                        });
                        y = doc.lastAutoTable.finalY + 8;

                        if (dd.indice_fatiga) {
                            const f = dd.indice_fatiga;
                            sectionTitle('Índice de Fatiga');
                            doc.autoTable({
                                startY: y, margin: { left: mg, right: mg },
                                body: [
                                    ['Vel. primeros agarres', `${f.velocidad_primeros_ms} m/s`],
                                    ['Vel. últimos agarres',  `${f.velocidad_ultimos_ms} m/s`],
                                    ['Cambio',                `${f.cambio_pct > 0 ? '+' : ''}${f.cambio_pct}%`],
                                    ['Fatiga detectada',       f.fatiga_detectada ? 'SÍ' : 'No'],
                                ],
                                styles:           { fontSize: 10, cellPadding: 4 },
                                alternateRowStyles: { fillColor: [248, 248, 248] },
                                columnStyles:     { 0: { fontStyle: 'bold', cellWidth: 60 } },
                            });
                            y = doc.lastAutoTable.finalY + 8;
                        }
                    }

                    // --- Trayectoria 3D ---
                    else if (sec.id === 'trayectoria') {
                        sectionTitle('Trayectoria 3D');
                        // El plot puede estar vacío (o a medio reproducir) si no se ha entrado a
                        // Reproducción 3D: renderizar la trayectoria completa para la captura
                        if (this.webglDisponible && dd?.x?.length) {
                            actualizarGrafico3D('plot3d', dd, 0, this.maxIndexGlobal, this.layoutFijo, null);
                        }
                        await addPlotImage('plot3d', 800, 520);
                        // Restaurar el estado de reproducción que tenía el clínico
                        if (this.webglDisponible && dd?.x?.length) this.actualizarGrafica3D();

                        // Leyenda de colores
                        const leyenda = [
                            { rgb: [79,  172, 254], label: 'Alcance (mano vacia)'     },
                            { rgb: [255, 158,   0], label: 'Transporte (con objeto)'  },
                            { rgb: [255,   0,  85], label: 'Posicion actual'           },
                            { rgb: [74,  222, 128], label: 'Posicion de agarre'        },
                        ];
                        needPage(12);
                        const itemW  = cW / leyenda.length;
                        const sqSize = 4;
                        const leyY   = y;
                        leyenda.forEach((item, i) => {
                            const xBase = mg + i * itemW;
                            doc.setFillColor(...item.rgb);
                            doc.roundedRect(xBase, leyY, sqSize, sqSize, 1, 1, 'F');
                            doc.setFontSize(8);
                            doc.setFont(undefined, 'normal');
                            doc.setTextColor(...DARK);
                            doc.text(item.label, xBase + sqSize + 2, leyY + sqSize - 0.5);
                        });
                        y += sqSize + 6;
                    }

                    // --- Perfil de velocidad ---
                    else if (sec.id === 'velocidad') {
                        sectionTitle('Perfil de Velocidad');
                        await addPlotImage('plotVelocidad', 900, 380);
                    }

                    // --- Scores por frame ---
                    else if (sec.id === 'scores') {
                        sectionTitle('Puntuación por Frames');
                        await addPlotImage('plotScores', 900, 350);
                    }

                    // --- Penalizaciones ---
                    else if (sec.id === 'penalizaciones' && dd?.penalizaciones) {
                        sectionTitle('Penalizaciones BBT');
                        const pen = dd.penalizaciones;
                        doc.autoTable({
                            startY: y, margin: { left: mg, right: mg },
                            head: [['Tipo', 'Valor', 'Descripción']],
                            body: [
                                ['Completados',   pen.completed,   'Cubos transportados con éxito'  ],
                                ['No válidos',    pen.no_valid,    'Agarres sin transporte exitoso' ],
                                ['Fuera de zona', pen.out_of_zone, 'Mano fuera del área válida'     ],
                            ],
                            styles:           { fontSize: 10, cellPadding: 5 },
                            headStyles:       { fillColor: ACCENT, textColor: DARK, fontStyle: 'bold' },
                            alternateRowStyles: { fillColor: [248, 248, 248] },
                            columnStyles:     { 1: { halign: 'right', fontStyle: 'bold', cellWidth: 20 } },
                        });
                        y = doc.lastAutoTable.finalY + 8;
                    }

                    // --- Anomalías ---
                    else if (sec.id === 'anomalias' && this.anomaliasBBT?.length) {
                        sectionTitle('Anomalías Detectadas');
                        doc.autoTable({
                            startY: y, margin: { left: mg, right: mg },
                            head: [['#', 'Frame ini', 'Frame fin', 'Duración', 'Score', 'T. ini (s)', 'T. fin (s)']],
                            body: this.anomaliasBBT.map(a => [
                                a.num, a.frame_inicio, a.frame_fin,
                                `${a.duracion_frames}f`, a.score,
                                a.tiempo_inicio_s ?? '—', a.tiempo_fin_s ?? '—',
                            ]),
                            styles:           { fontSize: 9, cellPadding: 3 },
                            headStyles:       { fillColor: ACCENT, textColor: DARK, fontStyle: 'bold' },
                            alternateRowStyles: { fillColor: [248, 248, 248] },
                        });
                        y = doc.lastAutoTable.finalY + 8;
                    }

                    // --- Velocidad comparada ---
                    else if (sec.id === 'vel_comparar' && this.ddVelocidadComparar) {
                        sectionTitle('Velocidad Comparada — D vs I');
                        await addPlotImage('plotVelocidadComparacion', 900, 400);
                    }

                    // --- Comparación de manos ---
                    else if (sec.id === 'comparacion_manos' && this.ddComparacionManos) {
                        sectionTitle('Comparación de Manos — Derecha vs Izquierda');
                        const mD  = this.ddComparacionManos.derecha?.metricas        || {};
                        const mI  = this.ddComparacionManos.izquierda?.metricas      || {};
                        const pD  = this.ddComparacionManos.derecha?.penalizaciones  || {};
                        const pI  = this.ddComparacionManos.izquierda?.penalizaciones || {};
                        doc.autoTable({
                            startY: y, margin: { left: mg, right: mg },
                            head: [['Métrica', 'Derecha', 'Izquierda']],
                            body: [
                                ['Trayectoria (m)',    mD.distancia_m           ?? '—', mI.distancia_m           ?? '—'],
                                ['Vel. media (m/s)',   mD.velocidad_media_ms    ?? '—', mI.velocidad_media_ms    ?? '—'],
                                ['Vel. pico (m/s)',    mD.velocidad_pico_ms     ?? '—', mI.velocidad_pico_ms     ?? '—'],
                                ['T. Alcance (s)',     mD.tiempo_alcance_s      ?? '—', mI.tiempo_alcance_s      ?? '—'],
                                ['T. Transporte (s)', mD.tiempo_transporte_s   ?? '—', mI.tiempo_transporte_s   ?? '—'],
                                ['Transiciones',      mD.num_transiciones      ?? '—', mI.num_transiciones      ?? '—'],
                                ['Eficiencia (%)',    mD.ratio_eficiencia_pct  ?? '—', mI.ratio_eficiencia_pct  ?? '—'],
                                ['Completados',       pD.completed             ?? '—', pI.completed             ?? '—'],
                                ['No válidos',        pD.no_valid              ?? '—', pI.no_valid              ?? '—'],
                                ['Fuera de zona',     pD.out_of_zone           ?? '—', pI.out_of_zone           ?? '—'],
                            ],
                            styles:           { fontSize: 10, cellPadding: 4 },
                            headStyles:       { fillColor: ACCENT, textColor: DARK, fontStyle: 'bold' },
                            alternateRowStyles: { fillColor: [248, 248, 248] },
                            columnStyles: {
                                0: { fontStyle: 'bold', cellWidth: 55 },
                                1: { halign: 'right' },
                                2: { halign: 'right' },
                            },
                        });
                        y = doc.lastAutoTable.finalY + 8;
                    }

                    // --- Evolución temporal BBT ---
                    else if (sec.id === 'evolucion' && this.evolucion) {
                        sectionTitle('Evolución Temporal BBT');
                        await addPlotImage('plotEvolucion', 900, 440);
                    }

                    // --- Métricas Fruits ---
                    else if (sec.id === 'fruits_metrics' && dd?.hands) {
                        sectionTitle('Métricas Fruits');
                        for (const [hand, hdata] of Object.entries(dd.hands)) {
                            const m = hdata?.metricas || {};
                            needPage(8);
                            doc.setFontSize(10);
                            doc.setFont(undefined, 'bold');
                            doc.setTextColor(...GRAY);
                            doc.text(`Mano: ${hand}`, mg, y);
                            y += 5;
                            doc.autoTable({
                                startY: y, margin: { left: mg, right: mg },
                                body: Object.entries(m).map(([k, v]) => [k, v]),
                                styles:           { fontSize: 9, cellPadding: 3 },
                                alternateRowStyles: { fillColor: [248, 248, 248] },
                                columnStyles:     { 0: { fontStyle: 'bold', cellWidth: 80 } },
                            });
                            y = doc.lastAutoTable.finalY + 6;
                        }
                    }

                    // --- Gráficos Fruits ---
                    else if (sec.id === 'fruits_graficos') {
                        sectionTitle('Gráficos Fruits');
                        await addPlotImage('plotFruitsComparacion', 900, 380);
                        await addPlotImage('plotFruitsTimes', 900, 380);
                        await addPlotImage('plotFruitsAsimetria', 900, 380);
                        if (dd?.game_type === 'fruits_race') {
                            await addPlotImage('plotRaceScatter', 900, 420);
                        }
                    }

                    // --- Notas clínicas ---
                    else if (sec.id === 'notas') {
                        sectionTitle('Notas Clínicas');
                        doc.setFontSize(10);
                        doc.setFont(undefined, 'normal');
                        doc.setTextColor(...DARK);
                        const notas = this.pdfNotas?.trim() || '(Sin observaciones registradas)';
                        const lines = doc.splitTextToSize(notas, cW);
                        needPage(lines.length * 5 + 4);
                        doc.text(lines, mg, y);
                        y += lines.length * 5 + 6;
                    }
                }

                // ── PIE DE PÁGINA en todas las páginas ───────────────────
                const totalPages = doc.internal.getNumberOfPages();
                for (let pg = 1; pg <= totalPages; pg++) {
                    doc.setPage(pg);
                    doc.setFontSize(8);
                    doc.setFont(undefined, 'normal');
                    doc.setTextColor(...GRAY);
                    doc.setDrawColor(...GRAY);
                    doc.line(mg, pH - 12, pW - mg, pH - 12);
                    doc.text('Sistema de Rehabilitación Robótica — UC3M', mg, pH - 7);
                    doc.text(`Página ${pg} / ${totalPages}`, pW - mg, pH - 7, { align: 'right' });
                }

                // ── GUARDAR ──────────────────────────────────────────────
                const nombreFichero = (pac?.name || dd?.patient || 'informe').replace(/\s+/g, '_');
                const fechaHoy      = new Date().toISOString().slice(0, 10);
                doc.save(`informe_${nombreFichero}_${fechaHoy}.pdf`);

                this.pdfModalAbierto = false;

            } catch (err) {
                this.mensajeError = `Error al generar PDF: ${err.message}`;
                console.error('PDF generation error:', err);
            } finally {
                this.pdfGenerando = false;
            }
        },
    },

    mounted() {
        this._aplicarTema();          // restaura el tema guardado antes de pintar
        this.webglDisponible = this._detectarWebGL();
        this.cargarPacientes();
    },

    beforeUnmount() {
        this.pausar();
    }

}).mount('#app');
