/* ===========================================================================
 * Banco de medición en navegador — RNF-07 y RNF-08
 * ---------------------------------------------------------------------------
 * RNF-07  carga de la trayectoria 3D  < 3 s   y   reproducción > 20 fps
 * RNF-08  generación del informe PDF  < 10 s
 *
 * USO
 *   1. Arrancar el sistema y abrir un panel de BBT con trayectoria.
 *   2. Abrir la consola del navegador (F12) y pegar este fichero entero.
 *   3. Seguir las tres pruebas que indica. Repetir cada una 3-5 veces.
 *   4. Ejecutar  bench.informe()  para ver medianas y veredicto.
 * =========================================================================== */
(() => {
  // La instancia raíz se localiza probando varias rutas: en el build de
  // producción de Vue 3 (_instance) puede venir a null, así que se recorren
  // también el vnode del contenedor y los hijos montados.
  const METODOS = ['seleccionarJuego', 'siguientePunto', 'pausar', 'generarPDF'];
  const sirve = o => o && METODOS.every(m => typeof o[m] === 'function');

  function localizar() {
    const raices = [document.querySelector('#app'), document.body, document.documentElement];
    for (const el of raices) {
      if (!el) continue;
      const a = el.__vue_app__;
      const rutas = [
        a && a._instance && a._instance.proxy,
        a && a._container && a._container._vnode && a._container._vnode.component
          && a._container._vnode.component.proxy,
        el.__vueParentComponent && el.__vueParentComponent.proxy,
        el.__vue__,
      ];
      for (const c of rutas) if (sirve(c)) return c;
    }
    // último recurso: recorrer el DOM buscando cualquier nodo con componente
    for (const el of document.querySelectorAll('*')) {
      const c = el.__vueParentComponent;
      if (!c) continue;
      for (let x = c; x; x = x.parent) if (sirve(x.proxy)) return x.proxy;
    }
    return null;
  }

  const vm = localizar();
  if (!vm) {
    console.error('No localizo la instancia Vue con los métodos esperados.');
    const el = document.querySelector('#app');
    console.log('diagnóstico -> #app:', !!el,
                '| __vue_app__:', !!(el && el.__vue_app__),
                '| _instance:', el && el.__vue_app__ ? el.__vue_app__._instance : 'n/d',
                '| vista actual:', el ? el.getAttribute('data-vista') : 'n/d');
    console.log('Comprueba que estás en un panel de BBT ya cargado y vuelve a pegar el script.');
    return;
  }
  console.log('Instancia localizada. Vista actual:', vm.vista);

  const M = { carga: [], fps: [], pdf: [] };
  const mediana = a => { if (!a.length) return null;
    const s = [...a].sort((x, y) => x - y), m = s.length >> 1;
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

  // ---- RNF-07a: de la selección del juego a la trayectoria pintada ---------
  let t0 = null;
  const selOrig = vm.seleccionarJuego.bind(vm);
  vm.seleccionarJuego = async function (...a) {
    t0 = performance.now();
    const r = await selOrig(...a);
    // el 3D se pinta tras el nextTick de Vue; se mide al vaciarse la cola
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (t0 === null) return;
      const ms = performance.now() - t0; t0 = null;
      M.carga.push(ms);
      console.log(`[RNF-07 carga]  ${(ms / 1000).toFixed(2)} s`);
    }));
    return r;
  };

  // ---- RNF-07b: cadencia real de la reproducción --------------------------
  let ult = null, marcas = [];
  const sigOrig = vm.siguientePunto.bind(vm);
  vm.siguientePunto = function (...a) {
    const t = performance.now();
    if (ult !== null) marcas.push(t - ult);
    ult = t;
    return sigOrig(...a);
  };
  const pauOrig = vm.pausar.bind(vm);
  vm.pausar = function (...a) {
    if (marcas.length >= 10) {
      const dt = mediana(marcas);              // ms entre fotogramas
      const f  = 1000 / dt;
      M.fps.push(f);
      console.log(`[RNF-07 fps]    ${f.toFixed(1)} fps  (${marcas.length} fotogramas, mediana ${dt.toFixed(1)} ms)`);
    }
    marcas = []; ult = null;
    return pauOrig(...a);
  };

  // ---- RNF-08: informe PDF completo ---------------------------------------
  const pdfOrig = vm.generarPDF.bind(vm);
  vm.generarPDF = async function (...a) {
    const t = performance.now();
    const r = await pdfOrig(...a);
    const ms = performance.now() - t;
    M.pdf.push(ms);
    console.log(`[RNF-08 pdf]    ${(ms / 1000).toFixed(2)} s`);
    return r;
  };

  window.bench = {
    datos: M,
    informe() {
      const fila = (id, arr, unidad, umbral, mejorMayor) => {
        if (!arr.length) return `${id}: sin medidas`;
        const m = mediana(arr);
        const ok = mejorMayor ? m > umbral : m < umbral;
        return `${id}: mediana ${m.toFixed(mejorMayor ? 1 : 0)} ${unidad}` +
               `  (n=${arr.length}, min ${Math.min(...arr).toFixed(mejorMayor ? 1 : 0)},` +
               ` max ${Math.max(...arr).toFixed(mejorMayor ? 1 : 0)})  ->  ${ok ? 'CUMPLE' : 'NO CUMPLE'}`;
      };
      console.log('\n===== RNF-07 / RNF-08 =====');
      console.log(fila('Carga 3D   (<3000 ms)', M.carga, 'ms', 3000, false));
      console.log(fila('Reproducc. (>20 fps) ', M.fps, 'fps', 20, true));
      console.log(fila('Informe PDF(<10000 ms)', M.pdf, 'ms', 10000, false));
      console.log('\nEntorno:', navigator.userAgent);
      console.log('Núcleos:', navigator.hardwareConcurrency, '| memoria JS:',
                  performance.memory ? (performance.memory.jsHeapSizeLimit / 1048576).toFixed(0) + ' MB' : 'n/d');
    },
    reset() { M.carga = []; M.fps = []; M.pdf = []; console.log('medidas borradas'); }
  };

  console.log('%cBanco instalado.', 'font-weight:bold');
  console.log('1) CARGA 3D  : vuelve a la lista de juegos y abre otra vez el BBT. Repite 3-5 veces.');
  console.log('2) FPS       : pulsa Reproducir, deja correr ~10 s y pulsa Pausa. Repite 3 veces.');
  console.log('3) PDF       : genera el informe completo. Repite 3 veces.');
  console.log('Luego:  bench.informe()');
})();
