/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{vue,js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                'bg-primary': 'var(--bg-primary)',
                'bg-secondary': 'var(--bg-secondary)',
                'surface': 'var(--bg-surface)',
                'accent-1': 'var(--accent-1)',
                'accent-2': 'var(--accent-2)',
                'text-main': 'var(--text-main)',
                'text-secondary': 'var(--text-secondary)',
                'border-main': 'var(--border-color)',
                'border-subtle': 'var(--border-subtle)',
                'state-success': 'var(--state-success)',
                'state-warning': 'var(--state-warning)',
                'state-error': 'var(--state-error)',
            },
            fontFamily: {
                'heading': ['Bebas Neue', 'sans-serif'],
                'body': ['Inter', 'sans-serif'],
                'comic': ['Bangers', 'cursive'],
            },
            boxShadow: {
                'comic': '5px 5px 0px 0px var(--card-shadow-color)',
                'comic-hover': '7px 7px 0px 0px var(--card-shadow-hover)',
            },
            borderWidth: {
                'card': 'var(--card-border-width)',
            }
        },
    },
    plugins: [],
}
