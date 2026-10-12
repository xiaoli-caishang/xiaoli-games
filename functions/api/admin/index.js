// 工作台读写接口（仅管理员）。资产、任务、花期、产品、账号指标、播种记录都走这里，统一存 KV（xl_kv）。
// 鉴权：请求头 x-admin-token（或 ?token=）等于 EdgeOne 环境变量 ADMIN_TOKEN。口令不写进代码、不写进 Git。
//   GET  /api/admin?prefix=asset_            列出某前缀下全部记录（自动翻页，最多 2000 条）
//   POST /api/admin  {op:'put',   key, val}   新建 / 整体覆盖一条记录
//   POST /api/admin  {op:'patch', key, val}   合并更新（lead_ 只允许改 status/note/amount/ep）
//   POST /api/admin  {op:'del',   key}        删除（只能删工作台自己的前缀，游戏记录和线索不能删）
const H = { 'content-type': 'application/json; charset=UTF-8', 'cache-control': 'no-store' };
const J = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: H });
// 工作台可写的前缀；lead_ 只能 patch；r_ e_ c_ 只读（走 /api/export）
const WRITE = ['asset_', 'task_', 'ep_', 'prod_', 'agent_', 'run_', 'metric_', 'acct_', 'note_'];
const READ = WRITE.concat(['lead_', 'r_', 'e_fp_', 'c_']);
const LEAD_FIELDS = ['status', 'note', 'amount', 'ep'];
const MAX_VAL = 16000;

export async function onRequest({ request, env }) {
  const kv = globalThis.xl_kv || (env && env.xl_kv);
  const tok = (env && env.ADMIN_TOKEN) || globalThis.ADMIN_TOKEN || '';
  const u = new URL(request.url);
  const given = request.headers.get('x-admin-token') || u.searchParams.get('token') || '';
  if (!tok || tok.length < 12 || given !== tok) return J({ ok: false, err: 'auth' }, 403);
  if (!kv) return J({ ok: false, err: 'kv_not_bound' }, 503);

  if (request.method === 'GET') {
    const prefix = (u.searchParams.get('prefix') || '').replace(/[^\w.\-]/g, '');
    if (!READ.some(p => prefix.startsWith(p))) return J({ ok: false, err: 'prefix' }, 400);
    const items = []; let cursor; let guard = 0;
    do {
      const opt = { prefix, limit: 256 }; if (cursor) opt.cursor = cursor;
      const page = await kv.list(opt);
      const keys = (page && page.keys) || [];
      const vals = await Promise.all(keys.map(k => kv.get(k.key, { type: 'json' }).catch(() => null)));
      vals.forEach((v, i) => { if (v && typeof v === 'object') items.push(Object.assign({ _k: keys[i].key }, v)); });
      // 没满一页就说明到底了；否则用返回的 cursor（没有就用最后一个 key）继续翻
      cursor = (page.complete || keys.length < 256) ? null : (page.cursor || keys[keys.length - 1].key);
    } while (cursor && ++guard < 8);
    return J({ ok: true, items });
  }

  if (request.method !== 'POST') return J({ ok: false }, 405);
  const txt = await request.text();
  if (txt.length > MAX_VAL + 400) return J({ ok: false, err: 'too_large' }, 413);
  let d; try { d = JSON.parse(txt); } catch (e) { return J({ ok: false, err: 'json' }, 400); }
  const key = String(d.key || '').replace(/[^\w.\-]/g, '').slice(0, 96);
  if (key.length < 4) return J({ ok: false, err: 'key' }, 400);
  const op = d.op;
  const writable = WRITE.some(p => key.startsWith(p));
  const isLead = key.startsWith('lead_');

  if (op === 'del') {
    if (!writable) return J({ ok: false, err: 'readonly' }, 403);
    await kv.delete(key);
    return J({ ok: true });
  }
  if (op !== 'put' && op !== 'patch') return J({ ok: false, err: 'op' }, 400);
  if (!writable && !(isLead && op === 'patch')) return J({ ok: false, err: 'readonly' }, 403);
  let val = d.val;
  if (!val || typeof val !== 'object' || Array.isArray(val)) return J({ ok: false, err: 'val' }, 400);
  delete val._k;
  if (isLead) {
    const clean = {}; for (const f of LEAD_FIELDS) if (f in val) clean[f] = val[f];
    val = clean;
  }
  let rec = val;
  if (op === 'patch') {
    const old = (await kv.get(key, { type: 'json' }).catch(() => null)) || {};
    rec = Object.assign(old, val);
  }
  rec.ts_up = Date.now();
  const s = JSON.stringify(rec);
  if (s.length > MAX_VAL) return J({ ok: false, err: 'too_large' }, 413);
  await kv.put(key, s);
  return J({ ok: true, key, val: rec });
}
