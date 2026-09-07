/* =============================================================================
   Configuración Global
   ============================================================================= */

/**
 * URL base de la API FastAPI.
 * - Servido por el backend (/app/) o Docker → mismo origen: usa location.origin,
 *   así funciona aunque otro equipo acceda por la IP del servidor.
 * - Abierto como archivo (file://) o dev con Live Server → fallback al backend local.
 */
const API_BASE = (location.protocol === 'http:' || location.protocol === 'https:')
    ? location.origin
    : 'http://127.0.0.1:8000';

/**
 * Configuración de Tailwind CSS.
 * Los colores referencian CSS variables definidas en styles.css,
 * permitiendo que cambien automáticamente con el tema.
 */
tailwind.config = {
    theme: {
        extend: {
            colors: {
                // Colores temáticos (cambian con dark/light)
                't-bg': 'var(--color-bg)',
                't-panel': 'var(--color-panel)',
                't-border': 'var(--color-border)',
                't-text': 'var(--color-text)',
                't-muted': 'var(--color-text-muted)',
                't-dimmed': 'var(--color-text-dimmed)',
                't-accent': 'var(--color-accent)',
                't-card': 'var(--color-card-bg)',
                't-card-border': 'var(--color-card-border)',
                't-input': 'var(--color-input-bg)',
                't-input-border': 'var(--color-input-border)',
                't-btn': 'var(--color-btn-secondary)',
                't-btn-hover': 'var(--color-btn-secondary-hover)',

                // Colores semánticos (cambian con el tema)
                't-blue':   'var(--color-sem-blue)',
                't-cyan':   'var(--color-sem-cyan)',
                't-green':  'var(--color-sem-green)',
                't-yellow': 'var(--color-sem-yellow)',
                't-purple': 'var(--color-sem-purple)',
                't-orange': 'var(--color-sem-orange)',
                't-red':    'var(--color-sem-red)',

                // Colores fijos de gráfico (no cambian)
                'transporte': '#ff9e00',
                'cursor3d': '#ff0055',
                'score': '#a78bfa',

                // alcance sí cambia con el tema
                'alcance': 'var(--color-alcance)',
            }
        }
    }
};
