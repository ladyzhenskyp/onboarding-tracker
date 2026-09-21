// Tailwind is compiled ahead of time into app/static/vendor/tailwind.css
// (run: python scripts/build_css.py), so the app loads no script from a CDN.
// Colours mirror the CSS variables in app/static/app.css. Corners are square by design.
module.exports = {
  content: ['./app/templates/**/*.html', './app/static/app.js'],
  theme: {
    borderRadius: { none: '0', sm: '0', DEFAULT: '0', md: '0', lg: '0', xl: '0', '2xl': '0', full: '9999px' },
    extend: {
      colors: {
        page: '#f6f7fb', surface: '#ffffff', mint: '#ecebfb', chip: '#eff0f6',
        line: { DEFAULT: '#e5e7f0', soft: '#eff0f6', strong: '#cdd0de' },
        ink: { DEFAULT: '#1c2033', 2: '#5a6078', 3: '#9095ab' },
        brand: { DEFAULT: '#453fb0', dark: '#3a3499', soft: '#ecebfb' },
        health: { red: '#b4534b', redsoft: '#fdf1f0', redfill: '#ea9a93', amber: '#96703a', ambersoft: '#fdf6e7', amberfill: '#ecc47e', green: '#3d8263', greensoft: '#edf7f1', greenfill: '#8fd0ae' },
        sev: { high: '#b0693a', highsoft: '#fdf1e8' },
      },
      fontFamily: { sans: ['Switzer', '-apple-system', 'Segoe UI', 'Helvetica', 'Arial', 'sans-serif'] },
    },
  },
}
