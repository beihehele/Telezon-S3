import { http } from '@/api/http'

export async function presignGet(bucket: string, key: string, expiresIn = 3600) {
  const { data } = await http.post<{ url: string }>('/v1/presign/', {
    bucket,
    key,
    method: 'GET',
    expires_in: expiresIn,
  })
  return data.url
}

export async function presignPut(bucket: string, key: string, expiresIn = 3600) {
  const { data } = await http.post<{ url: string }>('/v1/presign/', {
    bucket,
    key,
    method: 'PUT',
    expires_in: expiresIn,
  })
  return data.url
}

function objectPath(bucket: string, key: string) {
  const encKey = key.split('/').map(encodeURIComponent).join('/')
  return `/v1/buckets/${encodeURIComponent(bucket)}/objects/${encKey}`
}

export async function createContentTicket(bucket: string, key: string, expiresIn = 600) {
  const { data } = await http.post<{ media_token: string; expires_in: number }>(
    `${objectPath(bucket, key)}/content-ticket`,
    null,
    { params: { expires_in: expiresIn } },
  )
  return data.media_token
}

export function contentUrl(
  bucket: string,
  key: string,
  inline = true,
  mediaToken?: string | null,
) {
  const q = new URLSearchParams({ disposition: inline ? 'inline' : 'attachment' })
  if (mediaToken) {
    q.set('media_token', mediaToken)
  }
  return `/api${objectPath(bucket, key)}/content?${q}`
}
