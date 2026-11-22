import { proxyRequest } from 'h3'

export default defineEventHandler((event) => {
  const path = getRequestURL(event)
  const upstream = useRuntimeConfig(event).apiUpstream
  return proxyRequest(event, `${upstream}${path.pathname}${path.search}`)
})
