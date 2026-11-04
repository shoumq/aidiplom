export type Message = { role: 'user' | 'assistant'; content: string; api: string }
export type PlanItem = { title: string; level: number; words: number; brief: string }
export type Chat = { id: string; title: string; work_type: string; history: Message[]; fetched: Record<string, [string, string]>; lw: { topic?: string; plan?: PlanItem[]; written?: Record<string, [string, string]>; final?: string } }
export type ChatSummary = Pick<Chat, 'id' | 'title' | 'work_type'>
export type Settings = { model: string; work_type: string; language: string; words: number; total_words: number; style: string; style_sample: string; extra: string; rewrite_level: number; use_search: boolean; links: string[]; plan_mode: 'auto' | 'given'; given_plan: string; user_data: string; live_style_enabled: boolean; live_style: string }
export type User = { id: string; email: string }
export type OrderLine = { label: string; detail?: string; amount_rub: number }
export type Order = { id: string; chat_id: string; work_type: string; words: number; pages: number; amount_rub: number; status: 'awaiting_payment' | 'paid' | 'generating' | 'completed' | 'expired'; expires_at: number; breakdown: OrderLine[]; includes: string[]; payment_mode: 'mock' }
