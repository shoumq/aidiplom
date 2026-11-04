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
const authForm = reactive({ email: '', password: '', privacyAccepted: false })
const authBusy = ref(false)
const checkout = ref<{ order: Order; prompt: string; settings: Settings } | null>(null)
const settings = reactive<Settings>({ model: 'claude-sonnet-5.5', work_type: 'Эссе', language: 'русский', words: 800, total_words: 8000, style: '', style_sample: '', extra: '', rewrite_level: 90, use_search: true, links: [], plan_mode: 'auto', given_plan: '', user_data: '', live_style_enabled: true, live_style: '' })
const isLong = computed(() => ['Курсовая работа', 'Дипломная работа'].includes(settings.work_type))
const writtenCount = computed(() => Object.keys(current.value?.lw?.written || {}).length)
const writable = computed(() => current.value?.lw?.plan?.filter(x => x.words > 0).length || 0)
const lastAssistant = computed(() => [...(current.value?.history || [])].reverse().find(x => x.role === 'assistant'))
const selectedModel = computed(() => meta.value?.models?.[settings.model])
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
async function openChat(id: string) { error.value = ''; current.value = await writer.chat(id); settings.work_type = current.value.work_type; mobilePanel.value = 'editor' }
async function createChat() { busy.value = 'Новый чат'; try { current.value = await writer.create(settings.work_type); await refreshList(); mobilePanel.value = 'editor' } catch (e) { explainError(e) } finally { busy.value = '' } }
async function removeChat(id: string) { if (!confirm('Удалить этот чат?')) return; await writer.remove(id); await refreshList(); current.value = chats.value[0] ? await writer.chat(chats.value[0].id) : await writer.create(); await refreshList() }
async function send() {
  if (!prompt.value.trim() || !current.value) return
  busy.value = 'Рассчитываю стоимость'
  error.value = ''
  settings.links = linksText.value.split('\n').map(x => x.trim()).filter(Boolean)
  const snapshot = JSON.parse(JSON.stringify(settings)) as Settings
  try {
    const order = await writer.quote(current.value.id, prompt.value.trim(), snapshot)
    checkout.value = { order, prompt: prompt.value.trim(), settings: snapshot }
  } catch (e) { explainError(e) } finally { busy.value = '' }
}
async function payAndGenerate() {
  if (!checkout.value || !current.value) return
  busy.value = 'Провожу тестовую оплату'
  error.value = ''
  const purchase = checkout.value
  try {
    await writer.mockPay(purchase.order.id)
    busy.value = isLong.value ? 'Составляю план' : 'Пишу ответ'
    current.value = await writer.send(current.value.id, purchase.prompt, purchase.settings, purchase.order.id)
    prompt.value = ''
    checkout.value = null
    await refreshList()
  } catch (e) { explainError(e) } finally { busy.value = '' }
}
async function writeWork() { if (!current.value) return; busy.value = writtenCount.value ? 'Продолжаю работу' : 'Пишу работу'; error.value = ''; try { current.value = await writer.write(current.value.id, settings); await refreshList() } catch (e) { explainError(e); current.value = await writer.chat(current.value.id) } finally { busy.value = '' } }
async function revise() { if (!current.value || !revision.value.instruction.trim()) return; busy.value = 'Переписываю раздел'; error.value = ''; try { current.value = await writer.revise(current.value.id, revision.value.index, revision.value.instruction, settings); revision.value.instruction = '' } catch (e) { explainError(e) } finally { busy.value = '' } }
async function resetWork() { if (!current.value || !confirm('Сбросить план и написанные разделы?')) return; current.value = await writer.reset(current.value.id) }
async function loadWorkspace() { [meta.value, chats.value] = await Promise.all([writer.meta(), writer.chats()]); settings.model = meta.value.default_model; settings.live_style = meta.value.live_style; if (chats.value[0]) current.value = await writer.chat(chats.value[0].id) }
async function authenticate() { authBusy.value = true; error.value = ''; try { user.value = authMode.value === 'login' ? await writer.login(authForm.email, authForm.password) : await writer.register(authForm.email, authForm.password, authForm.privacyAccepted); authForm.password = ''; await loadWorkspace() } catch (e) { explainError(e) } finally { authBusy.value = false } }
async function logout() { await writer.logout(); user.value = null; current.value = null; chats.value = []; authForm.password = '' }
async function deleteAccount() { if (!confirm('Удалить аккаунт, все тексты и заказы без возможности восстановления?')) return; await writer.deleteAccount(); user.value = null; current.value = null; chats.value = [] }

onMounted(async () => { try { meta.value = await writer.meta(); user.value = await writer.me(); await loadWorkspace() } catch (e: any) { if (e?.status !== 401 && e?.statusCode !== 401) explainError(e) } })
</script>

<template>
  <main v-if="!user" class="auth-page">
    <section class="auth-card">
      <div class="auth-brand"><img class="brand-logo" src="/avtorskaya-logo.png" alt=""><strong>Авторская</strong></div>
      <h1>{{ authMode === 'login' ? 'Войти' : 'Создать аккаунт' }}</h1>
      <p>{{ authMode === 'login' ? 'Ваши работы доступны после входа.' : 'Сохраняйте чаты и продолжайте работу с любого устройства.' }}</p>
      <form @submit.prevent="authenticate">
        <label>Email<input v-model.trim="authForm.email" type="email" autocomplete="email" required placeholder="student@example.com"></label>
        <label>Пароль<input v-model="authForm.password" type="password" :autocomplete="authMode === 'login' ? 'current-password' : 'new-password'" minlength="8" required placeholder="Не менее 8 символов"></label>
        <label v-if="authMode === 'register'" class="legal-consent"><input v-model="authForm.privacyAccepted" type="checkbox" required><span>Принимаю <NuxtLink to="/privacy" target="_blank">политику обработки персональных данных</NuxtLink></span></label>
        <div v-if="error" class="auth-error">{{ error }}</div>
        <button class="auth-submit" :disabled="authBusy">{{ authBusy ? 'Подождите…' : authMode === 'login' ? 'Войти' : 'Зарегистрироваться' }}</button>
      </form>
      <button class="auth-switch" @click="authMode = authMode === 'login' ? 'register' : 'login'; error = ''">{{ authMode === 'login' ? 'Нет аккаунта? Зарегистрироваться' : 'Уже есть аккаунт? Войти' }}</button>
    </section>
  </main>
  <div v-else class="app-shell">
    <header class="mobile-nav">
      <button @click="mobilePanel = 'chats'"><Icon name="lucide:library" /> Чаты</button>
      <strong>Авторская</strong>
      <button @click="mobilePanel = 'settings'"><Icon name="lucide:sliders-horizontal" /> Настройки</button>
    </header>

    <aside class="chat-rail" :class="{ 'mobile-show': mobilePanel === 'chats' }">
      <div class="brand"><img class="brand-logo" src="/avtorskaya-logo.png" alt=""><div><strong>Авторская</strong><small>Учебные работы</small></div></div>
      <button class="new-chat" :disabled="!!busy" @click="createChat"><Icon name="lucide:plus" /> Новый текст</button>
      <nav class="chat-list" aria-label="История чатов">
        <button v-for="chat in chats" :key="chat.id" class="chat-item" :class="{ active: current?.id === chat.id }" @click="openChat(chat.id)">
          <span><strong>{{ chat.title }}</strong><small>{{ chat.work_type }}</small></span>
          <Icon name="lucide:trash-2" class="trash" @click.stop="removeChat(chat.id)" />
        </button>
      </nav>
      <div class="account-block"><span>{{ user.email }}</span><a :href="writer.exportAccount()"><Icon name="lucide:download" /> Скачать мои данные</a><NuxtLink to="/privacy"><Icon name="lucide:shield-check" /> Конфиденциальность</NuxtLink><button class="delete-account" @click="deleteAccount"><Icon name="lucide:user-x" /> Удалить аккаунт</button><button @click="logout"><Icon name="lucide:log-out" /> Выйти</button></div>
    </aside>

    <main class="workspace" :class="{ 'mobile-hide': mobilePanel !== 'editor' }">
      <header class="workspace-head">
        <div><span class="status-dot" /> {{ busy || 'Готов к работе' }}</div>
        <div class="downloads" v-if="lastAssistant && current">
          <a :href="writer.download(current.id, 'docx')"><Icon name="lucide:file-text" /> Скачать Word</a>
        </div>
      </header>

      <section v-if="current" class="manuscript">
        <div v-if="!current.history.length" class="empty-state">
          <div class="folio"><Icon name="lucide:file-pen-line" /></div>
          <h1>Что нужно написать?</h1>
          <p>Укажите тему и требования. Для курсовой или дипломной сначала составим план, затем напишем работу по разделам.</p>
          <div class="prompt-chips"><button @click="prompt = 'Напиши эссе о влиянии искусственного интеллекта на образование'">Пример эссе</button><button @click="settings.work_type='Курсовая работа'; prompt='Составь план курсовой работы по цифровой трансформации бизнеса'">Пример курсовой</button></div>
        </div>
        <article v-for="(message, index) in current.history" :key="index" class="message" :class="message.role">
          <div class="message-label">{{ message.role === 'user' ? 'Вы' : 'Авторская' }}</div>
          <div class="markdown" v-html="messageHtml(message.content)" />
        </article>
      </section>

      <div v-if="error" class="error-banner"><Icon name="lucide:circle-alert" /><span>{{ error }}</span><button @click="error=''">×</button></div>
      <form class="composer" @submit.prevent="send">
        <textarea v-model="prompt" rows="2" :placeholder="isLong ? 'Тема, задание или правки к плану…' : 'Тема, задача или правки…'" @keydown.meta.enter.prevent="send" @keydown.ctrl.enter.prevent="send" />
        <div class="composer-foot"><span>Ctrl/⌘ + Enter</span><button :disabled="!!busy || !prompt.trim()"><Icon :name="busy ? 'lucide:loader-circle' : 'lucide:arrow-up'" :class="{ spin: !!busy }" /></button></div>
      </form>
    </main>

    <aside class="settings-panel" :class="{ 'mobile-show': mobilePanel === 'settings' }">
      <div class="settings-title"><div><h2>Параметры</h2><p>Настройте форму и голос текста</p></div><button class="mobile-close" @click="mobilePanel='editor'">×</button></div>
      <label>Модель
        <select v-model="settings.model">
          <option v-for="(model, id) in meta?.models" :key="id" :value="id">{{ model.label }} — {{ model.tier }}</option>
        </select>
        <small v-if="selectedModel" class="model-rate">Ввод {{ selectedModel.prompt_cost }} ₽ · вывод {{ selectedModel.completion_cost }} ₽ за 1 млн токенов. Стоимость модели войдёт в заказ.</small>
      </label>
      <label>Тип работы<select v-model="settings.work_type"><option v-for="(_, name) in meta?.work_types" :key="name">{{ name }}</option></select><small>{{ meta?.work_types?.[settings.work_type] }}</small></label>
      <div class="field-row"><label>Язык<select v-model="settings.language"><option v-for="lang in meta?.languages" :key="lang">{{ lang }}</option></select></label><label>Объём, страниц<input v-model.number="selectedPages" type="number" min="1" :max="isLong ? 115 : 18"><small>≈ {{ selectedWords.toLocaleString('ru-RU') }} слов</small></label></div>

      <template v-if="isLong">
        <div v-if="current?.lw?.plan" class="plan-card">
          <div class="plan-head"><strong>План готов</strong><span>{{ writtenCount }}/{{ writable }} разделов</span></div>
          <ol><li v-for="(item, i) in current.lw.plan" :key="i" :class="{ chapter: item.level === 1 }"><span>{{ item.title }}</span><small v-if="item.words">{{ item.words }}</small></li></ol>
          <button v-if="!current.lw.final" class="primary-action" :disabled="!!busy" @click="writeWork">{{ writtenCount ? 'Продолжить работу' : 'Написать по плану' }}</button>
          <template v-else><label>Раздел для правки<select v-model.number="revision.index"><option v-for="(item, i) in current.lw.plan" v-show="item.words" :key="i" :value="i">{{ item.title }}</option></select></label><label>Что изменить<textarea v-model="revision.instruction" rows="3" /></label><button class="primary-action" :disabled="!!busy" @click="revise">Переписать раздел</button></template>
          <button class="text-action danger" @click="resetWork">Сбросить план</button>
        </div>
        <template v-else><label>План<select v-model="settings.plan_mode"><option value="auto">Составить автоматически</option><option value="given">У меня есть готовый</option></select></label><label v-if="settings.plan_mode === 'given'">Ваш план<textarea v-model="settings.given_plan" rows="5" /></label></template>
        <label>Данные для практической части<textarea v-model="settings.user_data" rows="4" placeholder="Показатели, выдержки, цифры…" /></label>
        <label class="toggle"><input v-model="settings.live_style_enabled" type="checkbox"><span /> Живой авторский стиль</label>
        <label v-if="settings.live_style_enabled">Промпт живого стиля<textarea v-model="settings.live_style" rows="7" /></label>
      </template>

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

    <div v-if="checkout" class="checkout-backdrop" @click.self="checkout = null">
      <section class="checkout-sheet" role="dialog" aria-modal="true" aria-labelledby="checkout-title">
        <button class="checkout-close" aria-label="Закрыть" :disabled="!!busy" @click="checkout = null">×</button>
        <div class="checkout-mark"><Icon name="lucide:receipt-text" /></div>
        <h2 id="checkout-title">Заказ готов к оплате</h2>
        <p class="checkout-topic">{{ checkout.prompt }}</p>
        <dl class="checkout-lines">
          <div v-for="line in checkout.order.breakdown" :key="line.label"><dt><strong>{{ line.label }}</strong><small v-if="line.detail">{{ line.detail }}</small></dt><dd>{{ line.amount_rub }} ₽</dd></div>
        </dl>
        <div class="checkout-total"><span>К оплате</span><strong>{{ checkout.order.amount_rub }} ₽</strong></div>
        <div class="checkout-includes"><strong>Что входит в стоимость</strong><ul><li v-for="item in checkout.order.includes" :key="item"><Icon name="lucide:check" />{{ item }}</li></ul></div>
        <button class="checkout-pay" :disabled="!!busy" @click="payAndGenerate">
          <Icon :name="busy ? 'lucide:loader-circle' : 'lucide:credit-card'" :class="{ spin: !!busy }" />
          {{ busy ? busy : `Оплатить ${checkout.order.amount_rub} ₽` }}
        </button>
        <p class="checkout-note"><Icon name="lucide:flask-conical" /> Тестовый режим — деньги не списываются</p>
      </section>
    </div>
  </div>
</template>
