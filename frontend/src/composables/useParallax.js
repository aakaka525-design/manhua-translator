import { onMounted } from 'vue'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

export function useParallax() {
    onMounted(() => {
        gsap.registerPlugin(ScrollTrigger)

        // Parallax background effect
        // Assumes '.halftone-bg' class exists
        gsap.to('.halftone-bg', {
            backgroundPosition: '0px 100px',
            ease: 'none',
            scrollTrigger: {
                trigger: 'body',
                start: 'top top',
                end: 'bottom bottom',
                scrub: true
            }
        })

        // Fade in elements with class .gsap-fade-up
        const fadeElements = document.querySelectorAll('.gsap-fade-up')
        fadeElements.forEach(el => {
            gsap.fromTo(el,
                { opacity: 0, y: 30 },
                {
                    opacity: 1,
                    y: 0,
                    duration: 0.8,
                    ease: 'power2.out',
                    scrollTrigger: {
                        trigger: el,
                        start: 'top 90%',
                    }
                }
            )
        })
    })
}
