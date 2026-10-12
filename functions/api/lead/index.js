// 官网咨询表单「你想解决什么问题？」：写入 KV（lead_ 前缀），管理员在 /admin/ 查看。不记录 IP。
const H = { 'content-type': 'application/json; charset=UTF-8', 'cache-control': 'no-store' };
const J = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: H });
const day8 = ms => new Date(ms + 8 * 3600e3).toISOString().slice(0, 10).replace(/-/g, '');
const clip = (v, n) => String(v == null ? '' : v).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, '').trim().slice(0, n);
const rid = () => Math.random().toString(36).slice(2, 10);

export async function onRequest({ request, env }) {
  const kv = globalThis.xl_kv || (env && env.xl_kv);
  if (request.method !== 'POST') return J({ ok: false }, 405);
  if (!kv) return J({ ok: false, err: 'kv_not_bound' }, 503);
  const txt = await request.text();
  if (txt.length > 8000) return J({ ok: false }, 413);
  let d; try { d = JSON.parse(txt); } catch (e) { return J({ ok: false }, 400); }
  if (d.website) return J({ ok: true }); // 蜜罐字段：真人看不到，机器人会填
  const need = clip(d.need, 2000);
  const contact = clip(d.contact, 80);
  if (need.length < 4 || contact.length < 3) return J({ ok: false, err: 'missing' }, 400);
  const now = Date.now();
  const rec = {
    id: rid(), ts: now, day: day8(now), status: 'new',
    topic: clip(d.topic, 80), need, contact,
    src: clip(d.src, 20).replace(/[^\w.\-]/g, ''), ref: clip(d.ref, 60).replace(/[^\w.\-]/g, ''),
  };
  await kv.put('lead_' + rec.day + '_' + now.toString(36) + rec.id, JSON.stringify(rec));
  const c = Number(await kv.get('c_lead').catch(() => 0)) || 0;
  await kv.put('c_lead', String(c + 1));
  return J({ ok: true });
}
