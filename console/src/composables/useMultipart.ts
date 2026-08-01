import { http } from '@/api/http'

const DEFAULT_PART = 8 * 1024 * 1024

async function presign(
  bucket: string,
  key: string,
  method: string,
  query: Record<string, string>,
) {
  const { data } = await http.post<{ url: string }>('/v1/presign/', {
    bucket,
    key,
    method,
    expires_in: 3600,
    query,
  })
  return data.url
}

function parseUploadId(xml: string): string {
  const m = xml.match(/<UploadId>([^<]+)<\/UploadId>/)
  if (!m) {
    throw new Error('无法解析 UploadId')
  }
  return m[1]
}

export async function uploadMultipart(
  bucket: string,
  key: string,
  file: File,
  partSize = DEFAULT_PART,
  onProgress?: (pct: number) => void,
) {
  const initUrl = await presign(bucket, key, 'POST', { uploads: '' })
  const initRes = await fetch(initUrl, { method: 'POST' })
  if (!initRes.ok) {
    throw new Error('初始化分片上传失败')
  }
  const uploadId = parseUploadId(await initRes.text())
  const parts: { partNumber: number; etag: string }[] = []
  let offset = 0
  let partNumber = 1
  while (offset < file.size) {
    const end = Math.min(offset + partSize, file.size)
    const chunk = file.slice(offset, end)
    const url = await presign(bucket, key, 'PUT', {
      uploadId,
      partNumber: String(partNumber),
    })
    const res = await fetch(url, { method: 'PUT', body: chunk })
    if (!res.ok) {
      throw new Error(`分片 ${partNumber} 上传失败`)
    }
    const etag = res.headers.get('etag') || res.headers.get('ETag') || ''
    parts.push({ partNumber, etag })
    offset = end
    partNumber += 1
    onProgress?.(Math.min(100, Math.round((offset / file.size) * 100)))
  }
  const completeXml =
    '<CompleteMultipartUpload>' +
    parts
      .map(
        (p) =>
          `<Part><PartNumber>${p.partNumber}</PartNumber><ETag>${p.etag}</ETag></Part>`,
      )
      .join('') +
    '</CompleteMultipartUpload>'
  const completeUrl = await presign(bucket, key, 'POST', { uploadId })
  const done = await fetch(completeUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/xml' },
    body: completeXml,
  })
  if (!done.ok) {
    throw new Error('完成分片上传失败')
  }
}
