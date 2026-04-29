// Patches https.Agent to bypass broken system DNS for *.googleapis.com
// Uses pre-resolved IPs from 8.8.8.8
const https = require('https');
const dns = require('dns');
const tls = require('tls');

dns.setServers(['8.8.8.8', '1.1.1.1']);

const resolveCache = {};

function resolveGoogle(hostname, cb) {
  if (resolveCache[hostname]) return cb(null, resolveCache[hostname]);
  dns.resolve4(hostname, (err, addrs) => {
    if (!err && addrs.length > 0) {
      resolveCache[hostname] = addrs[0];
      return cb(null, addrs[0]);
    }
    cb(err);
  });
}

const OriginalAgent = https.Agent;
class PatchedAgent extends OriginalAgent {
  createConnection(options, callback) {
    if (options.host && options.host.endsWith('.googleapis.com') || options.host === 'googleapis.com') {
      const host = options.host;
      resolveGoogle(host, (err, ip) => {
        if (err) return callback(err);
        const newOpts = { ...options, host: ip, servername: host };
        callback(null, super.createConnection(newOpts));
      });
      return;
    }
    return super.createConnection(options, callback);
  }
}

// Monkey-patch the global HTTPS agent
https.globalAgent = new PatchedAgent({ keepAlive: true });
const origRequest = https.request.bind(https);
const origGet = https.get.bind(https);

function patchOptions(options) {
  if (typeof options === 'string') return options;
  if (!options.agent) options = { ...options, agent: https.globalAgent };
  return options;
}

https.request = (options, ...args) => origRequest(patchOptions(options), ...args);
https.get = (options, ...args) => origGet(patchOptions(options), ...args);

console.error('[DNS-PATCH] Google DNS patch loaded');
