import http from 'node:http';
import { createInterface } from 'node:readline';
import { once } from 'node:events';
import { pathToFileURL } from 'node:url';
const { aggregate } = await import(pathToFileURL(process.argv[2]).href);
const lines = createInterface({input: process.stdin})[Symbol.asyncIterator]();
const [host, port] = (await lines.next()).value!.split(':');
let seen = 0, finished = 0, connections = 0;
const server = http.createServer(async (req,res) => {
  seen++; res.on('finish', () => { finished++; });
  if (req.method === 'GET' && req.url === '/hello') { res.writeHead(200, {'content-type':'application/json','connection':'close'}); res.end('{"message":"Hello, world!"}'); return; }
  if (req.method !== 'POST' || req.url !== '/aggregate') { res.writeHead(404); res.end(); return; }
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > 64*1024*1024) { res.writeHead(413); res.end(); return; }
    chunks.push(chunk);
  }
  const body = aggregate(Buffer.concat(chunks).toString('utf8'));
  res.writeHead(body === '{"error":"invalid"}' ? 400 : 200, {'content-type':'application/json','connection':'close'});
  res.end(body);
});
server.on('connection', () => { connections++; });
server.listen(Number(port),host);
await once(server,'listening');
console.log('@ready');
await lines.next();
server.close();
await once(server,'close');

console.error(JSON.stringify({seen,finished,connections}));
