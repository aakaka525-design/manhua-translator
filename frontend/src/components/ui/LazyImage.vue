<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  src: String,
  alt: {
    type: String,
    default: ''
  },
  threshold: {
    type: Number,
    default: 0.1
  }
})

const imgRef = ref(null)
const isVisible = ref(false)
const isLoaded = ref(false)
const error = ref(false)

let observer = null

onMounted(() => {
  if (!window.IntersectionObserver) {
    isVisible.value = true
    return
  }

  observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting) {
      isVisible.value = true
      observer.disconnect()
    }
  }, {
    rootMargin: '50% 0px', // Load when within 50% viewport height
    threshold: props.threshold
  })

  if (imgRef.value) {
    observer.observe(imgRef.value)
  }

  const imgEl = imgRef.value?.querySelector('img')
  if (imgEl && imgEl.complete) {
    isVisible.value = true
    isLoaded.value = true
  }
})

onUnmounted(() => {
  if (observer) observer.disconnect()
})

const onLoad = () => {
  isLoaded.value = true
}

const onError = () => {
  error.value = true
}
</script>

<template>
  <div ref="imgRef" class="relative overflow-hidden bg-bg-secondary/30 min-h-[200px] flex items-center justify-center">
    <!-- Placeholder / Skeleton -->
    <div v-if="!isLoaded && !error" class="absolute inset-0 animate-pulse bg-bg-secondary/50">
        <div class="h-full w-full flex items-center justify-center">
            <i class="fas fa-image text-4xl text-text-secondary/20"></i>
        </div>
    </div>

    <!-- Error State -->
    <div v-if="error" class="absolute inset-0 flex flex-col items-center justify-center text-text-secondary">
        <i class="fas fa-exclamation-triangle text-2xl mb-2 text-state-error/50"></i>
        <span class="text-xs">加载失败</span>
    </div>

    <!-- Image -->
    <img 
      v-if="isVisible"
      :src="src" 
      :alt="alt"
      class="w-full h-auto transition-opacity duration-300 block"
      :class="isLoaded ? 'opacity-100' : 'opacity-0'"
      @load="onLoad"
      @error="onError"
      @loadstart="() => { if (isLoaded) isLoaded = false }"
    />
  </div>
</template>
