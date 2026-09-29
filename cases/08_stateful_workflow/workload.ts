type Item = {kind: string, amount: number, payload: number[]};
type Request = {key: string, mode: string, items: Item[]};
type Cell = {id: number, value: number, payload: number[]};
type Entry = {total: number, cells: Cell[]};
type Config = {requests: string[], batch: number, retain: number, fanout: number, delay_ms: number, capture: boolean};
type State = {config: Config, cache: Map<string, Entry>, order: string[], slot: number, cursor: number, digest: number, response_bytes: number};
export function prepare(raw: string): State {
  return {config: JSON.parse(raw), cache: new Map(), order: [], slot: 0, cursor: 0, digest: 0, response_bytes: 0};
}
async function tool(req: Request, worker: number, delay: number): Promise<Cell[]> {
  const cells: Cell[] = [];
  for(let i=worker;i<req.items.length;i+=4) {
    const item=req.items[i];
    const value=item.kind==='credit'?item.amount:item.kind==='debit'?-item.amount:0;
    cells.push({id:i,value,payload:item.payload.map(v=>v+worker+1)});
  }
  if(delay) await new Promise(resolve=>setTimeout(resolve,delay));
  return cells;
}
function sum(c: Cell) {return c.value+c.payload.reduce((a,b)=>a+b,0);}
function check(cells: Cell[]) {return cells.reduce((v,c)=>v+(c.id+1)*sum(c),0);}
async function process(s: State, raw: string) {
  const req: Request=JSON.parse(raw);
  if(!req||typeof req.key!=='string'||!req.key||!/^[\x00-\x7f]*$/.test(req.key)||!['replace','accumulate'].includes(req.mode)||!Array.isArray(req.items)) throw Error('invalid');
  for(const item of req.items) {
    if(!item||!['credit','debit','skip'].includes(item.kind)||!Number.isInteger(item.amount)||item.amount<0||item.amount>1000000||!Array.isArray(item.payload)||item.payload.some(v=>!Number.isInteger(v)||v<0||v>1000000)) throw Error('invalid');
  }
  const parts: Cell[][]=[];
  if(s.config.fanout===4) parts.push(...await Promise.all([0,1,2,3].map(i=>tool(req,i,s.config.delay_ms))));
  else for(let i=0;i<4;i++) parts.push(await tool(req,i,s.config.delay_ms));
  const cells: Cell[]=[];
  for(const part of parts) for(const cell of part) cells.push(cell);
  let total=cells.reduce((v,c)=>v+sum(c),0);
  if(req.mode==='accumulate') total+=s.cache.get(req.key)?.total??0;
  let evicted='';
  if(s.config.retain) {
    if(!s.cache.has(req.key)) {
      if(s.order.length<s.config.retain) s.order.push(req.key);
      else {evicted=s.order[s.slot];s.cache.delete(evicted);s.order[s.slot]=req.key;s.slot=(s.slot+1)%s.config.retain;}
    }
    s.cache.set(req.key,{total,cells});
  }
  return {seq:s.cursor,ok:true,key:req.key,total,check:check(cells),evicted};
}
export async function run(s: State): Promise<string> {
  const responses=[];
  for(let i=0;i<s.config.batch;i++) {
    let response;
    try {response=await process(s,s.config.requests[s.cursor%s.config.requests.length]);}
    catch {response={seq:s.cursor,ok:false,key:'',total:0,check:0,evicted:''};}
    s.response_bytes+=JSON.stringify(response).length;
    for(const v of [s.cursor,Number(response.ok),response.total,response.check,s.cache.size]) s.digest=((s.digest*257+v)%1000000007+1000000007)%1000000007;
    if(s.config.capture) responses.push(response);
    s.cursor++;
  }
  const cache=Array.from(s.cache.keys()).sort().map(key=>{const e=s.cache.get(key)!;return {key,total:e.total,check:check(e.cells),count:e.cells.length};});
  return JSON.stringify({processed:s.cursor,digest:s.digest,response_bytes:s.response_bytes,cache,responses});
}
