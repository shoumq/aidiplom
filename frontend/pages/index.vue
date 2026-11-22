<script setup lang="ts">
import MarkdownIt from 'markdown-it'
import type { Chat, ChatSummary, Order, Settings, User } from '~/types'

const writer = useWriterApi()
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
const chats = ref<ChatSummary[]>([])
const current = ref<Chat | null>(null)
const meta = ref<any>(null)
const prompt = ref('')
const busy = ref('')
const error = ref('')
const mobilePanel = ref<'chats' | 'editor' | 'settings'>('editor')
const advanced = ref(false)
const revision = ref({ index: 0, instruction: '' })
const linksText = ref('')
const user = ref<User | null>(null)
const authMode = ref<'login' | 'register'>('login')
const authForm = reactive({ email: '', password: '', privacyAccepted: false, offerAccepted: false, referralCode: '' })
const authDialog = ref<HTMLDialogElement | null>(null)
const guideDialog = ref<HTMLDialogElement | null>(null)
const authError = ref('')
const offerAccepted = ref(false)
const applyCredit = ref(true)
const sectionIndex = ref<number | undefined>()
const route = useRoute()
const authBusy = ref(false)
const checkout = ref<{ order: Order; prompt: string; settings: Settings; appliedCredit?: number } | null>(null)
const checkoutPaid = computed(() => !!checkout.value && ['paid', 'generating', 'completed'].includes(checkout.value.order.status))
const initialSettings: Settings = { model: 'claude-sonnet-5.5', work_type: 'Эссе', language: 'русский', words: 800, total_words: 8000, style: '', style_sample: '', extra: '', rewrite_level: 90, use_search: true, links: [], plan_mode: 'auto', given_plan: '', user_data: '', live_style_enabled: true, live_style: '' }
const settings = reactive<Settings>({ ...initialSettings })
const isLong = computed(() => ['Курсовая работа', 'Дипломная работа'].includes(settings.work_type))
const writtenCount = computed(() => Object.keys(current.value?.lw?.written || {}).length)
const writable = computed(() => current.value?.lw?.plan?.filter(x => x.words > 0).length || 0)
const lastAssistant = computed(() => [...(current.value?.history || [])].reverse().find(x => x.role === 'assistant'))
const creditToApply = computed(() => checkout.value?.appliedCredit ?? (applyCredit.value ? Math.min(user.value?.balance_rub ?? 0, checkout.value?.order.amount_rub ?? 0) : 0))
const remainingPrice = computed(() => (checkout.value?.order.amount_rub ?? 0) - creditToApply.value)
const referralLink = computed(() => {
  if (!user.value || !import.meta.client) return ''
  const url = new URL('/', window.location.origin)
  url.searchParams.set('ref', user.value.referral_code)
  return url.href
})
const selectedSectionText = computed(() => sectionIndex.value === undefined ? '' : current.value?.lw?.written?.[sectionIndex.value]?.[0] ?? '')
watch(() => current.value?.id, () => { sectionIndex.value = undefined })
const selectedWords = computed({
  get: () => isLong.value ? settings.total_words : settings.words,
  set: (value: number) => { if (isLong.value) settings.total_words = value; else settings.words = value }
})
const selectedPages = computed({
  get: () => Math.max(1, Math.ceil(selectedWords.value / 350)),
  set: (value: number) => { selectedWords.value = Math.max(1, Number(value) || 1) * 350 }
})

function messageHtml(text: string) { return md.render(text) }
function explainError(e: any) { error.value = e?.data?.detail || e?.message || 'Не удалось выполнить действие' }
async function refreshList() { chats.value = await writer.chats() }
async function openChat(id: string) {
  if (busy.value) return
  busy.value = 'Открываю чат'
  error.value = ''
  try {
    current.value = await writer.chat(id)
    settings.work_type = current.value.work_type
    mobilePanel.value = 'editor'
  } catch (e) { explainError(e) } finally { busy.value = '' }
}
async function createChat() { if (!user.value) return openAuth(); if (busy.value) return; busy.value = 'Новый чат'; try { current.value = await writer.create(settings.work_type); await refreshList(); mobilePanel.value = 'editor' } catch (e) { explainError(e) } finally { busy.value = '' } }
async function removeChat(id: string) {
  if (busy.value || !confirm('Удалить этот чат из истории?')) return
  busy.value = 'Удаляю чат'
  error.value = ''
  try {
    await writer.remove(id)
    await refreshList()
    if (current.value?.id === id) {
      current.value = chats.value[0] ? await writer.chat(chats.value[0].id) : null
      if (current.value) settings.work_type = current.value.work_type
    }
  } catch (e) { explainError(e) } finally { busy.value = '' }
}
function openAuth(mode: 'login' | 'register' = authForm.referralCode ? 'register' : 'login') {
  authMode.value = mode
  authError.value = ''
  if (!authDialog.value?.open) authDialog.value?.showModal()
}
function setExample(type: 'Эссе' | 'Курсовая работа') {
  settings.work_type = type
  prompt.value = type === 'Эссе'
    ? 'Напиши эссе о влиянии искусственного интеллекта на образование'
    : 'Составь план курсовой работы по цифровой трансформации бизнеса'
}
function setLiveStyle(event: Event) {
  settings.live_style_enabled = (event.target as HTMLInputElement).checked
  if (settings.live_style_enabled && !settings.live_style.trim()) {
    settings.live_style = meta.value?.live_style || ''
  }
}
async function send() {
  if (busy.value || !prompt.value.trim()) return
  if (!user.value) return openAuth()
  busy.value = 'Рассчитываю стоимость'
  error.value = ''
  settings.links = linksText.value.split('\n').map(x => x.trim()).filter(Boolean)
  const snapshot = JSON.parse(JSON.stringify(settings)) as Settings
  try {
    const topic = prompt.value.trim()
    if (!current.value) {
      const chat = await writer.create(settings.work_type)
      current.value = chat
      chats.value.unshift({ id: chat.id, title: chat.title, work_type: chat.work_type })
    }
    const order = await writer.quote(current.value.id, topic, snapshot)
    applyCredit.value = true
    offerAccepted.value = false
    checkout.value = { order, prompt: topic, settings: snapshot }
  } catch (e) { explainError(e) } finally { busy.value = '' }
}
async function payAndGenerate() {
  if (busy.value || !checkout.value || (!checkoutPaid.value && checkout.value.order.status !== 'payment_pending' && meta.value?.offer_version && !offerAccepted.value)) return
  busy.value = 'Подтверждаю заказ'
  error.value = ''
  const purchase = checkout.value
  try {
    if (!checkoutPaid.value) {
      const credit = creditToApply.value
      const result = await writer.pay(purchase.order.id, credit, meta.value?.offer_version ?? undefined)
      purchase.order = result
      purchase.appliedCredit = result.credit_rub ?? credit
      if (result.confirmation_url && !['paid', 'generating', 'completed'].includes(result.status)) {
        window.location.assign(result.confirmation_url)
        return
      }
      if (!['paid', 'generating', 'completed'].includes(result.status)) {
        error.value = result.payment_status === 'canceled' ? 'Платёж отменён. Создайте новый заказ.' : 'Платёж ожидает подтверждения.'
        return
      }
      user.value = await writer.me()
    }
    if (purchase.order.status === 'completed') {
      current.value = await writer.chat(purchase.order.chat_id)
      checkout.value = null
      return
    }
    busy.value = ['Курсовая работа', 'Дипломная работа'].includes(purchase.settings.work_type) ? 'Составляю план' : 'Пишу ответ'
    current.value = await writer.send(purchase.order.chat_id, purchase.prompt, purchase.settings, purchase.order.id)
    sectionIndex.value = undefined
    prompt.value = ''
    checkout.value = null
    await refreshList()
  } catch (e) { explainError(e) } finally { busy.value = '' }
}
async function writeWork(indices?: number[]) {
  if (busy.value || !current.value) return
  const chatId = current.value.id
  busy.value = indices ? 'Пишу раздел' : writtenCount.value ? 'Продолжаю работу' : 'Пишу работу'
  error.value = ''
  try {
    current.value = await writer.write(chatId, settings, indices)
    await refreshList()
  } catch (e) {
    explainError(e)
    try { current.value = await writer.chat(chatId) } catch { /* Keep the generation error visible. */ }
  } finally { busy.value = '' }
}
async function revise() { if (busy.value || !current.value || !revision.value.instruction.trim()) return; busy.value = 'Переписываю раздел'; error.value = ''; try { current.value = await writer.revise(current.value.id, revision.value.index, revision.value.instruction, settings); revision.value.instruction = '' } catch (e) { explainError(e) } finally { busy.value = '' } }
async function resetWork() {
  if (busy.value || !current.value || !confirm('Сбросить план и написанные разделы?')) return
  busy.value = 'Сбрасываю план'
  try {
    current.value = await writer.reset(current.value.id)
    sectionIndex.value = undefined
  } catch (e) { explainError(e) } finally { busy.value = '' }
}
async function loadMeta() {
  meta.value = await writer.meta()
  settings.model = meta.value.default_model
  if (settings.live_style_enabled && !settings.live_style.trim()) settings.live_style = meta.value.live_style
}
async function loadWorkspace(preserveDraft = false) {
  await refreshList()
  if (!preserveDraft && chats.value[0]) await openChat(chats.value[0].id)
}
async function authenticate() {
  if (authBusy.value) return
  authBusy.value = true
  authError.value = ''
  try {
    user.value = authMode.value === 'login'
      ? await writer.login(authForm.email, authForm.password)
      : await writer.register({
          email: authForm.email,
          password: authForm.password,
          privacy_accepted: authForm.privacyAccepted,
          privacy_version: meta.value?.privacy_version,
          offer_version: authForm.offerAccepted ? meta.value?.offer_version : undefined,
          referral_code: authForm.referralCode
        })
    authForm.password = ''
    authDialog.value?.close()
    try { await loadWorkspace(!!prompt.value.trim()); await restorePayment() } catch (e) { explainError(e) }
  } catch (e: any) {
    authError.value = e?.data?.detail || 'Не удалось выполнить вход или регистрацию'
  } finally { authBusy.value = false }
}
async function logout() {
  if (busy.value) return
  try {
    await writer.logout()
    user.value = null
    current.value = null
    chats.value = []
    checkout.value = null
    prompt.value = ''
    linksText.value = ''
    Object.assign(settings, initialSettings, { model: meta.value?.default_model, live_style: meta.value?.live_style })
    authForm.password = ''
  } catch (e) { explainError(e) }
}
async function deleteAccount() {
  if (busy.value || !confirm('Удалить аккаунт, все тексты и заказы без возможности восстановления?')) return
  try { await writer.deleteAccount(); await logout() } catch (e) { explainError(e) }
}

async function restorePayment() {
  const orderId = checkout.value?.order.id || (typeof route.query.order === 'string' ? route.query.order : '')
  if (!user.value || !orderId || busy.value) return
  busy.value = 'Проверяю оплату'
  error.value = ''
  try {
    const order = await writer.order(orderId)
    if (!order.settings || !order.prompt) throw new Error('Данные заказа недоступны')
    checkout.value = { order, settings: order.settings, prompt: order.prompt, appliedCredit: order.credit_rub }
    offerAccepted.value = true
    current.value = await writer.chat(order.chat_id)
    settings.work_type = order.work_type
    mobilePanel.value = 'editor'
    user.value = await writer.me()
  } catch (e) { explainError(e) } finally { busy.value = '' }
}

onMounted(async () => {
  if (typeof route.query.ref === 'string') authForm.referralCode = route.query.ref.slice(0, 32)
  const results = await Promise.allSettled([loadMeta(), writer.me()])
  if (results[0].status === 'rejected') explainError(results[0].reason)
  const session = results[1]
  if (session.status === 'fulfilled') {
    user.value = session.value
    try { await loadWorkspace(); await restorePayment() } catch (e) { explainError(e) }
  } else if (session.reason?.status !== 401 && session.reason?.statusCode !== 401) {
    explainError(session.reason)
  }
})
</script>

<template>
  <dialog ref="authDialog" class="auth-card app-dialog" aria-labelledby="auth-title">
      <button type="button" class="checkout-close" aria-label="Закрыть" @click="authDialog?.close()">×</button>
      <div class="auth-brand"><img class="brand-logo" src="/avtorskaya-logo.png" alt=""><strong>Авторская</strong></div>
      <h1 id="auth-title">{{ authMode === 'login' ? 'Войти' : 'Создать аккаунт' }}</h1>
      <p>{{ authMode === 'login' ? 'Ваши работы доступны после входа.' : 'Сохраняйте чаты и продолжайте работу с любого устройства.' }}</p>
      <form @submit.prevent="authenticate">
        <label>Email<input v-model.trim="authForm.email" type="email" autocomplete="email" required placeholder="student@example.com"></label>
        <label>Пароль<input v-model="authForm.password" type="password" :autocomplete="authMode === 'login' ? 'current-password' : 'new-password'" minlength="8" required placeholder="Не менее 8 символов"></label>
        <label v-if="authMode === 'register'" class="legal-consent"><input v-model="authForm.privacyAccepted" type="checkbox" required><span>Принимаю <NuxtLink to="/privacy" target="_blank">политику обработки персональных данных</NuxtLink></span></label>
        <template v-if="authMode === 'register'">
          <label>Реферальный код (необязательно)<input v-model.trim="authForm.referralCode" maxlength="32" autocomplete="off"></label>
          <label v-if="meta?.offer_version" class="legal-consent"><input v-model="authForm.offerAccepted" type="checkbox" required><span>Принимаю <NuxtLink to="/offer" target="_blank">условия публичной оферты</NuxtLink></span></label>
        </template>
        <div v-if="authError" class="auth-error" role="alert">{{ authError }}</div>
        <button class="auth-submit" :disabled="authBusy">{{ authBusy ? 'Подождите…' : authMode === 'login' ? 'Войти' : 'Зарегистрироваться' }}</button>
      </form>
      <button class="auth-switch" @click="authMode = authMode === 'login' ? 'register' : 'login'; authError = ''">{{ authMode === 'login' ? 'Нет аккаунта? Зарегистрироваться' : 'Уже есть аккаунт? Войти' }}</button>
  </dialog>
  <div class="app-shell">
    <header class="mobile-nav">
      <button @click="mobilePanel = 'chats'"><Icon name="lucide:library" /> Чаты</button>
      <strong>Авторская</strong>
      <button @click="mobilePanel = 'settings'"><Icon name="lucide:sliders-horizontal" /> Настройки</button>
    </header>

    <aside class="chat-rail" :class="{ 'mobile-show': mobilePanel === 'chats' }">
      <div class="brand"><img class="brand-logo" src="/avtorskaya-logo.png" alt=""><div><strong>Авторская</strong><small>Учебные работы</small></div></div>
      <button class="new-chat" :disabled="!!busy" @click="createChat"><Icon name="lucide:plus" /> Новый текст</button>
      <nav v-if="user" class="chat-list" aria-label="История чатов">
        <div v-for="chat in chats" :key="chat.id" class="chat-row" :class="{ active: current?.id === chat.id }">
          <button class="chat-item" :disabled="!!busy" @click="openChat(chat.id)">
            <span><strong>{{ chat.title }}</strong><small>{{ chat.work_type }}</small></span>
          </button>
          <button type="button" class="chat-delete" :aria-label="`Удалить чат «${chat.title}»`" :disabled="!!busy" @click="removeChat(chat.id)"><Icon name="lucide:trash-2" /></button>
        </div>
      </nav>
      <div class="account-block">
        <template v-if="user">
          <span>{{ user.email }}</span>
          <p>Баланс {{ user.balance_rub.toLocaleString('ru-RU') }} ₽</p>
          <details class="referral-details">
            <summary>Пригласить друга</summary>
            <p>{{ meta?.referral_reward_rub ?? 150 }} ₽ на баланс после первой оплаты друга.<template v-if="meta?.payment_mode === 'mock'"> Сейчас начисления тестовые.</template></p>
            <label>Ссылка для приглашения<input readonly :value="referralLink" @focus="($event.target as HTMLInputElement).select()"></label>
            <p>Код приглашения <code>{{ user.referral_code }}</code></p>
          </details>
          <button class="delete-account" :disabled="!!busy" @click="deleteAccount"><Icon name="lucide:user-x" /> Удалить аккаунт</button>
          <button :disabled="!!busy" @click="logout"><Icon name="lucide:log-out" /> Выйти</button>
        </template>
        <button v-else @click="openAuth()">Войти или зарегистрироваться</button>
        <NuxtLink to="/privacy"><Icon name="lucide:shield-check" /> Конфиденциальность</NuxtLink>
        <NuxtLink v-if="meta?.offer_version" to="/offer">Публичная оферта</NuxtLink>
      </div>
    </aside>

    <main class="workspace" :class="{ 'mobile-hide': mobilePanel !== 'editor' }">
      <header class="workspace-head">
        <div><span class="status-dot" /> {{ busy || 'Готов к работе' }}</div>
        <div class="workspace-actions">
          <button type="button" class="text-action" @click="guideDialog?.showModal()">Как пользоваться</button>
          <button v-if="!user" type="button" class="text-action" @click="openAuth()">Войти</button>
          <div class="downloads" v-if="lastAssistant && current">
            <a :href="writer.download(current.id, 'docx')"><Icon name="lucide:file-text" /> Скачать Word</a>
          </div>
        </div>
      </header>

      <section class="manuscript">
        <div v-if="!current?.history.length" class="empty-state">
          <div class="folio"><Icon name="lucide:file-pen-line" /></div>
          <h1>Что нужно написать?</h1>
          <p>Укажите тему, выберите тип и объём работы, затем отправьте задание для расчёта стоимости. Для курсовой или дипломной вы сможете проверить план и выбрать, какие разделы написать.</p>
          <div class="prompt-chips"><button @click="setExample('Эссе')">Пример эссе</button><button @click="setExample('Курсовая работа')">Пример курсовой</button></div>
        </div>
        <article v-for="(message, index) in current?.history" :key="index" class="message" :class="message.role">
          <div class="message-label">{{ message.role === 'user' ? 'Вы' : 'Авторская' }}</div>
          <div class="markdown" v-html="messageHtml(message.content)" />
        </article>
        <article v-if="selectedSectionText && !current?.lw.final" class="message assistant">
          <div class="message-label">Готовый раздел</div>
          <div class="markdown" v-html="messageHtml(selectedSectionText)" />
        </article>
      </section>

      <div v-if="error" class="error-banner"><Icon name="lucide:circle-alert" /><span>{{ error }}</span><button @click="error=''">×</button></div>
      <form class="composer" @submit.prevent="send">
        <textarea v-model="prompt" aria-label="Задание" rows="2" :placeholder="isLong ? 'Тема, задание или правки к плану…' : 'Тема, задача или правки…'" @keydown.meta.enter.prevent="send" @keydown.ctrl.enter.prevent="send" />
        <div class="composer-foot"><span>Ctrl/⌘ + Enter</span><button type="submit" aria-label="Отправить задание" :disabled="!!busy || !prompt.trim()"><Icon v-if="busy" name="lucide:loader-circle" class="spin" /><svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg></button></div>
      </form>
    </main>

    <aside class="settings-panel" :class="{ 'mobile-show': mobilePanel === 'settings' }">
      <div class="settings-title"><div><h2>Параметры</h2><p>Настройте форму и голос текста</p></div><button class="mobile-close" @click="mobilePanel='editor'">×</button></div>
      <label>Модель
        <select v-model="settings.model">
          <option v-for="(model, id) in meta?.models" :key="id" :value="id">{{ model.label }} — {{ model.tier }}</option>
        </select>
        <small class="model-rate">Стоимость модели войдёт в заказ.</small>
      </label>
      <label>Тип работы<select v-model="settings.work_type"><option v-for="(_, name) in meta?.work_types" :key="name">{{ name }}</option></select><small>{{ meta?.work_types?.[settings.work_type] }}</small></label>
      <div class="field-row"><label>Язык<select v-model="settings.language"><option v-for="lang in meta?.languages" :key="lang">{{ lang }}</option></select></label><label>Объём, страниц<input v-model.number="selectedPages" type="number" min="1" :max="isLong ? 115 : 18"><small>≈ {{ selectedWords.toLocaleString('ru-RU') }} слов</small></label></div>

      <template v-if="isLong">
        <div v-if="current?.lw?.plan" class="plan-card">
          <div class="plan-head"><strong>План готов</strong><span>{{ writtenCount }}/{{ writable }} разделов</span></div>
          <ol><li v-for="(item, i) in current.lw.plan" :key="i" :class="{ chapter: item.level === 1 }"><span>{{ item.title }}</span><small v-if="item.words">{{ item.words }}</small></li></ol>
          <button v-if="!current.lw.final" class="primary-action" :disabled="!!busy" @click="writeWork()">{{ writtenCount ? 'Продолжить работу' : 'Написать по плану' }}</button>
          <template v-if="!current.lw.final">
            <label>Отдельный раздел<select v-model="sectionIndex" :disabled="!!busy"><option :value="undefined">Выберите раздел</option><template v-for="(item, i) in current.lw.plan" :key="i"><option v-if="item.words" :value="i">{{ item.title }}{{ current.lw.written?.[i] ? ' (готов)' : '' }}</option></template></select></label>
            <button v-if="sectionIndex !== undefined && !selectedSectionText" class="text-action" :disabled="!!busy" @click="writeWork([sectionIndex])">Написать выбранный раздел</button>
            <button v-if="selectedSectionText" class="text-action" @click="mobilePanel = 'editor'">Показать в редакторе</button>
          </template>
          <template v-else><label>Раздел для правки<select v-model.number="revision.index"><option v-for="(item, i) in current.lw.plan" v-show="item.words" :key="i" :value="i" :disabled="!item.words">{{ item.title }}</option></select></label><label>Что изменить<textarea v-model="revision.instruction" rows="3" /></label><button class="primary-action" :disabled="!!busy" @click="revise">Переписать раздел</button></template>
          <button class="text-action danger" :disabled="!!busy" @click="resetWork">Сбросить план</button>
        </div>
        <template v-else><label>План<select v-model="settings.plan_mode"><option value="auto">Составить автоматически</option><option value="given">У меня есть готовый</option></select></label><label v-if="settings.plan_mode === 'given'">Ваш план<textarea v-model="settings.given_plan" rows="5" /></label></template>
        <label>Данные для практической части<textarea v-model="settings.user_data" rows="4" placeholder="Показатели, выдержки, цифры…" /></label>
      </template>
      <label class="toggle"><input :checked="settings.live_style_enabled" type="checkbox" @change="setLiveStyle"><span /> Живой авторский стиль</label>
      <details v-if="settings.live_style_enabled" class="live-style-details">
        <summary>Промпт живого стиля</summary>
        <textarea v-model="settings.live_style" aria-label="Промпт живого стиля" rows="7" />
      </details>

      <button class="section-toggle" @click="advanced = !advanced"><span><Icon name="lucide:pen-tool" /> Стиль и источники</span><Icon :name="advanced ? 'lucide:chevron-up' : 'lucide:chevron-down'" /></button>
      <div v-if="advanced" class="advanced-fields">
        <label>Стиль и тон<input v-model="settings.style" placeholder="академический, живой…"></label>
        <label>Образец вашего стиля<textarea v-model="settings.style_sample" rows="4" /></label>
        <label>Дополнительные требования<textarea v-model="settings.extra" rows="3" /></label>
        <label class="toggle"><input v-model="settings.use_search" type="checkbox"><span /> Веб-поиск источников</label>
        <label>Ссылки, по одной в строке<textarea v-model="linksText" rows="4" placeholder="https://…" /></label>
        <label>Переработка источников — {{ settings.rewrite_level }}%<input v-model.number="settings.rewrite_level" type="range" min="50" max="100"></label>
      </div>
    </aside>

    <div v-if="checkout" class="checkout-backdrop" @click.self="!busy && (checkout = null)">
      <section class="checkout-sheet" role="dialog" aria-modal="true" aria-labelledby="checkout-title">
        <button class="checkout-close" aria-label="Закрыть" :disabled="!!busy" @click="checkout = null">×</button>
        <div class="checkout-mark"><Icon name="lucide:receipt-text" /></div>
        <h2 id="checkout-title">Заказ готов к оплате</h2>
        <p class="checkout-topic">{{ checkout.prompt }}</p>
        <dl class="checkout-lines">
          <div v-for="line in checkout.order.breakdown" :key="line.label"><dt><strong>{{ line.label }}</strong><small v-if="line.detail">{{ line.detail }}</small></dt><dd>{{ line.amount_rub }} ₽</dd></div>
        </dl>
        <label v-if="user?.balance_rub && !checkoutPaid" class="legal-consent"><input v-model="applyCredit" type="checkbox" :disabled="!!busy"><span>Использовать баланс (доступно {{ user.balance_rub }} ₽)</span></label>
        <div v-if="creditToApply" class="checkout-total"><span>С баланса</span><strong>{{ creditToApply }} ₽</strong></div>
        <div class="checkout-total"><span>К оплате</span><strong>{{ remainingPrice }} ₽</strong></div>
        <div class="checkout-includes"><strong>Что входит в стоимость</strong><ul><li v-for="item in checkout.order.includes" :key="item"><Icon name="lucide:check" />{{ item }}</li></ul></div>
        <label v-if="meta?.offer_version && !checkoutPaid" class="legal-consent"><input v-model="offerAccepted" type="checkbox" :disabled="!!busy"><span>Принимаю <NuxtLink to="/offer" target="_blank">условия публичной оферты</NuxtLink></span></label>
        <div v-if="error" class="auth-error" role="alert">{{ error }}</div>
        <button class="checkout-pay" :disabled="!!busy || (!!meta?.offer_version && !offerAccepted && !checkoutPaid && checkout.order.status !== 'payment_pending') || (!checkoutPaid && checkout.order.payment_mode === 'external' && remainingPrice > 0) || checkout.order.status === 'expired'" @click="payAndGenerate">
          <Icon :name="busy ? 'lucide:loader-circle' : 'lucide:credit-card'" :class="{ spin: !!busy }" />
          {{ busy || (checkoutPaid ? 'Продолжить работу' : checkout.order.status === 'payment_pending' ? 'Перейти к оплате' : remainingPrice ? `Оплатить ${remainingPrice} ₽` : 'Оплатить с баланса') }}
        </button>
        <p v-if="checkout.order.payment_mode === 'mock'" class="checkout-note"><Icon name="lucide:flask-conical" /> Тестовый режим — деньги не списываются</p>
        <button v-if="checkout.order.status === 'payment_pending'" class="text-action" :disabled="!!busy" @click="restorePayment">Проверить оплату</button>
        <p v-if="checkout.order.payment_mode === 'external' && remainingPrice > 0" class="checkout-note">Оплата картой пока недоступна.</p>
      </section>
    </div>
  </div>
  <dialog ref="guideDialog" class="app-dialog guide-dialog" aria-labelledby="guide-title">
    <button type="button" class="checkout-close" aria-label="Закрыть" @click="guideDialog?.close()">×</button>
    <h2 id="guide-title">Как подготовить работу</h2>
    <ol>
      <li><strong>Сформулируйте задачу.</strong> Укажите тему, дисциплину и требования преподавателя, чтобы результат соответствовал заданию.</li>
      <li><strong>Настройте текст.</strong> Выберите тип, язык, объём и модель. Добавьте источники или образец стиля, если хотите задать тон и опорные материалы.</li>
      <li><strong>Отправьте задание.</strong> Войдите или зарегистрируйтесь, если вы ещё не в аккаунте. Тема и параметры сохранятся при входе.</li>
      <li><strong>Проверьте заказ.</strong> Стоимость видна до оплаты. При наличии баланса его можно применить к заказу.</li>
      <li><strong>Проверьте план длинной работы.</strong> Для курсовой или дипломной можно задать свой план, добавить данные для практической части и написать всю работу или выбранный раздел.</li>
      <li><strong>Проверьте результат.</strong> Сверьте факты и источники, внесите нужные правки и скачайте текст в Word.</li>
    </ol>
  </dialog>
</template>
