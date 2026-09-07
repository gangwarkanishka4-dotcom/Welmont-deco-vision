/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          950: '#0a0d12',
          900: '#0f1319',
          850: '#131822',
          800: '#161c28',
          700: '#1e2635',
          600: '#2a3446',
          500: '#3d4a61',
        },
        accent: {
          400: '#4d9fff',
          500: '#2f7fff',
          600: '#1c63e0',
        },
        status: {
          supervised: '#22c55e',
          waiting: '#f59e0b',
          unsupervised: '#ef4444',
          empty: '#64748b',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        panel: '0 1px 0 0 rgba(255,255,255,0.04) inset, 0 1px 3px rgba(0,0,0,0.4)',
      },
      keyframes: {
        pulseRing: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.35' },
        },
        slideIn: {
          '0%': { transform: 'translateX(24px)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
      },
      animation: {
        'pulse-ring': 'pulseRing 1.6s ease-in-out infinite',
        'slide-in': 'slideIn 0.2s ease-out',
      },
    },
  },
  plugins: [],
};
