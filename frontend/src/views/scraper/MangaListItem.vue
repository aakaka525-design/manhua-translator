<script setup>
import LazyImage from '@/components/ui/LazyImage.vue'

const props = defineProps({
  manga: {
    type: Object,
    required: true
  },
  isSelected: {
    type: Boolean,
    default: false
  },
  loading: {
    type: Boolean,
    default: false
  },
  actionLabel: {
    type: String,
    default: '查看章节'
  },
  disabled: {
    type: Boolean,
    default: false
  },
  cover: {
    type: String,
    default: ''
  },
  variant: {
    type: String,
    default: 'list',
    validator: (value) => ['list', 'grid'].includes(value)
  }
})

const emit = defineEmits(['select'])

function handleSelect() {
  if (props.disabled || props.loading) return
  emit('select', props.manga)
}
</script>

<template>
  <div v-if="variant === 'list'"
    class="flex items-center justify-between rounded-xl px-4 py-3 border transition group relative overflow-hidden"
    :class="isSelected 
      ? 'bg-accent-1/10 border-accent-1/60' 
      : 'bg-bg-secondary/30 border-border-subtle hover:border-accent-1/40 hover:bg-bg-secondary/60'"
  >
    <div class="flex items-center gap-4 overflow-hidden z-10">
      <div class="shrink-0 w-12 h-16 sm:w-16 sm:h-20 rounded-lg bg-bg-secondary border border-border-subtle overflow-hidden shadow-sm group-hover:shadow-md transition-all">
        <LazyImage 
          v-if="cover || manga.cover_url || manga.cover" 
          :src="cover || manga.cover_url || manga.cover" 
          alt="cover"
          class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
        />
        <div v-else class="w-full h-full flex items-center justify-center text-text-secondary/20">
          <i class="fas fa-image text-xl"></i>
        </div>
      </div>
      
      <div class="min-w-0">
        <p class="text-sm font-bold text-text-main truncate pr-2 group-hover:text-accent-1 transition-colors">
          {{ manga.title || manga.id }}
        </p>
        <p class="text-[11px] text-text-secondary truncate mt-0.5 font-mono opacity-60">
          {{ manga.url }}
        </p>
        <slot name="info"></slot>
      </div>
    </div>

    <div class="shrink-0 ml-2 z-10">
      <button 
        @click="handleSelect" 
        :disabled="disabled || loading"
        class="px-3 py-1.5 text-xs font-semibold rounded-full transition-all duration-300 transform active:scale-95 border"
        :class="(disabled || loading)
          ? 'opacity-60 cursor-not-allowed bg-bg-secondary text-text-secondary border-transparent' 
          : 'bg-bg-secondary/40 border-border-subtle text-text-main hover:text-accent-1 hover:border-accent-1 hover:shadow-md'"
      >
        {{ loading ? '...' : actionLabel }}
      </button>
    </div>
  </div>

  <div v-else
    class="group relative flex flex-col bg-bg-secondary/20 border border-border-subtle rounded-xl overflow-hidden hover:border-accent-1/50 transition-all duration-300 hover:shadow-lg hover:-translate-y-1 h-full cursor-pointer"
    :class="isSelected ? 'ring-2 ring-accent-1 border-transparent' : ''"
    @click="handleSelect"
  >
    <div class="aspect-[2/3] w-full relative overflow-hidden bg-bg-secondary/50">
      <LazyImage 
        v-if="cover || manga.cover_url || manga.cover" 
        :src="cover || manga.cover_url || manga.cover" 
        alt="cover"
        class="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110"
      />
      <div v-else class="w-full h-full flex items-center justify-center text-text-secondary/20">
        <i class="fas fa-image text-4xl"></i>
      </div>
      
      <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-end p-3">
        <button class="w-full py-2 bg-accent-1 text-white text-xs font-bold rounded-lg transform translate-y-4 group-hover:translate-y-0 transition-transform duration-300 shadow-lg">
          {{ loading ? '加载中...' : actionLabel }}
        </button>
      </div>
      
      <div v-if="loading" class="absolute inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-20">
        <i class="fas fa-circle-notch fa-spin text-accent-1 text-2xl"></i>
      </div>
    </div>

    <div class="p-3 flex flex-col flex-1">
      <h4 class="text-sm font-bold text-text-main line-clamp-2 leading-tight group-hover:text-accent-1 transition-colors mb-1">
        {{ manga.title || manga.id }}
      </h4>
      <p class="text-[10px] text-text-secondary truncate opacity-60 font-mono mt-auto pt-2 border-t border-border-subtle">
        {{ manga.url }}
      </p>
    </div>
  </div>
</template>
