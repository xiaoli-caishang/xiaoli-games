// 通用游戏事件（量化基金生存录继续用 /api/log）。键：e_<游戏>_<日期>_<局id>。不记录 IP 和个人信息。
const H = { 'content-type': 'application/json; charset=UTF-8', 'cache-control': 'no-store' };
const J = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: H });
const day8 = ms => new Date(ms + 8 * 3600e3).toISOString().slice(0, 10).replace(/-/g, '');
const str = (v, n, re) => String(v == null ? '' : v).replace(re || /[^\w.\-]/g, '').slice(0, n);
const num = (v, lo, hi) => { const x = Number(v); return Number.isFinite(x) ? Math.min(hi, Math.max(lo, x)) : null; };

// 每个游戏允许的事件和结果字段；新增游戏在这里登记
const GAMES = {
  fp: { evs: ['start', 'end', 'poster', 'pair'], code: /[^RSDILTCM]/g, codeLen: 4 },
  // 你给未来的自己打几折：类型(P/E/N/S)+末题延迟档位(2位)+环境条数+是否反转+可靠感
  fd: { evs: ['start', 'end'], code: /[^A-Z0-9]/g, codeLen: 6 },
};

export async function onRequest({ request, env }) {
  const kv = globalThis.xl_kv || (env && env.xl_kv);
  if (request.method !== 'POST') return J({ ok: false }, 405);
  if (!kv) return J({ ok: false, err: 'kv_not_bound' });
  const txt = await request.text();
  if (txt.length > 2000) return J({ ok: false }, 413);
  let d; try { d = JSON.parse(txt); } catch (e) { return J({ ok: false }, 400); }
  const g = GAMES[d.g] ? d.g : null;
  if (!g) return J({ ok: false }, 400);
  const G = GAMES[g];
  const id = str(d.id, 16, /[^a-z0-9]/g);
  if (id.length < 8) return J({ ok: false }, 400);
  const ev = G.evs.includes(d.ev) ? d.ev : null;
  if (!ev) return J({ ok: false }, 400);

  const now = Date.now();
  const t0 = Math.abs(Number(d.t0) - now) < 2 * 86400e3 ? Number(d.t0) : now;
  const key = 'e_' + g + '_' + day8(t0) + '_' + id;
  const old = (await kv.get(key, { type: 'json' }).catch(() => null)) || {};
  const prevEv = old.ev, first = !prevEv;
  const rec = Object.assign(old, { g, id, ts: now });
  if (first) Object.assign(rec, { t0, day: day8(t0) });
  // 只用新事件里确实带了的值更新，避免后到的事件把已记下的渠道、模式、用时清空
  const fields = { v: str(d.v, 8), src: str(d.src, 20), ref: str(d.ref, 60), dev: str(d.dev, 1), mode: str(d.mode, 3, /[^a-z]/g) };
  for (const [k, v] of Object.entries(fields)) if (v) rec[k] = v;
  if (first) rec.ev = ev;
  if (ev === 'end' && prevEv !== 'end') {
    rec.ev = 'end'; rec.code = str(d.code, G.codeLen, G.code);
    const dur = num(d.dur, 0, 86400); if (dur != null) rec.dur = dur;
  }
  if (ev === 'poster') rec.posters = (old.posters || 0) + 1;
  if (ev === 'pair') rec.pair = 1;
  await kv.put(key, JSON.stringify(rec));

  if (ev === 'start' && first) {
    const c = Number(await kv.get('c_' + g + '_start').catch(() => 0)) || 0;
    await kv.put('c_' + g + '_start', String(c + 1));
  }
  if (ev === 'end' && prevEv !== 'end') {
    const c = Number(await kv.get('c_' + g + '_end').catch(() => 0)) || 0;
    await kv.put('c_' + g + '_end', String(c + 1));
  }
  return J({ ok: true });
}
