// 小梨 Studio 调度中心：网站管任务、看进度、签对象存储链接；视频处理由 worker（小梨的电脑 / 以后的云 GPU）领任务去做。
// 存储分工：KV（xl_kv）只放索引和状态；视频、抠像、成片、episode.json 都在腾讯云 COS 私有桶。
//
// 鉴权两把钥匙（都放 EdgeOne 环境变量，不进代码）：
//   x-admin-token  = ADMIN_TOKEN   浏览器（工作台）用，什么都能做
//   x-worker-token = WORKER_TOKEN  worker 用，只能领任务 / 报进度 / 签 COS / 更新一期索引
// COS：COS_SECRET_ID / COS_SECRET_KEY（子账号，只授权这个桶）、COS_BUCKET（如 xiaoli-studio-1250000000）、COS_REGION（如 ap-shanghai）
//
//   GET  /api/studio?a=state                 一期列表 + 最近任务 + worker 在线情况         admin
//   GET  /api/studio?a=job&id=               任务详情 + 日志尾巴                          admin
//   GET  /api/studio?a=list&prefix=assets/   列 COS 里的文件（素材库、3D 序列）          admin
//   POST /api/studio {a:'job', type, ep, params}    新建任务                             admin
//   POST /api/studio {a:'cancel', id}               取消排队 / 进行中的任务               admin
//   POST /api/studio {a:'ep', id, studio}           合并更新一期索引 ep_<id>.studio        admin|worker
//   POST /api/studio {a:'sign', method, key, expires}  COS 临时签名链接                  admin|worker
//   POST /api/studio {a:'claim', worker, caps}      worker 领一个排队任务（顺带心跳）       worker
//   POST /api/studio {a:'progress', id, ...}        worker 回报进度 / 日志 / 完成 / 失败    worker
const H = { 'content-type': 'application/json; charset=UTF-8', 'cache-control': 'no-store' };
const J = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: H });

const TYPES = ['make_episode', 'replan', 'render', 'cover', 'blender', 'research', 'broll', 'sync'];
const COS_PREFIX = ['raw/', 'ep/', 'out/', 'assets/'];
const MAX_LOG = 60000; // 日志尾巴最多 60KB，远小于 KV 单值 1MB
const STALE_MS = 10 * 60 * 1000; // 任务 10 分钟没心跳 → 当作 worker 掉线，重新排队

const clean = (s, n = 96) => String(s || '').replace(/[^\w.\-]/g, '').slice(0, n);
const now = () => Date.now();
const rid = () => now().toString(36) + Math.random().toString(36).slice(2, 7);

// ---------- COS 签名（XML API v5，与官方 cos-js-sdk getAuth 一致） ----------
const enc = (s) => encodeURIComponent(s).replace(/!/g, '%21').replace(/'/g, '%27').replace(/\(/g, '%28').replace(/\)/g, '%29').replace(/\*/g, '%2A');
const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
async function hmac(key, msg) {
  const k = await crypto.subtle.importKey('raw', new TextEncoder().encode(key), { name: 'HMAC', hash: 'SHA-1' }, false, ['sign']);
  return hex(await crypto.subtle.sign('HMAC', k, new TextEncoder().encode(msg)));
}
async function sha1(msg) {
  return hex(await crypto.subtle.digest('SHA-1', new TextEncoder().encode(msg)));
}
const kvstr = (obj) => Object.keys(obj).map((k) => [enc(k).toLowerCase(), enc(String(obj[k] ?? ''))]).sort((a, b) => (a[0] > b[0] ? 1 : a[0] < b[0] ? -1 : 0));

export async function cosAuth({ id, secret, method, path, query = {}, headers = {}, start, expires = 900 }) {
  const t0 = start ?? Math.floor(now() / 1000) - 60;
  const keyTime = `${t0};${t0 + expires}`;
  const signKey = await hmac(secret, keyTime);
  const q = kvstr(query);
  const h = kvstr(headers);
  const fmt = [method.toLowerCase(), path, q.map((x) => x.join('=')).join('&'), h.map((x) => x.join('=')).join('&'), ''].join('\n');
  const sts = ['sha1', keyTime, await sha1(fmt), ''].join('\n');
  const sig = await hmac(signKey, sts);
  return [
    'q-sign-algorithm=sha1', `q-ak=${id}`, `q-sign-time=${keyTime}`, `q-key-time=${keyTime}`,
    `q-header-list=${h.map((x) => x[0]).join(';')}`, `q-url-param-list=${q.map((x) => x[0]).join(';')}`, `q-signature=${sig}`,
  ].join('&');
}

function cosCfg(env) {
  const g = (k) => (env && env[k]) || globalThis[k] || '';
  const c = { id: g('COS_SECRET_ID'), secret: g('COS_SECRET_KEY'), bucket: g('COS_BUCKET'), region: g('COS_REGION') };
  c.ok = !!(c.id && c.secret && c.bucket && c.region);
  c.host = `${c.bucket}.cos.${c.region}.myqcloud.com`;
  return c;
}

async function signUrl(cfg, method, key, expires = 3600) {
  const path = '/' + key.replace(/^\/+/, '');
  const auth = await cosAuth({ id: cfg.id, secret: cfg.secret, method, path, headers: { host: cfg.host }, expires });
  const encPath = path.split('/').map(enc).join('/');
  return `https://${cfg.host}${encPath}?${auth.split('&').map((kv) => { const i = kv.indexOf('='); return kv.slice(0, i) + '=' + enc(kv.slice(i + 1)); }).join('&')}`;
}

async function cosList(cfg, prefix, marker = '') {
  const query = { prefix, 'max-keys': '1000' };
  if (marker) query.marker = marker;
  const auth = await cosAuth({ id: cfg.id, secret: cfg.secret, method: 'get', path: '/', query, headers: { host: cfg.host }, expires: 300 });
  const qs = Object.keys(query).map((k) => `${enc(k)}=${enc(query[k])}`).join('&');
  const r = await fetch(`https://${cfg.host}/?${qs}`, { headers: { Authorization: auth } });
  const xml = await r.text();
  if (!r.ok) throw new Error('cos_list_' + r.status);
  const items = [...xml.matchAll(/<Contents>([\s\S]*?)<\/Contents>/g)].map((m) => {
    const t = (n) => ((m[1].match(new RegExp(`<${n}>([\\s\\S]*?)</${n}>`)) || [])[1] || '');
    return { key: t('Key'), size: +t('Size'), mtime: t('LastModified') };
  });
  const truncated = /<IsTruncated>true<\/IsTruncated>/.test(xml);
  const next = (xml.match(/<NextMarker>([\s\S]*?)<\/NextMarker>/) || [])[1] || (truncated && items.length ? items[items.length - 1].key : '');
  return { items, next: truncated ? next : '' };
}

// ---------- KV 小工具 ----------
async function listAll(kv, prefix, cap = 600) {
  const out = []; let cursor; let guard = 0;
  do {
    const opt = { prefix, limit: 256 }; if (cursor) opt.cursor = cursor;
    const page = await kv.list(opt);
    const keys = (page && page.keys) || [];
    const vals = await Promise.all(keys.map((k) => kv.get(k.key, { type: 'json' }).catch(() => null)));
    vals.forEach((v, i) => { if (v && typeof v === 'object') out.push(Object.assign({ _k: keys[i].key }, v)); });
    cursor = (page.complete || keys.length < 256) ? null : (page.cursor || keys[keys.length - 1].key);
  } while (cursor && out.length < cap && ++guard < 8);
  return out;
}
const getJ = (kv, k) => kv.get(k, { type: 'json' }).catch(() => null);
const putJ = (kv, k, v) => kv.put(k, JSON.stringify(v));

export async function onRequest({ request, env }) {
  const kv = globalThis.xl_kv || (env && env.xl_kv);
  const admin = (env && env.ADMIN_TOKEN) || globalThis.ADMIN_TOKEN || '';
  const worker = (env && env.WORKER_TOKEN) || globalThis.WORKER_TOKEN || '';
  const u = new URL(request.url);
  const isAdmin = admin.length >= 12 && (request.headers.get('x-admin-token') || '') === admin;
  const isWorker = worker.length >= 16 && (request.headers.get('x-worker-token') || '') === worker;
  if (!isAdmin && !isWorker) return J({ ok: false, err: 'auth' }, 403);
  if (!kv) return J({ ok: false, err: 'kv_not_bound' }, 503);
  const cos = cosCfg(env);

  try {
    if (request.method === 'GET') {
      const a = u.searchParams.get('a');
      if (!isAdmin) return J({ ok: false, err: 'auth' }, 403);
      if (a === 'state') {
        const [eps, jobs, wks] = await Promise.all([listAll(kv, 'ep_'), listAll(kv, 'job_', 300), listAll(kv, 'wk_')]);
        jobs.sort((x, y) => (y.ts || 0) - (x.ts || 0));
        return J({
          ok: true, cos: cos.ok,
          episodes: eps.filter((e) => e.studio).map((e) => ({ id: e._k.slice(3), title: e.title || e.studio.title || e._k.slice(3), studio: e.studio, ts_up: e.ts_up })),
          jobs: jobs.slice(0, 60),
          workers: wks.map((w) => ({ ...w, online: now() - (w.seen || 0) < 90 * 1000 })),
        });
      }
      if (a === 'job') {
        const id = clean(u.searchParams.get('id'));
        const [job, log] = await Promise.all([getJ(kv, 'job_' + id), kv.get('jlog_' + id).catch(() => '')]);
        return job ? J({ ok: true, job, log: log || '' }) : J({ ok: false, err: 'not_found' }, 404);
      }
      if (a === 'list') {
        if (!cos.ok) return J({ ok: false, err: 'cos_not_configured' }, 503);
        const prefix = String(u.searchParams.get('prefix') || '');
        if (!COS_PREFIX.some((p) => prefix.startsWith(p))) return J({ ok: false, err: 'prefix' }, 400);
        const r = await cosList(cos, prefix, u.searchParams.get('marker') || '');
        return J({ ok: true, ...r });
      }
      return J({ ok: false, err: 'action' }, 400);
    }

    if (request.method !== 'POST') return J({ ok: false }, 405);
    const txt = await request.text();
    if (txt.length > 200000) return J({ ok: false, err: 'too_large' }, 413);
    let d; try { d = JSON.parse(txt); } catch (e) { return J({ ok: false, err: 'json' }, 400); }
    const a = d.a;

    if (a === 'sign') {
      if (!cos.ok) return J({ ok: false, err: 'cos_not_configured' }, 503);
      const method = String(d.method || 'GET').toUpperCase();
      if (!['GET', 'PUT', 'HEAD'].includes(method)) return J({ ok: false, err: 'method' }, 400);
      const exp = Math.min(Math.max(+d.expires || 3600, 60), 6 * 3600);
      const norm = (k) => String(k || '').replace(/^\/+/, '');
      // 浏览器只能往 raw/（原片稿子）、assets/（素材）、ep/*/episode.json（画面计划）写；worker 什么都能写
      const okKey = (k) => k.length <= 400 && !k.includes('..') && COS_PREFIX.some((p) => k.startsWith(p)) &&
        (method !== 'PUT' || isWorker || k.startsWith('raw/') || k.startsWith('assets/') || /^ep\/[\w.\-]+\/episode\.json$/.test(k));
      if (Array.isArray(d.keys)) {
        const keys = d.keys.slice(0, 300).map(norm);
        const bad = keys.find((k) => !okKey(k));
        if (bad !== undefined) return J({ ok: false, err: 'key', key: bad.slice(0, 120) }, 400);
        const urls = {};
        for (const k of keys) urls[k] = await signUrl(cos, method, k, exp);
        return J({ ok: true, urls });
      }
      const key = norm(d.key);
      if (!okKey(key)) return J({ ok: false, err: 'key' }, 400);
      return J({ ok: true, url: await signUrl(cos, method, key, exp) });
    }

    if (a === 'ep') {
      const id = clean(d.id, 40);
      if (id.length < 2) return J({ ok: false, err: 'id' }, 400);
      const old = (await getJ(kv, 'ep_' + id)) || {};
      const studio = Object.assign({}, old.studio || {}, d.studio || {});
      const rec = Object.assign(old, { studio, ts_up: now() });
      if (!rec.title && studio.title) rec.title = studio.title;
      const s = JSON.stringify(rec);
      if (s.length > 16000) return J({ ok: false, err: 'too_large' }, 413);
      await kv.put('ep_' + id, s);
      return J({ ok: true });
    }

    if (a === 'job') {
      if (!isAdmin) return J({ ok: false, err: 'auth' }, 403);
      if (!TYPES.includes(d.type)) return J({ ok: false, err: 'type' }, 400);
      const id = rid();
      const job = { id, type: d.type, ep: clean(d.ep, 40), params: d.params || {}, status: 'queued', pct: 0, msg: '排队中', ts: now(), ts_up: now() };
      const s = JSON.stringify(job);
      if (s.length > 16000) return J({ ok: false, err: 'too_large' }, 413);
      await kv.put('job_' + id, s);
      return J({ ok: true, job });
    }

    if (a === 'cancel') {
      if (!isAdmin) return J({ ok: false, err: 'auth' }, 403);
      const id = clean(d.id);
      const job = await getJ(kv, 'job_' + id);
      if (!job) return J({ ok: false, err: 'not_found' }, 404);
      if (['done', 'failed', 'canceled'].includes(job.status)) return J({ ok: true, job });
      job.status = job.status === 'queued' ? 'canceled' : 'canceling';
      job.ts_up = now();
      await putJ(kv, 'job_' + id, job);
      return J({ ok: true, job });
    }

    if (a === 'claim') {
      if (!isWorker) return J({ ok: false, err: 'auth' }, 403);
      const name = clean(d.worker, 40) || 'worker';
      await putJ(kv, 'wk_' + name, { name, seen: now(), caps: d.caps || {}, ver: String(d.ver || '').slice(0, 20), busy: !!d.busy });
      if (d.busy) return J({ ok: true, job: null });
      const jobs = await listAll(kv, 'job_', 300);
      const t = now();
      // 掉线回收：进行中但太久没心跳的任务重新排队
      for (const j of jobs) {
        if (j.status === 'running' && t - (j.ts_up || 0) > STALE_MS) { j.status = 'queued'; j.msg = '上一台 worker 掉线，重新排队'; j.worker = ''; await putJ(kv, j._k, j); }
      }
      const caps = d.caps || {};
      const q = jobs.filter((j) => j.status === 'queued' && (!caps.types || caps.types.includes(j.type))).sort((x, y) => x.ts - y.ts);
      for (const j of q) {
        const key = j._k; delete j._k;
        const lease = rid();
        j.status = 'running'; j.worker = name; j.lease = lease; j.msg = '已领取'; j.ts_start = t; j.ts_up = t;
        await putJ(kv, key, j);
        const back = await getJ(kv, key); // KV 没有事务：写完再读一次，确认是自己领到的
        if (back && back.lease === lease) return J({ ok: true, job: back });
      }
      return J({ ok: true, job: null });
    }

    if (a === 'progress') {
      if (!isWorker) return J({ ok: false, err: 'auth' }, 403);
      const id = clean(d.id);
      const job = await getJ(kv, 'job_' + id);
      if (!job) return J({ ok: false, err: 'not_found' }, 404);
      if (d.lease && job.lease && d.lease !== job.lease) return J({ ok: false, err: 'lease_lost' }, 409);
      if (typeof d.pct === 'number') job.pct = Math.max(0, Math.min(100, d.pct));
      if (d.msg) job.msg = String(d.msg).slice(0, 200);
      if (d.result && typeof d.result === 'object') job.result = d.result;
      if (['done', 'failed', 'canceled'].includes(d.status)) { job.status = d.status; job.ts_end = now(); }
      job.ts_up = now();
      if (typeof d.log === 'string') await kv.put('jlog_' + id, d.log.slice(-MAX_LOG));
      await putJ(kv, 'job_' + id, job);
      return J({ ok: true, cancel: job.status === 'canceling' });
    }

    return J({ ok: false, err: 'action' }, 400);
  } catch (e) {
    return J({ ok: false, err: String((e && e.message) || e).slice(0, 200) }, 500);
  }
}
