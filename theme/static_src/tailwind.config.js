/**
 * Build with `npm run build` in this directory. The compiled stylesheet (static/css/tailwind.css) is
 * committed, so deployments do not need Node.
 */
module.exports = {
    content: [
        '../../templates/**/*.html',
        '../../**/templates/**/*.html',
        '../../static/js/**/*.js',
        '!../../**/node_modules/**',
    ],
    theme: {
        extend: {
            colors: {
                primary: {
                    50: '#f0fdf4', 100: '#dcfce7', 200: '#bbf7d0', 300: '#86efac', 400: '#4ade80',
                    500: '#22c55e', 600: '#16a34a', 700: '#15803d', 800: '#166534', 900: '#14532d', 950: '#052e16',
                },
            },
            fontFamily: {
                sans: ['Inter', 'Noto Sans Tamil', 'Noto Sans Devanagari', 'Noto Naskh Arabic', 'system-ui', 'sans-serif'],
            },
        },
    },
    plugins: [require('@tailwindcss/forms'), require('@tailwindcss/typography'), require('@tailwindcss/aspect-ratio')],
}
