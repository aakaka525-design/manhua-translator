<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  original: String,
  translated: String,
  active: Boolean
})

const sliderVal = ref(50)
const container = ref(null)
const isDragging = ref(false)

function onStart(e) {
  if (!props.active) return
  isDragging.value = true
  // Prevent scrolling while sliding
  e.preventDefault() 
}

function onEnd() {
  isDragging.value = false
}

function onMove(e) {
  if (!isDragging.value || !props.active) return
  
  const rect = container.value.getBoundingClientRect()
  const clientX = e.touches ? e.touches[0].clientX : e.clientX
  
  const percentage = ((clientX - rect.left) / rect.width) * 100
  sliderVal.value = Math.max(0, Math.min(100, percentage))
}

onUnmounted(() => {
  window.removeEventListener('mouseup', onEnd)
  window.removeEventListener('touchend', onEnd)
  window.removeEventListener('mousemove', onMove)
  window.removeEventListener('touchmove', onMove)
  if (observer) observer.disconnect()
})

// Lazy Loading Logic
const isVisible = ref(false)
let observer = null

onMounted(() => {
  // Global event listeners
  window.addEventListener('mouseup', onEnd)
  window.addEventListener('touchend', onEnd)
  window.addEventListener('mousemove', onMove)
  window.addEventListener('touchmove', onMove, { passive: false })

  // Observer
  if (!window.IntersectionObserver) {
    isVisible.value = true
    return
  }
  
  observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting) {
      isVisible.value = true
      observer.disconnect()
    }
  }, { rootMargin: '50% 0px' })
  
  if (container.value) {
    observer.observe(container.value)
  }
})
</script>

<template>
  <div 
    ref="container"
    class="relative w-full overflow-hidden select-none touch-none"
    @mousedown="onStart"
    @touchstart="onStart"
  >
    <!-- Translated Image (Background) -->
    <div v-if="!isVisible" class="w-full pb-[140%] bg-bg-secondary/30 animate-pulse"></div>
    <img 
      v-if="isVisible"
      :src="translated" 
      class="w-full h-auto block" 
      draggable="false"
    />
    
    <!-- Original Image (Clipped Overlay) -->
    <div 
      v-if="active"
      class="absolute inset-0 overflow-hidden"
      :style="{ width: sliderVal + '%' }"
    >
      <img 
        :src="original" 
        class="absolute top-0 left-0 max-w-none h-full" 
        :style="{ width: container ? container.clientWidth + 'px' : '100%' }"
        draggable="false"
      />
      
      <!-- Slider Handle line -->
      <div class="absolute top-0 right-0 w-1 h-full bg-accent-2 shadow-[0_0_10px_theme('colors.accent-2')]"></div>
    </div>
    
    <!-- Handle Button -->
    <div 
      v-if="active"
      class="absolute top-1/2 -translate-y-1/2 w-8 h-8 bg-accent-2 rounded-full flex items-center justify-center shadow-lg -mr-4 cursor-ew-resize z-10"
      :style="{ left: sliderVal + '%' }"
    >
      <i class="fas fa-arrows-alt-h text-black text-xs"></i>
    </div>
  </div>
</template>
