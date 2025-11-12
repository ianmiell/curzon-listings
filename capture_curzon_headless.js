// capture_curzon_headless.js
// Visit https://www.curzon.com/ headless, capture network traffic and extract bearer tokens & correlation ids.
// Output: curzon_tokens.json

const fs = require('fs');
const puppeteer = require('puppeteer');
console.log('Using puppeteer version', puppeteer.version);

const STORE_KEY = 'VistaOmnichannelComponents::browsing-domain-store';
const SITE_ALLOWLIST = new Set(['MAY1', 'BLO1', 'CAM1', 'HOX1', 'SOH1', 'ALD1', 'VIC1']);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

const slugifySite = (name = '', fallback = '') =>
  name
    .toLowerCase()
    .replace(/&/g, 'and')
    .replace(/[^a-z0-9\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-') || fallback.toLowerCase();

const mergeKeyedEntries = (target = {}, source = {}) => {
  if (!target || typeof target !== 'object') return;
  if (!source || typeof source !== 'object') return;
  for (const [key, value] of Object.entries(source)) {
    if (value === undefined || value === null) continue;
    target[key] = value;
  }
};

const filterStoreBySiteIds = (store, allowedSites) => {
  if (!store || !allowedSites?.size) return;

  if (store.allSiteIds?.payload && Array.isArray(store.allSiteIds.payload)) {
    store.allSiteIds.payload = store.allSiteIds.payload.filter(siteId =>
      allowedSites.has(siteId)
    );
  }

  if (store.sitesById) {
    store.sitesById = Object.fromEntries(
      Object.entries(store.sitesById).filter(([siteId]) => allowedSites.has(siteId))
    );
  }

  if (store.showtimesById) {
    store.showtimesById = Object.fromEntries(
      Object.entries(store.showtimesById).filter(([, entry]) =>
        allowedSites.has(entry?.payload?.siteId)
      )
    );
  }

  const filmIdsInUse = new Set();
  for (const entry of Object.values(store.showtimesById || {})) {
    const filmId = entry?.payload?.filmId;
    if (filmId) filmIdsInUse.add(filmId);
  }
  if (store.filmsById) {
    store.filmsById = Object.fromEntries(
      Object.entries(store.filmsById).filter(([filmId]) => filmIdsInUse.has(filmId))
    );
  }
};

const enrichBrowsingStoreAcrossSites = async (page, found) => {
  if (!found?.localStorage?.[STORE_KEY]) return;

  let aggregated;
  try {
    aggregated = JSON.parse(found.localStorage[STORE_KEY]);
  } catch (err) {
    console.warn('Failed to parse initial browsing-domain-store', err);
    return;
  }

  const siteIds =
    aggregated?.allSiteIds?.payload && Array.isArray(aggregated.allSiteIds.payload)
      ? aggregated.allSiteIds.payload.filter(Boolean)
      : [];
  const targetSiteIds = siteIds.filter(siteId => SITE_ALLOWLIST.has(siteId));
  if (!targetSiteIds.length) return;

  const sitesById = aggregated.sitesById || {};
  const slugBySite = {};
  for (const [siteId, siteData] of Object.entries(sitesById)) {
    const name = siteData?.payload?.name?.text;
    slugBySite[siteId] = slugifySite(name, siteId);
  }

  const sitesWithShowtimes = new Set();
  if (aggregated.showtimesById) {
    for (const entry of Object.values(aggregated.showtimesById)) {
      const siteId = entry?.payload?.siteId;
      if (siteId && SITE_ALLOWLIST.has(siteId)) sitesWithShowtimes.add(siteId);
    }
  }

  const missingSiteIds = targetSiteIds.filter(siteId => !sitesWithShowtimes.has(siteId));
  if (!missingSiteIds.length) return;

  console.log(`Aggregating showtimes for ${missingSiteIds.length} additional site(s).`);

  for (const siteId of missingSiteIds) {
    const slug = slugBySite[siteId];
    if (!slug) {
      console.warn(`Skipping ${siteId}: unable to derive slug.`);
      continue;
    }
    const url = `https://www.curzon.com/venues/${slug}/`;
    console.log(`Visiting ${siteId} -> ${url}`);
    try {
      await page.goto(url, { waitUntil: 'networkidle2' });
      await sleep(3000);
      const storeString = await page.evaluate(key => localStorage.getItem(key), STORE_KEY);
      if (!storeString) {
        console.warn(`No store content for ${siteId}`);
        sitesWithShowtimes.add(siteId);
        continue;
      }
      let siteStore;
      try {
        siteStore = JSON.parse(storeString);
      } catch (err) {
        console.warn(`Invalid store JSON for ${siteId}`, err);
        sitesWithShowtimes.add(siteId);
        continue;
      }
      aggregated.filmsById = aggregated.filmsById || {};
      aggregated.showtimesById = aggregated.showtimesById || {};
      mergeKeyedEntries(aggregated.filmsById, siteStore.filmsById);
      mergeKeyedEntries(aggregated.showtimesById, siteStore.showtimesById);
      sitesWithShowtimes.add(siteId);
    } catch (err) {
      console.warn(`Failed to capture site ${siteId}`, err);
    }
  }

  filterStoreBySiteIds(aggregated, SITE_ALLOWLIST);

  const mergedStoreString = JSON.stringify(aggregated);
  found.localStorage = found.localStorage || {};
  found.localStorage[STORE_KEY] = mergedStoreString;

  if (!Array.isArray(found.bearerTokens)) found.bearerTokens = [];
  const storeEntry = found.bearerTokens.find(entry => entry.key === STORE_KEY);
  if (storeEntry) {
    storeEntry.value = mergedStoreString;
  } else {
    found.bearerTokens.push({
      source: 'localStorage',
      key: STORE_KEY,
      value: mergedStoreString,
      timestamp: new Date().toISOString()
    });
  }
};

(async () => {
  const OUT = 'curzon_tokens.json';
  const TARGET = 'https://www.curzon.com/venues/aldgate/';
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();
  page.setDefaultNavigationTimeout(120000);

  const found = {
    capturedAt: new Date().toISOString(),
    url: TARGET,
    bearerTokens: [],      // {source:'request'|'response'|'cookie'|'storage'|'response-json', value, url, headerName, timestamp}
    correlationIds: [],    // {headerName, value, url, direction, timestamp}
    cookies: [],
    localStorage: {},
    sessionStorage: {},
    requests: []
  };

  const pushUnique = (arr, item, key = JSON.stringify) => {
    const k = key(item);
    if (!arr.some(x => key(x) === k)) arr.push(item);
  };

  // Inspect outgoing requests
  page.on('request', req => {
    try {
      const url = req.url();
      const method = req.method();
      const headers = req.headers();
      const ts = new Date().toISOString();
      found.requests.push({ type: 'request', url, method, timestamp: ts });

      if (headers.authorization && /bearer\s+/i.test(headers.authorization)) {
        pushUnique(found.bearerTokens, {
          source: 'request-header',
          headerName: 'authorization',
          value: headers.authorization,
          url, timestamp: ts
        }, i => `${i.source}|${i.value}|${i.url}`);
      }

      for (const name of Object.keys(headers || {})) {
        if (/correl|x-request-id|x-correlation|request-id|x-trace-id/i.test(name)) {
          pushUnique(found.correlationIds, {
            headerName: name,
            value: headers[name],
            url,
            direction: 'request',
            timestamp: ts
          }, i => `${i.headerName}|${i.value}|${i.url}|${i.direction}`);
        }
      }
    } catch (e) { /* ignore */ }
  });

  // Inspect responses
  page.on('response', async res => {
    try {
      const url = res.url();
      const ts = new Date().toISOString();
      found.requests.push({ type: 'response', url, status: res.status(), timestamp: ts });

      const headers = res.headers() || {};
      for (const name of Object.keys(headers)) {
        if (/correl|x-request-id|x-correlation|request-id|x-trace-id/i.test(name)) {
          pushUnique(found.correlationIds, {
            headerName: name,
            value: headers[name],
            url,
            direction: 'response',
            timestamp: ts
          }, i => `${i.headerName}|${i.value}|${i.url}|${i.direction}`);
        }
        if (name.toLowerCase() === 'set-cookie') {
          pushUnique(found.cookies, { source: 'set-cookie', value: headers[name], url, timestamp: ts }, i => `${i.source}|${i.value}|${i.url}`);
        }
      }

      // If JSON, try to parse small bodies to find token-like strings (JWTs or long opaque tokens)
      const ct = (headers['content-type'] || '').toLowerCase();
      if (ct.includes('application/json')) {
        try {
          const text = await res.text();
          if (text && text.length < 200000) {
            // quick regex for Bearer inside body
            const bearerMatch = text.match(/Bearer\s+([A-Za-z0-9\-_\.=]+)/i);
            if (bearerMatch) {
              pushUnique(found.bearerTokens, {
                source: 'response-body-bearer',
                value: bearerMatch[0],
                url, timestamp: ts
              }, i => `${i.source}|${i.value}|${i.url}`);
            }
            // parse JSON and search for token-like values
            try {
              const j = JSON.parse(text);
              const stack = [j];
              while (stack.length) {
                const node = stack.pop();
                if (!node || typeof node !== 'object') continue;
                for (const k of Object.keys(node)) {
                  const v = node[k];
                  if (typeof v === 'string') {
                    if (/^eyJ[A-Za-z0-9-_]+/.test(v) || (v.length > 40 && /^[A-Za-z0-9\-_.=]+$/.test(v))) {
                      pushUnique(found.bearerTokens, {
                        source: 'response-json',
                        key: k,
                        value: v,
                        url, timestamp: ts
                      }, i => `${i.source}|${i.key}|${i.value}|${i.url}`);
                    }
                  } else if (typeof v === 'object') {
                    stack.push(v);
                  }
                }
              }
            } catch (e) { /* invalid JSON? ignore */ }
          }
        } catch (e) { /* ignore body read errors */ }
      }
    } catch (e) { /* ignore */ }
  });

  // Navigate and wait for idle
  await page.goto(TARGET, { waitUntil: 'networkidle2' });

  // small additional wait to catch deferred requests
  await sleep(3000);

  // snapshot storage and cookies
  try {
    const storage = await page.evaluate(() => {
      const dump = { local: {}, session: {} };
      try {
        for (let i = 0; i < localStorage.length; i++) {
          const k = localStorage.key(i);
          dump.local[k] = localStorage.getItem(k);
        }
      } catch (e) {}
      try {
        for (let i = 0; i < sessionStorage.length; i++) {
          const k = sessionStorage.key(i);
          dump.session[k] = sessionStorage.getItem(k);
        }
      } catch (e) {}
      return dump;
    });

    found.localStorage = storage.local;
    found.sessionStorage = storage.session;

    // scan storage for token-like strings
    for (const [k, v] of Object.entries(storage.local || {})) {
      if (typeof v === 'string' && (v.includes('Bearer ') || v.length > 40 || /^eyJ/.test(v))) {
        pushUnique(found.bearerTokens, {
          source: 'localStorage',
          key: k,
          value: v,
          timestamp: new Date().toISOString()
        }, i => `${i.source}|${i.key}|${i.value}`);
      }
    }
    for (const [k, v] of Object.entries(storage.session || {})) {
      if (typeof v === 'string' && (v.includes('Bearer ') || v.length > 40 || /^eyJ/.test(v))) {
        pushUnique(found.bearerTokens, {
          source: 'sessionStorage',
          key: k,
          value: v,
          timestamp: new Date().toISOString()
        }, i => `${i.source}|${i.key}|${i.value}`);
      }
    }

    const cookies = await page.cookies();
    for (const c of cookies) {
      pushUnique(found.cookies, { source: 'cookie', name: c.name, value: c.value, domain: c.domain, path: c.path, httpOnly: c.httpOnly, secure: c.secure, expires: c.expires }, i => `${i.name}|${i.domain}`);
      if (/token|auth|session|jwt|access/i.test(c.name) || (c.value && c.value.length > 40)) {
        pushUnique(found.bearerTokens, {
          source: 'cookie',
          name: c.name,
          value: c.value,
          domain: c.domain,
          timestamp: new Date().toISOString()
        }, i => `${i.source}|${i.name}|${i.value}`);
      }
    }
  } catch (e) {
    // storage/cookie read error - continue
  }

  await enrichBrowsingStoreAcrossSites(page, found);

  // write output
  try {
    fs.writeFileSync(OUT, JSON.stringify(found, null, 2), 'utf8');
    console.log('Wrote', OUT);
  } catch (e) {
    console.error('Failed to write output:', e);
  }

  await browser.close();
})();
