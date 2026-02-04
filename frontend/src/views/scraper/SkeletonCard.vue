<template>
  <div class="flex flex-col bg-bg-secondary/20 border border-border-subtle rounded-xl overflow-hidden h-full">
    <!-- Cover Skeleton -->
    <div class="aspect-[2/3] w-full bg-bg-secondary/50 animate-pulse relative overflow-hidden">
      <div class="absolute inset-0 bg-gradient-to-r from-transparent via-white/5 to-transparent -translate-x-full animate-[shimmer_1.5s_infinite]"></div>
    </div>

    <!-- Info Skeleton -->
    <div class="p-3 flex flex-col gap-2 flex-1">
      <div class="h-4 bg-bg-secondary/50 rounded w-3/4 animate-pulse"></div>
      <div class="h-3 bg-bg-secondary/30 rounded w-1/2 animate-pulse mt-auto"></div>
    </div>
  </div>
</template>

<style scoped>
@keyframes shimmer {
  100% {
    transform: translateX(100%);
  }
}
</style>
