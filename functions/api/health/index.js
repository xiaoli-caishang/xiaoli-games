// 部署自检：/api/health。只返回“有没有配好”，不返回任何口令或数据内容。
const H = { 'content-type': 'application/json; charset=UTF-8', 'cache-control': 'no-store' };
export async function onRequest({ env }) {
  const kv = globalThis.xl_kv || (env && env.xl_kv);
  const tok = (env && env.ADMIN_TOKEN) || globalThis.ADMIN_TOKEN || '';
  let kvOk = false, kvErr = '';
  if (kv) {
    try { await kv.get('c_start'); kvOk = true; } catch (e) { kvErr = String(e && e.message || e).slice(0, 120); }
  } else kvErr = 'kv_not_bound';
  return new Response(JSON.stringify({
    ok: kvOk && tok.length >= 12,
    kv: kvOk, kv_err: kvErr || undefined,
    admin_token: tok.length >= 12,
    time: new Date().toISOString(),
  }), { headers: H });
}
