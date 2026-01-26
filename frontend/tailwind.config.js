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
                'surface': 'var(--bg-surface)',
                'accent-1': 'var(--accent-1)',
                'accent-2': 'var(--accent-2)',
                'text-main': 'var(--text-main)',
                'border-main': 'var(--border-color)',
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
