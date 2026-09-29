type State={count:number,seed:number};
export function prepare(raw:string):State{return JSON.parse(raw)}
export async function run(s:State):Promise<string>{const a:number[]=[];let v=s.seed;for(let i=0;i<s.count;i++){v=v*48271%1000000007;a.push(v)}a.sort((x,y)=>x-y);return JSON.stringify(a)}
