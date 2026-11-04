import type { Chat, ChatSummary, Order, Settings, User } from '~/types'

export const useWriterApi = () => {
  const config = useRuntimeConfig()
  const api = <T>(path: string, options: any = {}) => $fetch<T>(`${config.public.apiBase}${path}`, { credentials: 'include', ...options })
  return {
    me: () => api<User>('/auth/me'),
    register: (email: string, password: string, privacy_accepted: boolean) => api<User>('/auth/register', { method: 'POST', body: { email, password, privacy_accepted } }),
    login: (email: string, password: string) => api<User>('/auth/login', { method: 'POST', body: { email, password } }),
    logout: () => api('/auth/logout', { method: 'POST' }),
    deleteAccount: () => api('/account', { method: 'DELETE' }),
    exportAccount: () => `${config.public.apiBase}/account/export`,
    meta: () => api<any>('/meta'),
    chats: () => api<ChatSummary[]>('/chats'),
    chat: (id: string) => api<Chat>(`/chats/${id}`),
    create: (work_type = 'Эссе') => api<Chat>('/chats', { method: 'POST', body: { work_type } }),
    remove: (id: string) => api(`/chats/${id}`, { method: 'DELETE' }),
    quote: (chat_id: string, prompt: string, settings: Settings) => api<Order>('/orders/quote', { method: 'POST', body: { chat_id, prompt, settings } }),
    mockPay: (orderId: string) => api<Order>(`/orders/${orderId}/mock-pay`, { method: 'POST' }),
    send: (id: string, prompt: string, settings: Settings, order_id: string) => api<Chat>(`/chats/${id}/messages`, { method: 'POST', body: { prompt, settings, order_id } }),
    write: (id: string, settings: Settings) => api<Chat>(`/chats/${id}/write`, { method: 'POST', body: { settings } }),
    revise: (id: string, section_index: number, instruction: string, settings: Settings) => api<Chat>(`/chats/${id}/revise`, { method: 'POST', body: { section_index, instruction, settings } }),
    reset: (id: string) => api<Chat>(`/chats/${id}/work`, { method: 'DELETE' }),
    download: (id: string, kind: 'md' | 'docx') => `${config.public.apiBase}/chats/${id}/download/${kind}`
  }
}
