import type { Chat, ChatSummary, Order, Settings, User } from '~/types'

export const useWriterApi = () => {
  const config = useRuntimeConfig()
  const api = <T>(path: string, options: any = {}) => $fetch<T>(`${config.public.apiBase}${path}`, { credentials: 'include', ...options })
  return {
    me: () => api<User>('/auth/me'),
    register: (body: { email: string; password: string; privacy_accepted: boolean; privacy_version?: string; offer_version?: string; referral_code: string }) => api<User>('/auth/register', { method: 'POST', body }),
    login: (email: string, password: string) => api<User>('/auth/login', { method: 'POST', body: { email, password } }),
    logout: () => api('/auth/logout', { method: 'POST' }),
    deleteAccount: () => api('/account', { method: 'DELETE' }),
    meta: () => api<any>('/meta'),
    chats: () => api<ChatSummary[]>('/chats'),
    chat: (id: string) => api<Chat>(`/chats/${id}`),
    create: (work_type = 'Эссе') => api<Chat>('/chats', { method: 'POST', body: { work_type } }),
    remove: (id: string) => api(`/chats/${id}`, { method: 'DELETE' }),
    quote: (chat_id: string, prompt: string, settings: Settings) => api<Order>('/orders/quote', { method: 'POST', body: { chat_id, prompt, settings } }),
    order: (id: string) => api<Order>(`/orders/${id}`),
    pay: (orderId: string, credit_rub: number, offer_version?: string) => api<Order>(`/orders/${orderId}/pay`, { method: 'POST', body: { credit_rub, offer_version } }),
    send: (id: string, prompt: string, settings: Settings, order_id: string) => api<Chat>(`/chats/${id}/messages`, { method: 'POST', body: { prompt, settings, order_id } }),
    write: (id: string, settings: Settings, section_indices?: number[]) => api<Chat>(`/chats/${id}/write`, { method: 'POST', body: { settings, section_indices } }),
    revise: (id: string, section_index: number, instruction: string, settings: Settings) => api<Chat>(`/chats/${id}/revise`, { method: 'POST', body: { section_index, instruction, settings } }),
    reset: (id: string) => api<Chat>(`/chats/${id}/work`, { method: 'DELETE' }),
    download: (id: string, kind: 'md' | 'docx') => `${config.public.apiBase}/chats/${id}/download/${kind}`
  }
}
