<script setup lang="ts">
const { public: { apiBase } } = useRuntimeConfig()
const { data: offer } = await useFetch<{ text: string; version: string } | null>(`${apiBase}/legal/offer`)
useHead({ title: 'Публичная оферта — Авторская' })
</script>

<template>
  <main class="legal-page">
    <NuxtLink class="legal-back" to="/">← Вернуться в Авторскую</NuxtLink>
    <article>
      <h1>Публичная оферта</h1>
      <div v-if="offer" class="legal-text">{{ offer.text }}</div>
      <p v-else>Оферта ещё не опубликована.</p>
    </article>
  </main>
</template>
