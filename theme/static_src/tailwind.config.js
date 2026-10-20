/**
 * Build with `npm run build` in this directory. The compiled stylesheet (static/css/tailwind.css) is
 * committed, so deployments do not need Node.
 *
 * Theme: every colour utility the templates already use (gray-*, slate-*, green-*, red-*, ...) is mapped to a CSS
 * variable, and html.dark swaps the variables. That makes the whole app light/dark aware without editing each
 * template. Light values are Tailwind's own palette, so pages that never set `dark` look exactly as before.
 */
const colors = require('tailwindcss/colors');
const plugin = require('tailwindcss/plugin');

const STEPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];
const NEUTRAL = ['gray', 'slate'];
const HUES = ['red', 'orange', 'amber', 'yellow', 'green', 'emerald', 'teal', 'sky', 'blue', 'indigo', 'purple', 'fuchsia', 'pink', 'rose'];

// Dark mode: only the tints (50-300: backgrounds, borders) are mirrored. Saturated shades (400-950) keep their value so
// solid buttons and gradient cards stay saturated; text-* utilities are lightened explicitly (see TEXT_DARK below).
const MIRROR = { 50: 950, 100: 900, 200: 800, 300: 700 };
const mirrored = (s) => MIRROR[s] || s;
const TEXT_DARK = { 600: 400, 700: 300, 800: 200, 900: 100 };                 // hues
const TEXT_DARK_NEUTRAL = { 400: 500, 500: 400, 600: 300, 700: 200, 800: 100, 900: 50 };
const BG_DARK_NEUTRAL = { 700: 600, 800: 700, 900: 700 };                     // dark solid backgrounds stay visible on dark cards

const rgb = (hex) => {
    const n = parseInt(hex.slice(1), 16);
    return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
};

const scales = {};          // tailwind colour config
const light = {};           // :root variables
const dark = {};            // .dark variables
const darkRules = {};       // html.dark .text-gray-500 { ... }
const add = (name, source, textMap, bgMap) => {
    scales[name] = {};
    STEPS.forEach((s) => {
        const v = `--c-${name}-${s}`;
        light[v] = rgb(colors[source][s]);
        if (MIRROR[s]) dark[v] = rgb(colors[source][mirrored(s)]);
        scales[name][s] = `rgb(var(${v}) / <alpha-value>)`;
        if (textMap[s]) darkRules[`html.dark .text-${name}-${s}`] = { color: `rgb(${rgb(colors[source][textMap[s]])})` };
        if (bgMap[s]) darkRules[`html.dark .bg-${name}-${s}`] = { 'background-color': `rgb(${rgb(colors[source][bgMap[s]])})` };
    });
};
NEUTRAL.forEach((h) => add(h, h, TEXT_DARK_NEUTRAL, BG_DARK_NEUTRAL));
HUES.forEach((h) => add(h, h, TEXT_DARK, {}));
// brand: same green scale as `green`, under the name the templates use
add('primary', 'green', TEXT_DARK, {});

// surfaces (shadcn-style semantic tokens)
Object.assign(light, { '--surface': '255 255 255', '--page': rgb(colors.gray[50]), '--overlay': '15 23 42' });
Object.assign(dark, { '--surface': rgb(colors.gray[900]), '--page': rgb('#0b1018'), '--overlay': '0 0 0' });
// dark ladder (page < surface < 50 < 100 < border-200 < border-300): keeps hover, input and border levels distinct
['gray', 'slate'].forEach((h) => {
    dark[`--c-${h}-50`] = '22 30 46';
    dark[`--c-${h}-100`] = '28 38 56';
    dark[`--c-${h}-200`] = '40 51 70';
});
// translucent white surfaces (glass bars): only the high opacities, not decorative bg-white/10 overlays
['70', '75', '80', '85', '90', '95'].forEach((o) => { darkRules[`html.dark .bg-white\\/${o}`] = { 'background-color': 'rgb(var(--surface) / 0.85)' }; });
// light tint text (text-green-100 ...) sits on saturated backgrounds: keep it light in dark mode
HUES.concat('primary').forEach((h) => [50, 100, 200, 300].forEach((s) => {
    const src = h === 'primary' ? 'green' : h;
    darkRules[`html.dark .text-${h}-${s}`] = { color: `rgb(${rgb(colors[src][s])})` };
}));

module.exports = {
    darkMode: 'class',
    content: [
        '../../templates/**/*.html',
        '../../**/templates/**/*.html',
        '../../static/js/**/*.js',
        '!../../**/node_modules/**',
    ],
    theme: {
        extend: {
            // @tailwindcss/aspect-ratio replaces the aspect-ratio scale with numbers; keep the named utilities too
            aspectRatio: { auto: 'auto', square: '1 / 1', video: '16 / 9' },
            colors: {
                ...scales,
                surface: 'rgb(var(--surface) / <alpha-value>)',
                page: 'rgb(var(--page) / <alpha-value>)',
            },
            fontFamily: {
                sans: ['Inter', 'Noto Sans Tamil', 'Noto Sans Devanagari', 'Noto Sans Telugu', 'Noto Sans Malayalam', 'Noto Sans Kannada', 'system-ui', 'sans-serif'],
            },
            borderRadius: { xl: '0.75rem', '2xl': '1rem' },
            boxShadow: {
                card: '0 1px 2px 0 rgb(0 0 0 / 0.04), 0 1px 3px 0 rgb(0 0 0 / 0.06)',
                pop: '0 10px 30px -10px rgb(0 0 0 / 0.25), 0 2px 8px -2px rgb(0 0 0 / 0.1)',
            },
            keyframes: {
                'ui-in': { from: { opacity: 0, transform: 'translateY(-4px) scale(.98)' }, to: { opacity: 1, transform: 'none' } },
            },
            animation: { 'ui-in': 'ui-in .14s ease-out' },
        },
    },
    plugins: [
        require('@tailwindcss/forms'),
        require('@tailwindcss/typography'),
        require('@tailwindcss/aspect-ratio'),
        plugin(({ addBase }) => addBase({ ':root': light, 'html.dark': { ...dark, 'color-scheme': 'dark' }, ...darkRules })),
    ],
};
