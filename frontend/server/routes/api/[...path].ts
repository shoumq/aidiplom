import { proxyRequest } from 'h3'

export default defineEventHandler((event) => {
  const path = event.context.params?.path || ''
  const requestUrl = getRequestURL(event)
  return proxyRequest(event, `http://backend:8000/api/${path}${requestUrl.search}`)
})
