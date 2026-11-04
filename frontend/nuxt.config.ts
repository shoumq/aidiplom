export default defineNuxtConfig({
  compatibilityDate: '2025-05-15',
  devtools: { enabled: false },
  modules: ['@nuxt/icon'],
  css: ['~/assets/css/main.css', '~/assets/css/logo.css'],
  runtimeConfig: { public: {
    apiBase: process.env.NUXT_PUBLIC_API_BASE || 'http://localhost:8000/api',
    operatorName: process.env.NUXT_PUBLIC_OPERATOR_NAME || '[Укажите ФИО ИП/самозанятого или название организации]',
    operatorEmail: process.env.NUXT_PUBLIC_OPERATOR_EMAIL || '[Укажите email оператора]',
    operatorAddress: process.env.NUXT_PUBLIC_OPERATOR_ADDRESS || '[Укажите адрес оператора]'
  } },
  app: { head: { title: 'Авторская — Writer Agent', meta: [{ name: 'description', content: 'Редакторская среда для учебных и авторских работ' }], link: [{ rel: 'icon', type: 'image/png', href: '/avtorskaya-logo.png' }] } }
})
